"""DPAPI-protected Personal live authorization and evidence outside the workspace."""

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from src.edition_policy import canonical_uuid
from src.raw_store.credentials import VaultError
from src.raw_store.personal_credentials import _check_path, _native_path, _protect
from src.raw_store.runtime_binding import personal_directory
from src.raw_store.store import dump


MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
SLOTS = {("search", 1), ("source", 1), ("model", 1), ("model", 2)}
REVIEWS = {"C0-2", "C0-4", "C0-5", "C0-6"}


class AuthorityError(ValueError):
    """A protected authorization record is unavailable or inconsistent."""


def _digest(value):
    return sha256(dump(value).encode("utf-8")).hexdigest()


def _stable(row):
    return {key: value for key, value in row.items() if key not in {"state", "state_reason"}}


def _absolute(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise AuthorityError("LIVE_AUTHORITY_ABSOLUTE_PATH_REQUIRED")
    return path


def _checked_path(path, *, directory=False):
    for parent in reversed(path.parents):
        if parent.parent != parent:
            _check_path(_native_path(parent).lstat(), directory=True)
    info = _native_path(path).lstat()
    _check_path(info, directory=directory, private=directory)
    return info


def _identity(info):
    if not info.st_ino:
        raise AuthorityError("LIVE_AUTHORITY_FILE_ID_MISSING")
    return [info.st_dev, info.st_ino]


class PersonalLiveAuthority:
    """Persist external batch anchors, per-slot grants and irrevocable send claims."""

    def __init__(self, directory, *, database, workspace_roots=()):
        self.directory = _absolute(directory)
        self.database = _absolute(database)
        repository = Path(__file__).resolve().parents[2]
        roots = (repository, self.database.parent, *(_absolute(path) for path in workspace_roots))
        try:
            root_id = _identity(_checked_path(self.directory, directory=True))
            self.directory = self.directory.resolve(strict=True)
            if any(self.directory.is_relative_to(root) or root.is_relative_to(self.directory)
                   for root in (root.resolve() for root in roots)):
                raise AuthorityError("LIVE_AUTHORITY_DIRECTORY_OVERLAP")
            personal_directory(self.directory)
            _checked_path(self.database)
            self.database = self.database.resolve(strict=True)
        except AuthorityError:
            raise
        except (OSError, ValueError):
            raise AuthorityError("LIVE_AUTHORITY_DIRECTORY_UNSAFE") from None
        self._root_id = root_id

    def _check_root(self):
        if _identity(_checked_path(self.directory, directory=True)) != self._root_id:
            raise AuthorityError("LIVE_AUTHORITY_DIRECTORY_CHANGED")

    def _database_anchor(self):
        return {"database": os.path.normcase(self.database), "file_id": _identity(_checked_path(self.database))}

    def deployment_record(self, owner_sha256, evidence_ref, *, create=False):
        value = {
            "workspace": self._database_anchor(), "directory": os.path.normcase(self.directory),
            "directory_id": self._root_id, "owner_sha256": owner_sha256, "evidence_ref": evidence_ref,
        }
        if create:
            self._create("deployment", value)
        if self._read("deployment") != value:
            raise AuthorityError("LIVE_DEPLOYMENT_BINDING_REQUIRED")
        return _digest(value)

    def _read(self, key):
        try:
            self._check_root()
            path = _native_path(self.directory / f"{key}.dpapi")
            info = path.lstat()
            _check_path(info, private=True)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                opened = os.fstat(stream.fileno())
                _check_path(opened, private=True)
                if _identity(opened) != _identity(info):
                    raise AuthorityError("LIVE_AUTHORITY_RECORD_CHANGED")
                encrypted = stream.read(MAX_ARTIFACT_BYTES + 1)
            if not 0 < len(encrypted) <= MAX_ARTIFACT_BYTES:
                raise AuthorityError("LIVE_AUTHORITY_RECORD_INVALID")
            envelope = json.loads(_protect(encrypted, encrypt=False))
            if (not isinstance(envelope, dict) or set(envelope) != {"version", "key", "value"}
                    or envelope["version"] != 1 or envelope["key"] != key):
                raise AuthorityError("LIVE_AUTHORITY_RECORD_INVALID")
            return envelope["value"]
        except FileNotFoundError:
            return None
        except (OSError, ValueError, VaultError, RecursionError):
            raise AuthorityError("LIVE_AUTHORITY_RECORD_UNAVAILABLE") from None

    def _create(self, key, value):
        stage = None
        try:
            self._check_root()
            encrypted = _protect(dump({"version": 1, "key": key, "value": value}).encode("utf-8"), encrypt=True)
            if not 0 < len(encrypted) <= MAX_ARTIFACT_BYTES:
                raise AuthorityError("LIVE_AUTHORITY_RECORD_TOO_LARGE")
            target = _native_path(self.directory / f"{key}.dpapi")
            with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                stage = Path(stream.name)
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_root()
            if os.name == "nt":
                os.rename(stage, target)
                stage = None
            else:
                os.link(stage, target)
                stage.unlink()
                stage = None
                directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return True
        except FileExistsError:
            return False
        except (OSError, ValueError, VaultError, TypeError, RecursionError):
            raise AuthorityError("LIVE_AUTHORITY_RECORD_WRITE_FAILED") from None
        finally:
            if stage is not None:
                try:
                    stage.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _batch(batch):
        batch_id = batch.get("batch_id")
        if (batch_id is None or canonical_uuid(batch_id) != batch_id
                or (batch.get("mode"), batch.get("edition"), batch.get("purpose"))
                != ("formal_live", "PERSONAL", "g1_personal_acceptance")):
            raise AuthorityError("LIVE_AUTHORITY_BATCH_INVALID")
        return batch_id, _digest(_stable(batch))

    @staticmethod
    def _slot(batch_id, grant):
        operation, slot = grant.get("operation"), grant.get("slot")
        grant_id = grant.get("grant_id")
        if (grant.get("batch_id") != batch_id or type(slot) is not int or (operation, slot) not in SLOTS
                or grant_id is None or canonical_uuid(grant_id) != grant_id):
            raise AuthorityError("LIVE_AUTHORITY_GRANT_INVALID")
        return f"{batch_id}-{operation}-{slot}"

    def _authorization(self, batch, grant):
        batch_id, batch_digest = self._batch(batch)
        slot = self._slot(batch_id, grant)
        return slot, {"batch": batch_digest, "grant": _digest(_stable(grant))}

    def _send_binding(self, batch, grant, request):
        slot, binding = self._authorization(batch, grant)
        request_id = request.get("request_id")
        if (request_id is None or canonical_uuid(request_id) != request_id
                or any(request.get(field) != grant.get(field) for field in (
                    "batch_id", "grant_id", "operation", "slot", "payload_sha256",
                ))):
            raise AuthorityError("LIVE_AUTHORITY_REQUEST_INVALID")
        return slot, binding | {"request": _digest(_stable(request))}

    def _current(self, batch, grant=None):
        batch_id, digest = self._batch(batch)
        database = self._database_anchor()
        if (self._read("database") != database
                or self._read(f"batch-{batch_id}") != {"batch": digest, **database}
                or self._read(f"revoked-{batch_id}") is not None):
            return False
        if grant is None:
            return True
        slot, expected = self._authorization(batch, grant)
        return self._read(f"grant-{slot}") == expected

    @staticmethod
    def _claimed_request(db, request_id):
        cursor = db.execute("""
            SELECT q.* FROM personal_validation_requests q
            JOIN personal_validation_request_events e USING (request_id)
            WHERE q.request_id=? AND e.state='claimed'
        """, (request_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip((column[0] for column in cursor.description), row, strict=True))

    def _claims_current(self, db):
        self._check_root()
        for path in _native_path(self.directory).glob("claim-*.dpapi"):
            record = self._read(path.stem)
            if not isinstance(record, dict):
                return False
            row = self._claimed_request(db, record.get("request_id"))
            if row is None or _digest(row) != record.get("request"):
                return False
        return True

    def _charges_current(self, db):
        for path in _native_path(self.directory).glob("live-charge-*.dpapi"):
            value = self._read(path.stem)
            if not isinstance(value, dict) or not isinstance(value.get("proof"), dict):
                return False
            proof = value["proof"]
            request_id = proof.get("request_id")
            if path.stem != f"live-charge-{request_id}":
                return False
            row = db.execute("""
                SELECT c.evidence_ref, c.actual_units, c.subject_ref
                FROM personal_validation_reconciliations c JOIN personal_validation_requests q USING (request_id)
                WHERE c.request_id=? AND q.batch_id=? AND q.grant_id=? ORDER BY c.sequence DESC LIMIT 1
            """, (request_id, value.get("batch_id"), value.get("grant_id"))).fetchone()
            if row is None or tuple(row) != (f"live-charge-{_digest(value)}", proof.get("actual_units"),
                                               proof.get("bill_ref")):
                return False
        return True

    def check(self, db, batch, grant):
        """Confirm the SQLite connection and the current independent authorization."""
        try:
            sqlite_main = next(row[2] for row in db.execute("PRAGMA database_list") if row[1] == "main")
            if Path(sqlite_main).resolve(strict=True) != self.database:
                return False
            return self._current(batch, grant) and self._claims_current(db) and self._charges_current(db)
        except (OSError, ValueError, sqlite3.Error, StopIteration):
            return False

    def register_batch(self, batch):
        batch_id, digest = self._batch(batch)
        key = f"batch-{batch_id}"
        database = self._database_anchor()
        if not self._create("database", database) and self._read("database") != database:
            raise AuthorityError("LIVE_AUTHORITY_DATABASE_CHANGED")
        expected = {"batch": digest, **database}
        if not self._create(key, expected) and self._read(key) != expected:
            raise AuthorityError("LIVE_AUTHORITY_BATCH_CONFLICT")

    def authorize(self, batch, grant):
        if not self._current(batch):
            raise AuthorityError("LIVE_AUTHORITY_BATCH_NOT_CURRENT")
        slot, expected = self._authorization(batch, grant)
        key = f"grant-{slot}"
        if not self._create(key, expected) and self._read(key) != expected:
            raise AuthorityError("LIVE_AUTHORITY_SLOT_CONFLICT")

    def revoke(self, batch):
        batch_id, digest = self._batch(batch)
        key = f"revoked-{batch_id}"
        if not self._create(key, digest) and self._read(key) != digest:
            raise AuthorityError("LIVE_AUTHORITY_REVOCATION_CONFLICT")

    def claim(self, batch, grant, request):
        slot, expected = self._send_binding(batch, grant, request)
        if request.get("state") != "claimed" or not self._current(batch, grant):
            raise AuthorityError("LIVE_AUTHORITY_CLAIM_INELIGIBLE")
        if self._read(f"claim-{slot}") is not None:
            return False
        try:
            with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as db:
                db.execute("BEGIN")
                claimed = self._claimed_request(db, request["request_id"])
                if (claimed is None or _digest(claimed) != expected["request"] or not self.check(db, batch, grant)):
                    raise AuthorityError("LIVE_AUTHORITY_CLAIM_NOT_CURRENT")
        except (OSError, sqlite3.Error):
            raise AuthorityError("LIVE_AUTHORITY_CLAIM_NOT_CURRENT") from None
        return self._create(f"claim-{slot}", expected | {"request_id": request["request_id"]})

    def verify_claim(self, batch, grant, request):
        try:
            slot, expected = self._send_binding(batch, grant, request)
            return self._read(f"claim-{slot}") == expected | {"request_id": request["request_id"]}
        except AuthorityError:
            return False

    def archive(self, batch, grant, request, payload, response):
        if (not self.verify_claim(batch, grant, request)
                or _digest(payload) != request["payload_sha256"]):
            raise AuthorityError("LIVE_AUTHORITY_ARCHIVE_UNBOUND")
        batch_id = batch["batch_id"]
        request_id = request["request_id"]
        ref = f"live-receipt-{request_id}"
        value = {"batch_id": batch_id, "request_id": request_id, "request": payload, "response": response}
        if not self._create(ref, value) and self._read(ref) != value:
            raise AuthorityError("LIVE_AUTHORITY_ARCHIVE_CONFLICT")
        return ref

    def read_archive(self, batch, grant, request, response_sha256):
        if not self.verify_claim(batch, grant, request):
            raise AuthorityError("LIVE_AUTHORITY_ARCHIVE_UNBOUND")
        value = self._read(f"live-receipt-{request['request_id']}")
        if (not isinstance(value, dict) or set(value) != {"batch_id", "request_id", "request", "response"}
                or value["batch_id"] != batch["batch_id"] or value["request_id"] != request["request_id"]
                or _digest(value["request"]) != request["payload_sha256"]
                or _digest(value["response"]) != response_sha256):
            raise AuthorityError("LIVE_AUTHORITY_ARCHIVE_MISSING_OR_INVALID")
        return value

    def has_archive(self, batch, grant, request, response_sha256):
        try:
            self.read_archive(batch, grant, request, response_sha256)
        except AuthorityError:
            return False
        return True

    def _charge(self, batch, grant, request, proof):
        if (not self.verify_claim(batch, grant, request) or not isinstance(proof, dict)
                or proof.get("request_id") != request["request_id"]
                or proof.get("currency") != batch.get("currency")
                or any(proof.get(field) != grant.get(field) for field in ("provider", "account_ref"))):
            raise AuthorityError("LIVE_AUTHORITY_CHARGE_UNBOUND")
        return {"batch_id": batch["batch_id"], "grant_id": grant["grant_id"], "proof": proof}

    def archive_charge(self, batch, grant, request, proof):
        value = self._charge(batch, grant, request, proof)
        key = f"live-charge-{request['request_id']}"
        if not self._create(key, value) and self._read(key) != value:
            raise AuthorityError("LIVE_AUTHORITY_CHARGE_CONFLICT")
        return f"live-charge-{_digest(value)}"

    def read_charge(self, batch, grant, request, evidence_ref):
        value = self._read(f"live-charge-{request['request_id']}")
        if (not isinstance(value, dict) or evidence_ref != f"live-charge-{_digest(value)}"
                or self._charge(batch, grant, request, value.get("proof")) != value):
            raise AuthorityError("LIVE_AUTHORITY_CHARGE_MISSING_OR_INVALID")
        return value["proof"]

    def archive_review(self, batch, requirement, evidence):
        if requirement not in REVIEWS or not self._current(batch) or not isinstance(evidence, dict):
            raise AuthorityError("LIVE_AUTHORITY_REVIEW_UNBOUND")
        labels = {"batch_id": batch["batch_id"], "requirement": requirement}
        if any(evidence.get(key, value) != value for key, value in labels.items()):
            raise AuthorityError("LIVE_AUTHORITY_REVIEW_UNBOUND")
        value = evidence | labels
        digest = _digest(value)
        ref = f"live-review-{requirement}-{digest}"
        if not self._create(ref, value) and self._read(ref) != value:
            raise AuthorityError("LIVE_AUTHORITY_REVIEW_CONFLICT")
        return ref, digest

    def read_review(self, batch, requirement, ref, digest):
        batch_id, _ = self._batch(batch)
        if (requirement not in REVIEWS or not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or ref != f"live-review-{requirement}-{digest}"):
            raise AuthorityError("LIVE_AUTHORITY_REVIEW_UNBOUND")
        value = self._read(ref)
        if (not isinstance(value, dict) or value.get("batch_id") != batch_id
                or value.get("requirement") != requirement or _digest(value) != digest):
            raise AuthorityError("LIVE_AUTHORITY_REVIEW_MISSING_OR_INVALID")
        return value
