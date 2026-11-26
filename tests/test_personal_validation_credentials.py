"""Verify pre-admission credential binding with synthetic secrets and no transport."""

from dataclasses import replace
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.dashboard.personal_workspace import provision
from src.edition_policy import Decision, Deployment, Domain, Edition, Permission, Scope
from src.raw_store.credentials import VaultError
from src.raw_store.personal_credentials import PersonalCredentials
from src.raw_store.personal_validation import BatchContext, ValidationLedger
from src.raw_store.personal_validation_credentials import (
    put_validation_credential, revoke_validation_credential, validation_binding,
)
from src.raw_store.store import Conflict, Store
from test_personal_credentials import FIRST, ROTATED, synthetic_protection


class ValidationCredentialTests(unittest.TestCase):
    def setUp(self):
        fixture = self.enterContext(TemporaryDirectory(
            prefix="voc-D 凭证 ", dir=os.environ.get("LOCALAPPDATA") if os.name == "nt" else None,
        ))
        self.directory = Path(fixture) / "local"
        workspace = provision(self.directory, "合成项目", "凭证隔离", uuid4())
        self.scope = Scope(*(workspace[key] for key in ("study_id", "scope_id", "scope_version")))
        self.store = Store(self.directory, edition=Edition.PERSONAL)
        self.decision = Decision(
            Edition.PERSONAL, Deployment.LOCAL, Domain.LOCAL_WORKSPACE,
            Permission.MANAGE_PERSONAL_CREDENTIALS, "personal", "NOT_EVALUATED", True, "fixture",
            "fixture-actor", "fixture-owner", self.scope, "personal_research",
            (Permission.MANAGE_PERSONAL_CREDENTIALS,), ("local:fixture-authorization",),
        )
        self.context = BatchContext(
            self.scope.study_id, self.scope.scope_id, self.scope.scope_version,
            self.decision.actor_ref, self.decision.owner_ref, self.decision.evidence_refs[0], self.decision.policy_version,
        )

    def put(self, operation="search", provider="tavily", api_key=FIRST, **changes):
        return put_validation_credential(self.store, **(
            dict(authorize=lambda db: self.decision, operation=operation, provider=provider,
                 account_ref="fixture-account", channel_ref="fixture-channel", api_key=api_key,
                 evidence_ref="local:fixture-credential") | changes
        ))

    def revoke(self, binding):
        revoke_validation_credential(
            self.store, authorize=lambda db: self.decision, operation=binding["operation"],
            provider=binding["provider"], account_ref=binding["account_ref"], channel_ref=binding["channel_ref"],
            evidence_ref="local:fixture-revocation",
        )

    def reveal(self, binding, context=None):
        with self.store.db() as db:
            db.execute("BEGIN")
            return validation_binding(self.store, db, context or self.context, binding)

    def vault(self, operation=None):
        extra = {"validation_operation": operation, "scope_version": self.scope.scope_version} if operation else {}
        return PersonalCredentials(self.directory, study_id=self.scope.study_id, scope_id=self.scope.scope_id, **extra)

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_scoped_bindings_prevent_cross_operation_and_scope_replay(self):
        search = self.put()
        source = self.put("source", "stackexchange", ROTATED)
        self.assertEqual(self.reveal(search), FIRST)
        self.assertEqual(self.reveal(source), ROTATED)
        self.assertNotIn(FIRST, repr(search))
        self.assertNotIn(ROTATED, repr(source))
        self.assertNotIn(FIRST.encode(), self.store.path.read_bytes())
        self.assertNotIn(ROTATED.encode(), self.store.path.read_bytes())
        for invalid in (
            search | {"credential_revision": source["credential_revision"]},
            search | {"provider": "stackexchange"},
            search | {"channel_ref": "other-channel"},
            search | {"account_ref": "other-account"},
        ):
            with self.assertRaises(VaultError):
                self.reveal(invalid)
        with self.assertRaises(VaultError):
            self.reveal(search, replace(self.context, scope_version="v2"))
        source_file = self.vault("source")._revision_path(source["credential_revision"])
        search_file = self.vault("search")._revision_path(search["credential_revision"])
        source_file.write_bytes(search_file.read_bytes())
        with self.assertRaises(VaultError):
            self.reveal(source)

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_rotation_failure_retains_new_anchor_and_blocks_old_ciphertext(self):
        old = self.put()
        vault = self.vault("search")
        old_file = vault._revision_path(old["credential_revision"])
        encrypted = old_file.read_bytes()
        with patch.object(PersonalCredentials, "discard_unbound", side_effect=OSError):
            with self.assertRaisesRegex(VaultError, "CLEANUP_UNAVAILABLE"):
                self.put(api_key=ROTATED)
        with self.store.db() as db:
            current = ValidationLedger(self.store).current_credential(db, self.context, "search", "tavily")
        self.assertEqual(self.reveal(current), ROTATED)
        self.assertEqual(old_file.read_bytes(), encrypted)
        with self.assertRaises(VaultError):
            self.reveal(old)
        self.revoke(current)
        old_file.write_bytes(encrypted)
        if os.name != "nt":
            old_file.chmod(0o600)
        with self.assertRaises(VaultError):
            self.reveal(old)
        with self.assertRaises(VaultError):
            self.reveal(current)

    def test_anonymous_source_has_a_unique_revocable_binding(self):
        with patch("src.raw_store.personal_credentials._protect", side_effect=AssertionError("anonymous DPAPI read")):
            first = self.put("source", "stackexchange", None)
            self.assertIsNone(self.reveal(first))
            self.revoke(first)
            with self.assertRaises(VaultError):
                self.reveal(first)
            second = self.put("source", "stackexchange", None)
            self.assertNotEqual(first["credential_revision"], second["credential_revision"])
            self.assertIsNone(self.reveal(second))
            with self.assertRaises(VaultError):
                self.reveal(first)

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_model_needs_current_c_anchor_even_if_old_dpapi_survives(self):
        vault = self.vault()
        first = vault.put("packycode", "typesafe-officially", "fixture-account", FIRST)
        with self.store.db() as db:
            db.execute("INSERT INTO personal_credential_binding VALUES (?, ?, ?)", (
                self.scope.study_id, self.scope.scope_id, first["credential_revision"],
            ))
        current = self.put("model", "packycode", None, channel_ref="typesafe-officially")
        self.assertEqual(self.reveal(current), FIRST)
        with self.assertRaises(VaultError):
            self.put("model", "packycode", ROTATED, channel_ref="typesafe-officially")
        rotated = vault.put("packycode", "typesafe-officially", "fixture-account", ROTATED)
        with self.store.db() as db:
            db.execute("UPDATE personal_credential_binding SET credential_revision=?", (rotated["credential_revision"],))
        self.assertTrue(vault._revision_path(first["credential_revision"]).exists())
        with self.assertRaises(VaultError):
            self.reveal(current)
        updated = self.put("model", "packycode", None, channel_ref="typesafe-officially")
        self.assertEqual(self.reveal(updated), ROTATED)
        with self.store.db() as db:
            db.execute("DELETE FROM personal_credential_binding")
        with self.assertRaises(VaultError):
            self.reveal(updated)

    @patch("src.raw_store.personal_credentials._protect", synthetic_protection)
    def test_authority_change_and_dpapi_failure_cannot_save_active_anchor(self):
        denied = replace(self.decision, allowed=False)
        with self.assertRaisesRegex(Conflict, "AUTHORITY_REQUIRED"):
            self.put(authorize=lambda db: denied)
        verdicts = iter((self.decision, denied))
        with self.assertRaisesRegex(Conflict, "AUTHORITY_REQUIRED"):
            self.put(authorize=lambda db: next(verdicts))
        with patch("src.raw_store.personal_credentials._protect", side_effect=VaultError("DPAPI fixture failure")):
            with self.assertRaisesRegex(VaultError, "DPAPI"):
                self.put(api_key=ROTATED)
        with self.store.db() as db:
            self.assertIsNone(ValidationLedger(self.store).current_credential(db, self.context, "search", "tavily"))

    @unittest.skipUnless(os.name == "nt", "Windows CurrentUser DPAPI only")
    def test_native_dpapi_roundtrip_uses_separate_operation_envelopes(self):
        search = self.put()
        source = self.put("source", "stackexchange", ROTATED)
        for binding, secret in ((search, FIRST), (source, ROTATED)):
            vault = self.vault(binding["operation"])
            path = vault._revision_path(binding["credential_revision"])
            self.assertNotIn(secret.encode(), path.read_bytes())
            self.assertEqual(self.reveal(binding), secret)
            self.revoke(binding)
            self.assertFalse(path.exists())
            with self.assertRaises(VaultError):
                self.reveal(binding)
