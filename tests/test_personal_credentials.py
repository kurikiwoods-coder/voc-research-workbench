import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.edition_policy import Edition
from src.raw_store.credentials import VaultError, windows_protect
from src.raw_store.personal_credentials import PersonalCredentials
from src.raw_store.runtime_binding import bind_directory


FIRST = "offline-synthetic-personal-credential-first"
ROTATED = "offline-synthetic-personal-credential-rotated"
BINDING = ("packycode", "offline-channel", "offline-account")
UNCONFIGURED = {
    "configured": False, "provider": None, "channel_ref": None,
    "account_ref": None, "credential_revision": None,
}


def synthetic_protection(data, *, encrypt):
    if encrypt:
        return b"fixture:" + data[::-1]
    if not data.startswith(b"fixture:"):
        raise VaultError("The fixture credential cannot be opened.")
    return data[len(b"fixture:"):][::-1]


class PersonalCredentialsTests(unittest.TestCase):
    def setUp(self):
        parent = os.environ["LOCALAPPDATA"] if os.name == "nt" else None
        self.temporary = TemporaryDirectory(prefix="voc-credential-fixture-", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = bind_directory(Path(self.temporary.name) / "new-runtime", Edition.PERSONAL)
        self.vault = PersonalCredentials(self.root)

    def assert_status(self, status):
        self.assertEqual(set(UNCONFIGURED), set(status))
        self.assertIs(status["configured"], True)
        self.assertEqual(BINDING, (status["provider"], status["channel_ref"], status["account_ref"]))
        self.assertRegex(status["credential_revision"], r"^[0-9a-f]{32}$")
        for marker in (FIRST, ROTATED):
            self.assertNotIn(marker, json.dumps(status))

    def lifecycle(self):
        self.assertEqual(UNCONFIGURED, self.vault.read())
        self.assertFalse(self.vault.path.exists())
        first = self.vault.put(*BINDING, FIRST)
        self.assert_status(first)
        first_bytes = self.vault.path.read_bytes()
        self.assertNotIn(FIRST.encode(), first_bytes)
        self.assertEqual(first, PersonalCredentials(self.root).read())

        rotated = self.vault.put(*BINDING, ROTATED)
        self.assert_status(rotated)
        self.assertNotEqual(first["credential_revision"], rotated["credential_revision"])
        rotated_bytes = self.vault.path.read_bytes()
        self.assertNotEqual(first_bytes, rotated_bytes)
        self.assertNotIn(ROTATED.encode(), rotated_bytes)
        self.assertEqual(rotated, PersonalCredentials(self.root).read())

        self.assertEqual(UNCONFIGURED, self.vault.delete())
        tombstone = self.vault.path.read_bytes()
        self.assertNotIn(tombstone, (first_bytes, rotated_bytes))
        self.assertEqual(UNCONFIGURED, PersonalCredentials(self.root).read())
        self.assertFalse((self.root / "credentials").exists())
        self.assertEqual({".voc-personal", self.vault.path.name}, {path.name for path in self.root.iterdir()})
        return tombstone

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_synthetic_lifecycle(self):
        self.lifecycle()

    @unittest.skipUnless(os.name == "nt", "Windows CurrentUser DPAPI only")
    def test_native_dpapi_lifecycle(self):
        tombstone = self.lifecycle()
        self.assertEqual({"version": 1, "configured": False, "scope": ""},
                         json.loads(windows_protect(tombstone, encrypt=False)))

    @unittest.skipIf(os.name == "nt", "non-Windows fail-closed path")
    def test_no_unencrypted_production_fallback(self):
        self.assertEqual(UNCONFIGURED, self.vault.read())
        with self.assertRaises(VaultError):
            self.vault.put(*BINDING, FIRST)
        self.assertFalse(self.vault.path.exists())
        with self.assertRaises(VaultError):
            self.vault.delete()
        self.assertFalse(self.vault.path.exists())

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_atomic_replace_failure_keeps_last_acknowledged_revision(self):
        first = self.vault.put(*BINDING, FIRST)
        contents = self.vault.path.read_bytes()
        with patch("src.raw_store.personal_credentials.os.replace", side_effect=OSError):
            with self.assertRaises(VaultError):
                self.vault.put(*BINDING, ROTATED)
            with self.assertRaises(VaultError):
                self.vault.delete()
        self.assertEqual(first, PersonalCredentials(self.root).read())
        self.assertEqual(contents, self.vault.path.read_bytes())
        self.assertEqual({".voc-personal", self.vault.path.name}, {path.name for path in self.root.iterdir()})

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_corrupt_and_linked_files_fail_closed(self):
        self.vault.put(*BINDING, FIRST)
        self.vault.path.write_bytes(b"invalid-ciphertext")
        with self.assertRaises(VaultError):
            PersonalCredentials(self.root).read()
        invalid_state = b'{"version":1,"configured":false,"api_key":"invalid"}'
        self.vault.path.write_bytes(synthetic_protection(invalid_state, encrypt=True))
        with self.assertRaises(VaultError):
            PersonalCredentials(self.root).read()
        sibling = self.vault.path.with_suffix(".linked")
        os.link(self.vault.path, sibling)
        with self.assertRaises(VaultError):
            self.vault.read()
        with self.assertRaises(VaultError):
            self.vault.delete()
        self.assertEqual(sibling.read_bytes(), self.vault.path.read_bytes())

    def test_invalid_binding_and_unbound_root_rejected(self):
        invalid = (None, "with a space", "bad\nvalue", "a" * 513)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(VaultError):
                self.vault.put(*BINDING, value)
        with self.assertRaises(VaultError):
            self.vault.put("packycode", "account-" + FIRST, "offline-account", FIRST)
        self.assertFalse(self.vault.path.exists())
        (self.root / ".voc-personal").unlink()
        with self.assertRaises(VaultError):
            self.vault.read()


if __name__ == "__main__":
    unittest.main()
