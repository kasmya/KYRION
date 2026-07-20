"""
Password Manager Module
-----------------------

Provides a `PasswordManager` class for securely storing, retrieving,
and managing passwords protected by a master password.

Features
~~~~~~~~
- AES‑256‑GCM encryption with authenticated data.
- PBKDF2‑HMAC‑SHA256 key derivation with per‑vault random salt.
- Add, edit, delete, and retrieve password entries.
- Secure random password generation.
- Type hints, detailed docstrings, and robust error handling.

Dependencies
~~~~~~~~~~~~
- cryptography (install with `pip install cryptography`)

Example
~~~~~~~
>>> from password_manager import PasswordManager
>>> vault = PasswordManager('vault.dat')
>>> vault.create_vault('my_master_password')
>>> vault.unlock('my_master_password')
>>> vault.add_entry('example.com', 'user', 'secret')
>>> vault.get_entry('example.com')
{'username': 'user', 'password': 'secret'}
>>> vault.lock()
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class PasswordManagerError(Exception):
    """Base class for all password manager errors."""


class AuthenticationError(PasswordManagerError):
    """Raised when master password authentication fails."""


class VaultLockedError(PasswordManagerError):
    """Raised when an operation is attempted on a locked vault."""


@dataclass
class _VaultData:
    """Internal representation of the decrypted vault."""
    entries: Dict[str, Dict[str, str]] = field(default_factory=dict)


class PasswordManager:
    """
    Secure password manager using AES‑256‑GCM encryption.

    Parameters
    ----------
    file_path : str
        Path to the encrypted vault file.
    """

    _KDF_ITERATIONS: int = 200_000
    _SALT_SIZE: int = 16
    _NONCE_SIZE: int = 12
    _KEY_SIZE: int = 32  # 256‑bit

    def __init__(self, file_path: str) -> None:
        self._file_path: str = file_path
        self._key: Optional[bytes] = None
        self._vault: Optional[_VaultData] = None
        self._nonce: Optional[bytes] = None

    # --------------------------------------------------------------------- #
    # Vault lifecycle
    # --------------------------------------------------------------------- #
    def create_vault(self, master_password: str) -> None:
        """
        Initialise a new vault encrypted with ``master_password``.

        If a vault file already exists it will be overwritten.
        """
        if os.path.exists(self._file_path):
            os.remove(self._file_path)

        salt = secrets.token_bytes(self._SALT_SIZE)
        self._key = self._derive_key(master_password.encode(), salt)
        self._vault = _VaultData()
        self._nonce = secrets.token_bytes(self._NONCE_SIZE)
        self._write_encrypted(salt)

    def unlock(self, master_password: str) -> None:
        """
        Unlock the vault using ``master_password``.

        Raises
        ------
        AuthenticationError
            If the password cannot decrypt the vault.
        FileNotFoundError
            If the vault file does not exist.
        """
        if not os.path.isfile(self._file_path):
            raise FileNotFoundError(f"Vault file not found: {self._file_path}")

        with open(self._file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        try:
            salt = base64.b64decode(data["salt"])
            self._nonce = base64.b64decode(data["nonce"])
            ciphertext = base64.b64decode(data["ciphertext"])
        except (KeyError, ValueError) as exc:
            raise PasswordManagerError("Corrupted vault file.") from exc

        self._key = self._derive_key(master_password.encode(), salt)

        try:
            plain = AESGCM(self._key).decrypt(self._nonce, ciphertext, None)
            vault_dict = json.loads(plain.decode("utf-8"))
            self._vault = _VaultData(entries=vault_dict.get("entries", {}))
        except Exception as exc:
            raise AuthenticationError("Invalid master password or corrupted vault.") from exc

    def lock(self) -> None:
        """
        Encrypt and persist the vault, then clear sensitive data from memory.
        """
        if self._key is None or self._vault is None or self._nonce is None:
            raise VaultLockedError("Vault is not unlocked.")

        self._write_encrypted()
        # Zero‑out sensitive attributes
        self._key = None
        self._vault = None
        self._nonce = None

    # --------------------------------------------------------------------- #
    # Entry management
    # --------------------------------------------------------------------- #
    def add_entry(self, site: str, username: str, password: str) -> None:
        """
        Add a new entry. Overwrites existing entry with the same ``site``.
        """
        self._require_unlocked()
        self._vault.entries[site] = {"username": username, "password": password}

    def edit_entry(self, site: str, username: Optional[str] = None,
                   password: Optional[str] = None) -> None:
        """
        Edit an existing entry.

        Parameters
        ----------
        site : str
            Identifier of the entry.
        username : Optional[str]
            New username (if provided).
        password : Optional[str]
            New password (if provided).

        Raises
        ------
        KeyError
            If ``site`` does not exist.
        """
        self._require_unlocked()
        if site not in self._vault.entries:
            raise KeyError(f"No entry for site: {site}")

        entry = self._vault.entries[site]
        if username is not None:
            entry["username"] = username
        if password is not None:
            entry["password"] = password

    def delete_entry(self, site: str) -> None:
        """
        Remove an entry.

        Raises
        ------
        KeyError
            If ``site`` does not exist.
        """
        self._require_unlocked()
        try:
            del self._vault.entries[site]
        except KeyError as exc:
            raise KeyError(f"No entry for site: {site}") from exc

    def get_entry(self, site: str) -> Dict[str, str]:
        """
        Retrieve an entry.

        Returns
        -------
        dict
            ``{'username': ..., 'password': ...}``

        Raises
        ------
        KeyError
            If ``site`` does not exist.
        """
        self._require_unlocked()
        try:
            return self._vault.entries[site].copy()
        except KeyError as exc:
            raise KeyError(f"No entry for site: {site}") from exc

    def list_sites(self) -> list[str]:
        """Return a list of all site identifiers stored in the vault."""
        self._require_unlocked()
        return list(self._vault.entries.keys())

    # --------------------------------------------------------------------- #
    # Password generation
    # --------------------------------------------------------------------- #
    @staticmethod
    def generate_password(length: int = 16,
                          use_upper: bool = True,
                          use_digits: bool = True,
                          use_symbols: bool = True) -> str:
        """
        Generate a cryptographically‑secure random password.

        Parameters
        ----------
        length : int
            Desired password length (minimum 8).
        use_upper : bool
            Include uppercase letters.
        use_digits : bool
            Include digits.
        use_symbols : bool
            Include punctuation symbols.

        Returns
        -------
        str
            Generated password.

        Raises
        ------
        ValueError
            If ``length`` is less than 8.
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters.")

        charset = string.ascii_lowercase
        if use_upper:
            charset += string.ascii_uppercase
        if use_digits:
            charset += string.digits
        if use_symbols:
            charset += string.punctuation

        return "".join(secrets.choice(charset) for _ in range(length))

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _derive_key(self, password: bytes, salt: bytes) -> bytes:
        """Derive a symmetric key from ``password`` and ``salt`` using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self._KEY_SIZE,
            salt=salt,
            iterations=self._KDF_ITERATIONS,
        )
        return kdf.derive(password)

    def _write_encrypted(self, salt: Optional[bytes] = None) -> None:
        """Encrypt the current vault and write to ``self._file_path``."""
        if self._key is None or self._vault is None:
            raise VaultLockedError("Vault is not unlocked.")

        # Serialize vault data
        plain_dict: Dict[str, Any] = {"entries": self._vault.entries}
        plain_bytes = json.dumps(plain_dict, separators=(",", ":")).encode("utf-8")

        # Encrypt
        aesgcm = AESGCM(self._key)
        if self._nonce is None:
            self._nonce = secrets.token_bytes(self._NONCE_SIZE)
        ciphertext = aesgcm.encrypt(self._nonce, plain_bytes, None)

        # Store with base64 encoding for JSON compatibility
        if salt is None:
            # When locking an existing vault we reuse the original salt
            # stored in the file. Read it back if needed.
            with open(self._file_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            salt = base64.b64decode(existing["salt"])

        payload = {
            "salt": base64.b64encode(salt).decode("utf-8"),
            "nonce": base64.b64encode(self._nonce).decode("utf-8"),
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        }

        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

    def _require_unlocked(self) -> None:
        """Raise ``VaultLockedError`` if the vault is not currently unlocked."""
        if self._vault is None:
            raise VaultLockedError("Vault must be unlocked to perform this operation.")