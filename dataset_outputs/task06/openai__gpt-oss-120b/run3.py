"""
Password Manager Implementation
================================

Features
--------
- Secure storage of passwords using AES‑GCM (via ``cryptography``).
- Master‑password based authentication (key derived with PBKDF2‑HMAC‑SHA256).
- Add / edit / delete password entries.
- Random password generator.
- Typed public API with docstrings and thorough error handling.

Only the ``cryptography`` package from PyPI is required in addition to the
standard library.
"""

from __future__ import annotations

import json
import os
import secrets
import string
from base64 import b64encode, b64decode
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class PasswordManagerError(Exception):
    """Base class for all password manager errors."""


class AuthenticationError(PasswordManagerError):
    """Raised when the master password is incorrect."""


class EntryNotFoundError(PasswordManagerError):
    """Raised when a requested entry does not exist."""


class CorruptedStoreError(PasswordManagerError):
    """Raised when the encrypted store cannot be decrypted or is malformed."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass
class PasswordEntry:
    """
    Represents a single password record.

    Attributes
    ----------
    service: Name of the service / site.
    username: Username for the service.
    password: Encrypted password (plaintext in memory, stored encrypted).
    notes: Optional free‑form notes.
    """
    service: str
    username: str
    password: str
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        """Serialize entry to a JSON‑compatible dict."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "PasswordEntry":
        """Create a :class:`PasswordEntry` from a dict."""
        return PasswordEntry(
            service=data["service"],
            username=data["username"],
            password=data["password"],
            notes=data.get("notes", ""),
        )


# --------------------------------------------------------------------------- #
# Utility functions
# --------------------------------------------------------------------------- #


def _derive_key(master_password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    """
    Derive a 256‑bit AES key from the master password using PBKDF2‑HMAC‑SHA256.

    Parameters
    ----------
    master_password: The master password supplied by the user.
    salt: Random‑generated 16‑byte salt.
    iterations: Number of PBKDF2 iterations (default 200k).

    Returns
    -------
    32‑byte key suitable for AES‑GCM.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(master_password.encode("utf-8"))


def _encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Encrypt data with AES‑GCM.

    Returns
    -------
    A bytes object: ``nonce || ciphertext || tag``.
    """
    nonce = secrets.token_bytes(12)  # 96‑bit nonce recommended for GCM
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext  # ciphertext already contains the tag


def _decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt data produced by :func:`_encrypt`.

    Parameters
    ----------
    ciphertext: ``nonce || ciphertext || tag``.
    key: AES‑GCM key.

    Returns
    -------
    The original plaintext.
    """
    if len(ciphertext) < 12:
        raise CorruptedStoreError("Ciphertext too short.")
    nonce = ciphertext[:12]
    ct = ciphertext[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, associated_data=None)


def _load_json(data: bytes) -> Dict[str, Any]:
    """Decode UTF‑8 JSON bytes to a Python dict."""
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorruptedStoreError("Failed to decode JSON data.") from exc


def _dump_json(obj: Dict[str, Any]) -> bytes:
    """Encode Python dict to UTF‑8 JSON bytes."""
    return json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")


# --------------------------------------------------------------------------- #
# Core password manager
# --------------------------------------------------------------------------- #


class PasswordManager:
    """
    Password manager handling encrypted storage and entry manipulation.

    Example
    -------
    >>> pm = PasswordManager(Path("vault.bin"))
    >>> pm.unlock("my_master_password")
    >>> pm.add_entry("example.com", "alice", "s3cr3t")
    >>> pm.save()
    """

    _SALT_SIZE = 16
    _VERSION = 1  # future‑proofing for format changes

    def __init__(self, store_path: Path) -> None:
        """
        Parameters
        ----------
        store_path: Path to the encrypted vault file. The file will be created
                    on first ``save()`` if it does not exist.
        """
        self.store_path = store_path.expanduser().resolve()
        self._key: Optional[bytes] = None
        self._entries: Dict[str, PasswordEntry] = {}
        self._salt: Optional[bytes] = None

        if self.store_path.is_file():
            self._load_header()

    # ------------------------------------------------------------------- #
    # Internal helpers
    # ------------------------------------------------------------------- #

    def _load_header(self) -> None:
        """Read the file header (version + salt) without attempting decryption."""
        try:
            with self.store_path.open("rb") as f:
                header = f.read(1 + self._SALT_SIZE)
            if len(header) != 1 + self._SALT_SIZE:
                raise CorruptedStoreError("Header size mismatch.")
            version = header[0]
            if version != self._VERSION:
                raise CorruptedStoreError(f"Unsupported vault version: {version}")
            self._salt = header[1:]
        except OSError as exc:
            raise PasswordManagerError(f"Failed to read vault file: {exc}") from exc

    def _ensure_unlocked(self) -> None:
        if self._key is None:
            raise AuthenticationError("Vault is locked. Call 'unlock' first.")

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #

    def unlock(self, master_password: str) -> None:
        """
        Derive the encryption key from the master password and decrypt the store.

        Parameters
        ----------
        master_password: The master password supplied by the user.
        """
        if not self.store_path.is_file():
            # First‑time use – generate a random salt and start with empty store.
            self._salt = secrets.token_bytes(self._SALT_SIZE)
            self._key = _derive_key(master_password, self._salt)
            self._entries = {}
            return

        if self._salt is None:
            self._load_header()

        assert self._salt is not None  # for mypy

        key = _derive_key(master_password, self._salt)
        try:
            with self.store_path.open("rb") as f:
                f.seek(1 + self._SALT_SIZE)  # skip header
                encrypted_blob = f.read()
            plaintext = _decrypt(encrypted_blob, key)
            data = _load_json(plaintext)
            entries = data.get("entries", {})
            self._entries = {
                service: PasswordEntry.from_dict(entry_dict)
                for service, entry_dict in entries.items()
            }
            self._key = key
        except (CorruptedStoreError, AuthenticationError) as exc:
            raise AuthenticationError("Invalid master password or corrupted vault.") from exc
        except OSError as exc:
            raise PasswordManagerError(f"Failed to read vault file: {exc}") from exc

    def lock(self) -> None:
        """Erase the in‑memory key and entries."""
        self._key = None
        self._entries = {}
        self._salt = None

    def save(self) -> None:
        """Encrypt current entries and write them to disk."""
        self._ensure_unlocked()
        assert self._key is not None and self._salt is not None

        data = {"entries": {svc: entry.to_dict() for svc, entry in self._entries.items()}}
        plaintext = _dump_json(data)
        encrypted_blob = _encrypt(plaintext, self._key)

        try:
            with self.store_path.open("wb") as f:
                # Header: 1 byte version + 16 byte salt
                f.write(bytes([self._VERSION]) + self._salt + encrypted_blob)
        except OSError as exc:
            raise PasswordManagerError(f"Failed to write vault file: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Entry manipulation
    # ------------------------------------------------------------------- #

    def add_entry(self, service: str, username: str, password: str, notes: str = "") -> None:
        """
        Add a new password entry. Overwrites existing entry for the same service.

        Parameters
        ----------
        service: Identifier for the service (e.g., domain name).
        username: Username for the service.
        password: Password in plain text.
        notes: Optional notes.
        """
        self._ensure_unlocked()
        self._entries[service] = PasswordEntry(service, username, password, notes)

    def edit_entry(
        self,
        service: str,
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Edit an existing entry. Only provided fields are updated.

        Parameters
        ----------
        service: Service identifier of the entry to modify.
        username: New username (optional).
        password: New password (optional).
        notes: New notes (optional).

        Raises
        ------
        EntryNotFoundError: If the requested service does not exist.
        """
        self._ensure_unlocked()
        entry = self._entries.get(service)
        if entry is None:
            raise EntryNotFoundError(f"No entry for service: {service}")

        if username is not None:
            entry.username = username
        if password is not None:
            entry.password = password
        if notes is not None:
            entry.notes = notes

    def delete_entry(self, service: str) -> None:
        """
        Delete an entry identified by its service name.

        Raises
        ------
        EntryNotFoundError: If the entry does not exist.
        """
        self._ensure_unlocked()
        try:
            del self._entries[service]
        except KeyError as exc:
            raise EntryNotFoundError(f"No entry for service: {service}") from exc

    def get_entry(self, service: str) -> PasswordEntry:
        """
        Retrieve a copy of the entry for the given service.

        Raises
        ------
        EntryNotFoundError: If the entry does not exist.
        """
        self._ensure_unlocked()
        try:
            # Return a shallow copy to avoid accidental mutation without explicit edit.
            entry = self._entries[service]
            return PasswordEntry(**asdict(entry))
        except KeyError as exc:
            raise EntryNotFoundError(f"No entry for service: {service}") from exc

    def list_services(self) -> list[str]:
        """Return a sorted list of all stored service identifiers."""
        self._ensure_unlocked()
        return sorted(self._entries.keys())

    # ------------------------------------------------------------------- #
    # Password generation utilities
    # ------------------------------------------------------------------- #

    @staticmethod
    def generate_password(
        length: int = 16,
        *,
        uppercase: bool = True,
        lowercase: bool = True,
        digits: bool = True,
        punctuation: bool = True,
    ) -> str:
        """
        Generate a random password.

        Parameters
        ----------
        length: Desired length of the password (minimum 8).
        uppercase: Include uppercase ASCII letters.
        lowercase: Include lowercase ASCII letters.
        digits: Include decimal digits.
        punctuation: Include punctuation characters defined by ``string.punctuation``.

        Returns
        -------
        Randomly generated password string.

        Raises
        ------
        ValueError: If the character set is empty or length is < 8.
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters.")

        charset = ""
        if uppercase:
            charset += string.ascii_uppercase
        if lowercase:
            charset += string.ascii_lowercase
        if digits:
            charset += string.digits
        if punctuation:
            charset += string.punctuation

        if not charset:
            raise ValueError("At least one character class must be selected.")

        # Ensure the password contains at least one character from each selected class
        mandatory = []
        if uppercase:
            mandatory.append(secrets.choice(string.ascii_uppercase))
        if lowercase:
            mandatory.append(secrets.choice(string.ascii_lowercase))
        if digits:
            mandatory.append(secrets.choice(string.digits))
        if punctuation:
            mandatory.append(secrets.choice(string.punctuation))

        # Fill the rest of the password
        remaining = [secrets.choice(charset) for _ in range(length - len(mandatory))]
        password_chars = mandatory + remaining
        secrets.SystemRandom().shuffle(password_chars)
        return "".join(password_chars)

# --------------------------------------------------------------------------- #
# Simple command‑line interface (optional but helpful for quick testing)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import argparse
    import getpass

    def _print_entry(entry: PasswordEntry) -> None:
        print(f"Service : {entry.service}")
        print(f"Username: {entry.username}")
        print(f"Password: {entry.password}")
        if entry.notes:
            print(f"Notes   : {entry.notes}")

    parser = argparse.ArgumentParser(description="Secure password manager")
    parser.add_argument("vault", type=Path, help="Path to encrypted vault file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # unlock (implicit for every operation)
    # add
    parser_add = subparsers.add_parser("add", help="Add a new entry")
    parser_add.add_argument("service")
    parser_add.add_argument("username")
    parser_add.add_argument("password", nargs="?")
    parser_add.add_argument("--notes", default="")

    # edit
    parser_edit = subparsers.add_parser("edit", help="Edit existing entry")
    parser_edit.add_argument("service")
    parser_edit.add_argument("--username")
    parser_edit.add_argument("--password")
    parser_edit.add_argument("--notes")

    # delete
    parser_del = subparsers.add_parser("delete", help="Delete an entry")
    parser_del.add_argument("service")

    # get
    parser_get = subparsers.add_parser("get", help="Show an entry")
    parser_get.add_argument("service")

    # list
    subparsers.add_parser("list", help="List stored services")

    # gen
    parser_gen = subparsers.add_parser("gen", help="Generate a random password")
    parser_gen.add_argument("-l", "--length", type=int, default=16)
    parser_gen.add_argument("--no-uppercase", action="store_false", dest="uppercase")
    parser_gen.add_argument("--no-lowercase", action="store_false", dest="lowercase")
    parser_gen.add_argument("--no-digits", action="store_false", dest="digits")
    parser_gen.add_argument("--no-punct", action="store_false", dest="punctuation")

    args = parser.parse_args()

    master_pwd = getpass.getpass("Master password: ")
    pm = PasswordManager(args.vault)
    try:
        pm.unlock(master_pwd)
    except AuthenticationError as e:
        print(f"Error: {e}")
        exit(1)

    try:
        if args.command == "add":
            pwd = args.password or getpass.getpass("Password: ")
            pm.add_entry(args.service, args.username, pwd, notes=args.notes)
            pm.save()
            print("Entry added.")
        elif args.command == "edit":
            pm.edit_entry(
                args.service,
                username=args.username,
                password=args.password,
                notes=args.notes,
            )
            pm.save()
            print("Entry updated.")
        elif args.command == "delete":
            pm.delete_entry(args.service)
            pm.save()
            print("Entry deleted.")
        elif args.command == "get":
            entry = pm.get_entry(args.service)
            _print_entry(entry)
        elif args.command == "list":
            for svc in pm.list_services():
                print(svc)
        elif args.command == "gen":
            pwd = PasswordManager.generate_password(
                length=args.length,
                uppercase=args.uppercase,
                lowercase=args.lowercase,
                digits=args.digits,
                punctuation=args.punctuation,
            )
            print(pwd)
    finally:
        pm.lock()