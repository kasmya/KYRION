"""
password_manager.py

A simple, file‑based password manager with AES‑GCM encryption.
Features:
- Master password authentication (derived key via PBKDF2‑HMAC‑SHA256)
- Add / edit / delete / retrieve entries
- Secure random password generation
- JSON‑based storage encrypted with a single AES‑GCM ciphertext

Only the Python standard library and the widely‑used ``cryptography`` package are required.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from secrets import choice, token_bytes, token_urlsafe
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class PasswordManagerError(Exception):
    """Base class for all password manager errors."""


class AuthenticationError(PasswordManagerError):
    """Raised when master‑password verification fails."""


class EntryNotFoundError(PasswordManagerError):
    """Raised when a requested entry does not exist."""


class StorageError(PasswordManagerError):
    """Raised for I/O or data‑corruption problems."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class Entry:
    """A single password entry."""

    username: str
    password: str
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        """Convert the entry to a JSON‑serialisable dict."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Entry":
        """Create an Entry from a dict."""
        return Entry(
            username=data["username"],
            password=data["password"],
            notes=data.get("notes", ""),
        )


# --------------------------------------------------------------------------- #
# Core manager
# --------------------------------------------------------------------------- #
class PasswordManager:
    """
    Manage encrypted storage of password entries.

    The storage file contains a JSON object with the following keys:
        - ``salt``   : base64‑encoded PBKDF2 salt
        - ``nonce``  : base64‑encoded AES‑GCM nonce
        - ``cipher`` : base64‑encoded ciphertext (JSON of entries)
    """

    _KDF_ITERATIONS = 200_000
    _AES_KEY_SIZE = 32  # 256‑bit
    _NONCE_SIZE = 12    # AES‑GCM recommended size

    def __init__(self, storage_path: str) -> None:
        """
        Initialise the manager.

        Args:
            storage_path: Path to the encrypted JSON storage file.
        """
        self.storage_path = Path(storage_path).expanduser().resolve()
        self._key: Optional[bytes] = None
        self._entries: Dict[str, Entry] = {}

    # ------------------------------------------------------------------- #
    # Key derivation & encryption helpers
    # ------------------------------------------------------------------- #
    @staticmethod
    def _derive_key(password: str, salt: bytes) -> bytes:
        """
        Derive a symmetric key from a password and salt using PBKDF2‑HMAC‑SHA256.

        Args:
            password: Master password.
            salt: Randomly generated salt.

        Returns:
            A 256‑bit key suitable for AES‑GCM.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=PasswordManager._AES_KEY_SIZE,
            salt=salt,
            iterations=PasswordManager._KDF_ITERATIONS,
        )
        return kdf.derive(password.encode("utf-8"))

    @staticmethod
    def _encrypt(key: bytes, plaintext: bytes) -> Dict[str, str]:
        """
        Encrypt plaintext with AES‑GCM.

        Returns a dict containing base64‑encoded ``nonce`` and ``ciphertext``.
        """
        nonce = token_bytes(PasswordManager._NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
        return {
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "cipher": base64.b64encode(ciphertext).decode("utf-8"),
        }

    @staticmethod
    def _decrypt(key: bytes, nonce_b64: str, cipher_b64: str) -> bytes:
        """
        Decrypt AES‑GCM ciphertext.

        Raises:
            AuthenticationError: If decryption fails (e.g., wrong key or tampered data).
        """
        try:
            nonce = base64.b64decode(nonce_b64)
            ciphertext = base64.b64decode(cipher_b64)
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        except Exception as exc:
            raise AuthenticationError("Failed to decrypt storage.") from exc

    # ------------------------------------------------------------------- #
    # Storage handling
    # ------------------------------------------------------------------- #
    def _load_storage(self, password: str) -> None:
        """
        Load and decrypt the storage file using the supplied master password.

        Populates ``self._entries`` and ``self._key`` on success.

        Raises:
            AuthenticationError: If password is incorrect.
            StorageError: For I/O or format problems.
        """
        if not self.storage_path.is_file():
            raise StorageError(f"Storage file '{self.storage_path}' does not exist.")

        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            salt = base64.b64decode(data["salt"])
            key = self._derive_key(password, salt)
            plaintext = self._decrypt(key, data["nonce"], data["cipher"])
            entries_raw = json.loads(plaintext.decode("utf-8"))
            self._entries = {
                name: Entry.from_dict(entry_dict)
                for name, entry_dict in entries_raw.items()
            }
            self._key = key
        except (KeyError, json.JSONDecodeError) as exc:
            raise StorageError("Corrupted storage format.") from exc
        except AuthenticationError:
            raise
        except Exception as exc:
            raise StorageError("Unable to read storage.") from exc

    def _save_storage(self) -> None:
        """
        Encrypt current entries and write to the storage file.

        Requires that ``self._key`` and ``self._key_salt`` are already set.

        Raises:
            StorageError: If writing fails.
        """
        if self._key is None:
            raise StorageError("Encryption key not initialised.")
        try:
            entries_dict = {name: entry.to_dict() for name, entry in self._entries.items()}
            plaintext = json.dumps(entries_dict, ensure_ascii=False).encode("utf-8")
            encrypted = self._encrypt(self._key, plaintext)

            # The salt used for key derivation is stored alongside the ciphertext.
            # For a new storage file we generate a new salt; otherwise reuse existing.
            if not self.storage_path.is_file():
                # First‑time creation: generate a fresh salt.
                salt = token_bytes(16)
                # Re‑derive key with this new salt for consistency.
                self._key = self._derive_key(self._master_password, salt)  # type: ignore
            else:
                # Load existing salt from file.
                with self.storage_path.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
                salt = base64.b64decode(existing["salt"])

            payload = {
                "salt": base64.b64encode(salt).decode("utf-8"),
                "nonce": encrypted["nonce"],
                "cipher": encrypted["cipher"],
            }
            with self.storage_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            raise StorageError("Failed to write encrypted storage.") from exc

    # ------------------------------------------------------------------- #
    # Authentication API
    # ------------------------------------------------------------------- #
    def initialize_storage(self, master_password: str) -> None:
        """
        Create a brand‑new encrypted storage file.

        Overwrites any existing file after confirmation.

        Args:
            master_password: Desired master password.

        Raises:
            StorageError: If the file cannot be written.
        """
        if self.storage_path.is_file():
            raise StorageError("Storage already exists; use 'reset_storage' to overwrite.")
        self._master_password = master_password  # Temporary attribute for key derivation
        self._entries = {}
        self._key = self._derive_key(master_password, token_bytes(16))
        self._save_storage()
        del self._master_password  # Remove temporary attribute

    def reset_storage(self, master_password: str) -> None:
        """
        Delete existing storage and create a fresh one.

        Use with extreme caution – all data will be lost.

        Args:
            master_password: New master password.

        Raises:
            StorageError: If deletion or creation fails.
        """
        try:
            if self.storage_path.is_file():
                self.storage_path.unlink()
        except Exception as exc:
            raise StorageError("Failed to delete existing storage.") from exc
        self.initialize_storage(master_password)

    def authenticate(self, master_password: str) -> None:
        """
        Verify the master password and load entries into memory.

        Args:
            master_password: The password to verify.

        Raises:
            AuthenticationError: If password is incorrect.
            StorageError: If loading fails.
        """
        self._load_storage(master_password)

    # ------------------------------------------------------------------- #
    # Entry management
    # ------------------------------------------------------------------- #
    def add_entry(self, name: str, username: str, password: str, notes: str = "") -> None:
        """
        Add a new entry.

        Args:
            name: Identifier for the entry (must be unique).
            username: Username for the service.
            password: Password for the service.
            notes: Optional free‑form notes.

        Raises:
            ValueError: If an entry with ``name`` already exists.
            StorageError: If saving fails.
        """
        if name in self._entries:
            raise ValueError(f"Entry '{name}' already exists.")
        self._entries[name] = Entry(username=username, password=password, notes=notes)
        self._save_storage()

    def edit_entry(
        self,
        name: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Edit an existing entry.

        Only supplied fields are updated.

        Args:
            name: Entry identifier.
            username: New username (optional).
            password: New password (optional).
            notes: New notes (optional).

        Raises:
            EntryNotFoundError: If ``name`` does not exist.
            StorageError: If saving fails.
        """
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found.")
        entry = self._entries[name]
        if username is not None:
            entry.username = username
        if password is not None:
            entry.password = password
        if notes is not None:
            entry.notes = notes
        self._save_storage()

    def delete_entry(self, name: str) -> None:
        """
        Remove an entry.

        Args:
            name: Entry identifier.

        Raises:
            EntryNotFoundError: If ``name`` does not exist.
            StorageError: If saving fails.
        """
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found.")
        del self._entries[name]
        self._save_storage()

    def get_entry(self, name: str) -> Entry:
        """
        Retrieve a copy of an entry.

        Args:
            name: Entry identifier.

        Returns:
            An ``Entry`` instance.

        Raises:
            EntryNotFoundError: If ``name`` does not exist.
        """
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found.")
        # Return a shallow copy to prevent accidental mutation.
        entry = self._entries[name]
        return Entry(username=entry.username, password=entry.password, notes=entry.notes)

    def list_entries(self) -> List[str]:
        """
        List all stored entry names.

        Returns:
            Sorted list of entry identifiers.
        """
        return sorted(self._entries.keys())

    # ------------------------------------------------------------------- #
    # Password generation
    # ------------------------------------------------------------------- #
    @staticmethod
    def generate_password(
        length: int = 16,
        use_upper: bool = True,
        use_lower: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
    ) -> str:
        """
        Generate a random password.

        Args:
            length: Desired length (minimum 8).
            use_upper: Include uppercase letters.
            use_lower: Include lowercase letters.
            use_digits: Include decimal digits.
            use_symbols: Include punctuation symbols.

        Returns:
            A securely generated password string.

        Raises:
            ValueError: If no character sets are selected or length is too short.
        """
        if length < 8:
            raise ValueError("Password length should be at least 8 characters.")
        charset = ""
        if use_upper:
            charset += "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if use_lower:
            charset += "abcdefghijklmnopqrstuvwxyz"
        if use_digits:
            charset += "0123456789"
        if use_symbols:
            charset += "!@#$%^&*()-_=+[]{}|;:,.<>?/`~"
        if not charset:
            raise ValueError("At least one character set must be selected.")
        return "".join(choice(charset) for _ in range(length))


# --------------------------------------------------------------------------- #
# Convenience functions for command‑line usage (optional)
# --------------------------------------------------------------------------- #
def _demo() -> None:
    """
    Simple demonstration when the module is executed directly.
    """
    import getpass

    storage = PasswordManager("~/.pwmanager_store.json")
    if not storage.storage_path.is_file():
        print("No existing storage found. Creating new one.")
        pwd = getpass.getpass("Set master password: ")
        storage.initialize_storage(pwd)
    else:
        pwd = getpass.getpass("Master password: ")
        try:
            storage.authenticate(pwd)
        except AuthenticationError as e:
            print(f"Authentication failed: {e}")
            return

    while True:
        print("\nOptions: [a]dd, [e]dit, [d]elete, [l]ist, [g]et, [p]assword gen, [q]uit")
        choice_opt = input("Select: ").strip().lower()
        if choice_opt == "q":
            break
        elif choice_opt == "a":
            name = input("Entry name: ").strip()
            username = input("Username: ").strip()
            password = getpass.getpass("Password: ")
            notes = input("Notes (optional): ").strip()
            try:
                storage.add_entry(name, username, password, notes)
                print("Entry added.")
            except Exception as exc:
                print(f"Error: {exc}")
        elif choice_opt == "e":
            name = input("Entry name to edit: ").strip()
            username = input("New username (leave empty to keep): ").strip() or None
            password = getpass.getpass("New password (leave empty to keep): ").strip() or None
            notes = input("New notes (leave empty to keep): ").strip() or None
            try:
                storage.edit_entry(name, username, password, notes)
                print("Entry updated.")
            except Exception as exc:
                print(f"Error: {exc}")
        elif choice_opt == "d":
            name = input("Entry name to delete: ").strip()
            try:
                storage.delete_entry(name)
                print("Entry deleted.")
            except Exception as exc:
                print(f"Error: {exc}")
        elif choice_opt == "l":
            print("Stored entries:")
            for n in storage.list_entries():
                print(f" - {n}")
        elif choice_opt == "g":
            name = input("Entry name to retrieve: ").strip()
            try:
                entry = storage.get_entry(name)
                print(f"Username: {entry.username}")
                print(f"Password: {entry.password}")
                print(f"Notes: {entry.notes}")
            except Exception as exc:
                print(f"Error: {exc}")
        elif choice_opt == "p":
            try:
                length = int(input("Length (default 16): ").strip() or "16")
                pwd = storage.generate_password(length=length)
                print(f"Generated password: {pwd}")
            except Exception as exc:
                print(f"Error: {exc}")
        else:
            print("Unknown option.")


if __name__ == "__main__":
    _demo()