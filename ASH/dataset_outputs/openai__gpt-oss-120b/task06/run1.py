"""Password manager module.

Provides a simple password manager with AES‑GCM encrypted storage, master‑password
authentication, entry CRUD operations, and secure password generation.

The storage format (JSON) contains a base64‑encoded salt, nonce, and ciphertext.
Only the `cryptography` package from PyPI is required in addition to the Python
standard library.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import string
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class PasswordManagerError(Exception):
    """Base class for all password‑manager‑related errors."""


class AuthenticationError(PasswordManagerError):
    """Raised when the master password cannot decrypt the storage."""


class EntryNotFoundError(PasswordManagerError):
    """Raised when a requested entry does not exist."""


class StorageError(PasswordManagerError):
    """Raised for I/O or data‑format problems with the storage file."""


# --------------------------------------------------------------------------- #
# Helper dataclass for the encrypted blob
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _EncryptedBlob:
    """Container for the encrypted storage payload."""
    salt: bytes
    nonce: bytes
    ciphertext: bytes

    def to_json(self) -> str:
        """Serialize the blob to a JSON string."""
        payload = {
            "salt": base64.b64encode(self.salt).decode("utf-8"),
            "nonce": base64.b64encode(self.nonce).decode("utf-8"),
            "data": base64.b64encode(self.ciphertext).decode("utf-8"),
        }
        return json.dumps(payload)

    @staticmethod
    def from_json(text: str) -> "_EncryptedBlob":
        """Deserialize a JSON string back into an :class:`_EncryptedBlob`."""
        try:
            payload = json.loads(text)
            salt = base64.b64decode(payload["salt"])
            nonce = base64.b64decode(payload["nonce"])
            ciphertext = base64.b64decode(payload["data"])
            return _EncryptedBlob(salt=salt, nonce=nonce, ciphertext=ciphertext)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise StorageError("Corrupted storage format") from exc


# --------------------------------------------------------------------------- #
# Core password manager
# --------------------------------------------------------------------------- #

class PasswordManager:
    """
    Password manager handling encrypted storage and entry operations.

    Parameters
    ----------
    storage_path : str
        Path to the JSON file that holds the encrypted data.
    master_password : str
        Master password used to derive the encryption key.
    create_if_missing : bool, optional
        If ``True`` (default), a new storage file is created when none exists.
    """

    _KDF_ITERATIONS = 200_000
    _KEY_SIZE = 32  # 256‑bit AES key

    def __init__(
        self,
        storage_path: str,
        master_password: str,
        *,
        create_if_missing: bool = True,
    ) -> None:
        self._storage_path = storage_path
        self._master_password = master_password.encode("utf-8")
        self._entries: MutableMapping[str, Mapping[str, str]] = {}

        if not os.path.exists(self._storage_path):
            if not create_if_missing:
                raise StorageError(f"Storage file '{self._storage_path}' not found")
            # Initialise a fresh empty store
            self._save_encrypted({})
        else:
            self._load_encrypted()

    # ------------------------------------------------------------------- #
    # Key derivation
    # ------------------------------------------------------------------- #

    @staticmethod
    def _derive_key(
        password: bytes,
        salt: bytes,
        iterations: int = _KDF_ITERATIONS,
        length: int = _KEY_SIZE,
    ) -> bytes:
        """
        Derive a cryptographic key from ``password`` and ``salt`` using PBKDF2‑HMAC‑SHA256.

        Raises
        ------
        ValueError
            If the KDF parameters are invalid.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=iterations,
        )
        return kdf.derive(password)

    # ------------------------------------------------------------------- #
    # Encryption / decryption helpers
    # ------------------------------------------------------------------- #

    def _encrypt_data(self, data: Mapping[str, Any]) -> _EncryptedBlob:
        """
        Encrypt ``data`` using AES‑GCM and return an :class:`_EncryptedBlob`.

        The function generates a fresh 16‑byte salt and 12‑byte nonce.
        """
        salt = secrets.token_bytes(16)
        key = self._derive_key(self._master_password, salt)
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(12)

        serialized = json.dumps(data, separators=(",", ":")).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, serialized, associated_data=None)
        return _EncryptedBlob(salt=salt, nonce=nonce, ciphertext=ciphertext)

    def _decrypt_blob(self, blob: _EncryptedBlob) -> Mapping[str, Any]:
        """
        Decrypt an :class:`_EncryptedBlob` and return the original mapping.

        Raises
        ------
        AuthenticationError
            If decryption fails (e.g., wrong master password).
        StorageError
            If the decrypted payload cannot be parsed as JSON.
        """
        key = self._derive_key(self._master_password, blob.salt)
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(blob.nonce, blob.ciphertext, associated_data=None)
        except InvalidTag as exc:
            raise AuthenticationError("Invalid master password or corrupted data") from exc

        try:
            return json.loads(plaintext.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError("Decrypted data is not valid JSON") from exc

    # ------------------------------------------------------------------- #
    # Persistence
    # ------------------------------------------------------------------- #

    def _load_encrypted(self) -> None:
        """Load and decrypt the storage file into the internal ``_entries`` dict."""
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                blob = _EncryptedBlob.from_json(f.read())
        except OSError as exc:
            raise StorageError(f"Failed to read storage file: {exc}") from exc

        decrypted = self._decrypt_blob(blob)
        if not isinstance(decrypted, dict):
            raise StorageError("Storage payload is not a dictionary")
        # Ensure all values are dicts with expected fields
        self._entries = {k: v for k, v in decrypted.items() if isinstance(v, dict)}

    def _save_encrypted(self, data: Mapping[str, Any]) -> None:
        """Encrypt ``data`` and write it to the storage file."""
        blob = self._encrypt_data(data)
        try:
            with open(self._storage_path, "w", encoding="utf-8") as f:
                f.write(blob.to_json())
        except OSError as exc:
            raise StorageError(f"Failed to write storage file: {exc}") from exc

    def _commit(self) -> None:
        """Write the current in‑memory entries to disk."""
        self._save_encrypted(self._entries)

    # ------------------------------------------------------------------- #
    # Entry CRUD operations
    # ------------------------------------------------------------------- #

    def add_entry(self, service: str, username: str, password: str) -> None:
        """
        Add a new entry for ``service``.

        If an entry already exists for the service, ``AuthenticationError`` is raised.

        Raises
        ------
        PasswordManagerError
            If the entry cannot be added.
        """
        if service in self._entries:
            raise PasswordManagerError(f"Entry for service '{service}' already exists")
        self._entries[service] = {"username": username, "password": password}
        self._commit()

    def edit_entry(
        self,
        service: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """
        Edit an existing entry.

        Parameters
        ----------
        service : str
            Identifier of the entry to modify.
        username : str, optional
            New username. If ``None``, the username is left unchanged.
        password : str, optional
            New password. If ``None``, the password is left unchanged.

        Raises
        ------
        EntryNotFoundError
            If ``service`` does not exist.
        """
        if service not in self._entries:
            raise EntryNotFoundError(f"No entry for service '{service}'")
        entry = dict(self._entries[service])  # copy
        if username is not None:
            entry["username"] = username
        if password is not None:
            entry["password"] = password
        self._entries[service] = entry
        self._commit()

    def delete_entry(self, service: str) -> None:
        """
        Remove the entry for ``service`` from storage.

        Raises
        ------
        EntryNotFoundError
            If ``service`` does not exist.
        """
        if service not in self._entries:
            raise EntryNotFoundError(f"No entry for service '{service}'")
        del self._entries[service]
        self._commit()

    def get_entry(self, service: str) -> Dict[str, str]:
        """
        Retrieve the entry for ``service``.

        Returns
        -------
        dict
            Mapping with keys ``username`` and ``password``.

        Raises
        ------
        EntryNotFoundError
            If ``service`` does not exist.
        """
        if service not in self._entries:
            raise EntryNotFoundError(f"No entry for service '{service}'")
        return dict(self._entries[service])

    def list_services(self) -> List[str]:
        """
        Return a list of all stored service identifiers.

        Returns
        -------
        list of str
        """
        return sorted(self._entries.keys())

    # ------------------------------------------------------------------- #
    # Password generation
    # ------------------------------------------------------------------- #

    @staticmethod
    def generate_password(
        length: int = 16,
        *,
        use_upper: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
    ) -> str:
        """
        Generate a cryptographically secure random password.

        Parameters
        ----------
        length : int, optional
            Desired password length (minimum 8). Default is 16.
        use_upper : bool, optional
            Include uppercase ASCII letters. Default is ``True``.
        use_digits : bool, optional
            Include decimal digits. Default is ``True``.
        use_symbols : bool, optional
            Include punctuation symbols. Default is ``True``.

        Returns
        -------
        str
            The generated password.

        Raises
        ------
        ValueError
            If ``length`` is less than 8 or if the character set becomes empty.
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters")

        alphabet = list(string.ascii_lowercase)
        if use_upper:
            alphabet += list(string.ascii_uppercase)
        if use_digits:
            alphabet += list(string.digits)
        if use_symbols:
            alphabet += list(string.punctuation)

        if not alphabet:
            raise ValueError("Character set for password generation is empty")

        return "".join(secrets.choice(alphabet) for _ in range(length))


__all__ = [
    "PasswordManager",
    "AuthenticationError",
    "EntryNotFoundError",
    "StorageError",
    "PasswordManagerError",
]