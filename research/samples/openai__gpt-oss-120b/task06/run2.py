"""Password Manager Module.

This module provides a simple password manager with AES‑GCM encrypted storage.
It supports master‑password authentication, CRUD operations for credential
entries, and secure password generation.

Typical usage::

    from password_manager import PasswordManager, AuthenticationError

    pm = PasswordManager("my_vault.bin")
    try:
        pm.authenticate("my_master_password")
    except AuthenticationError as exc:
        print(f"Authentication failed: {exc}")
        raise

    pm.add_entry("example.com", "alice", "s3cr3t")
    entry = pm.get_entry("example.com")
    print(entry)

    pm.save_vault()
"""

from __future__ import annotations

import json
import os
import secrets
import string
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class AuthenticationError(Exception):
    """Raised when master‑password authentication fails."""


class EntryNotFoundError(Exception):
    """Raised when a requested credential entry does not exist."""


class VaultError(Exception):
    """General vault‑related errors (e.g., I/O, corruption)."""


def _derive_key(master_password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    """
    Derive a 256‑bit AES key from a master password using PBKDF2‑HMAC‑SHA256.

    Args:
        master_password: The user‑supplied master password.
        salt: Random salt (must be 16 bytes).
        iterations: Number of PBKDF2 iterations; higher = slower but more secure.

    Returns:
        A 32‑byte key suitable for AES‑GCM.
    """
    if not isinstance(master_password, str):
        raise TypeError("master_password must be a string")
    if not isinstance(salt, bytes):
        raise TypeError("salt must be bytes")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    return kdf.derive(master_password.encode("utf-8"))


@dataclass
class PasswordManager:
    """
    Core password manager handling encrypted storage and credential management.
    """

    vault_path: str
    _key: Optional[bytes] = field(init=False, default=None, repr=False)
    _entries: Dict[str, Dict[str, str]] = field(init=False, default_factory=dict)
    _salt: Optional[bytes] = field(init=False, default=None, repr=False)

    def authenticate(self, master_password: str) -> None:
        """
        Authenticate using the supplied master password.

        If the vault file does not exist, a new empty vault is created.

        Args:
            master_password: The master password.

        Raises:
            AuthenticationError: If decryption fails (wrong password or corrupted vault).
            VaultError: For I/O related problems.
        """
        if not isinstance(master_password, str):
            raise TypeError("master_password must be a string")

        if not os.path.exists(self.vault_path):
            # Initialise new vault
            self._salt = secrets.token_bytes(16)
            self._key = _derive_key(master_password, self._salt)
            self._entries = {}
            self._write_vault()
            return

        try:
            with open(self.vault_path, "rb") as f:
                raw = f.read()
        except OSError as exc:
            raise VaultError(f"Failed to read vault file: {exc}") from exc

        if len(raw) < 28:  # 16‑byte salt + 12‑byte nonce minimum
            raise VaultError("Vault file is corrupted or incomplete")

        self._salt = raw[:16]
        nonce = raw[16:28]
        ciphertext = raw[28:]

        try:
            self._key = _derive_key(master_password, self._salt)
            aesgcm = AESGCM(self._key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            self._entries = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise AuthenticationError("Invalid master password or corrupted vault") from exc

    def _encrypt(self, data: bytes) -> bytes:
        """
        Encrypt data using the derived AES‑GCM key.

        Args:
            data: Plaintext bytes to encrypt.

        Returns:
            Concatenated bytes: nonce (12) + ciphertext.

        Raises:
            VaultError: If encryption fails or key is not set.
        """
        if self._key is None:
            raise VaultError("Encryption key not initialised")
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def _write_vault(self) -> None:
        """
        Serialize and encrypt the current entries, then write to disk.

        Raises:
            VaultError: For I/O errors.
        """
        if self._salt is None or self._key is None:
            raise VaultError("Vault not initialised; call authenticate() first")
        try:
            plaintext = json.dumps(self._entries, separators=(",", ":")).encode("utf-8")
            encrypted = self._encrypt(plaintext)
            with open(self.vault_path, "wb") as f:
                f.write(self._salt + encrypted)
        except OSError as exc:
            raise VaultError(f"Failed to write vault file: {exc}") from exc

    def save_vault(self) -> None:
        """
        Public method to persist the current state to disk.

        Raises:
            VaultError: Propagates any underlying storage issues.
        """
        self._write_vault()

    def add_entry(self, site: str, username: str, password: str) -> None:
        """
        Add a new credential entry.

        Args:
            site: Identifier for the service (e.g., domain name).
            username: Account username.
            password: Account password.

        Raises:
            ValueError: If an entry for the site already exists.
        """
        if site in self._entries:
            raise ValueError(f"Entry for site '{site}' already exists")
        self._entries[site] = {"username": username, "password": password}

    def edit_entry(
        self,
        site: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """
        Edit an existing credential entry.

        Args:
            site: Identifier for the service to edit.
            username: New username (if provided).
            password: New password (if provided).

        Raises:
            EntryNotFoundError: If the site does not exist.
            ValueError: If neither username nor password is supplied.
        """
        if site not in self._entries:
            raise EntryNotFoundError(f"No entry found for site '{site}'")
        if username is None and password is None:
            raise ValueError("At least one of username or password must be provided")
        if username is not None:
            self._entries[site]["username"] = username
        if password is not None:
            self._entries[site]["password"] = password

    def delete_entry(self, site: str) -> None:
        """
        Delete a credential entry.

        Args:
            site: Identifier for the service to delete.

        Raises:
            EntryNotFoundError: If the site does not exist.
        """
        try:
            del self._entries[site]
        except KeyError as exc:
            raise EntryNotFoundError(f"No entry found for site '{site}'") from exc

    def get_entry(self, site: str) -> Dict[str, str]:
        """
        Retrieve a credential entry.

        Args:
            site: Identifier for the service.

        Returns:
            A dictionary with 'username' and 'password' keys.

        Raises:
            EntryNotFoundError: If the site does not exist.
        """
        try:
            return self._entries[site].copy()
        except KeyError as exc:
            raise EntryNotFoundError(f"No entry found for site '{site}'") from exc

    @staticmethod
    def generate_password(
        length: int = 16,
        use_symbols: bool = True,
        use_digits: bool = True,
        use_upper: bool = True,
        use_lower: bool = True,
    ) -> str:
        """
        Generate a cryptographically strong random password.

        Args:
            length: Desired password length (minimum 4).
            use_symbols: Include punctuation symbols.
            use_digits: Include numeric digits.
            use_upper: Include uppercase letters.
            use_lower: Include lowercase letters.

        Returns:
            A randomly generated password string.

        Raises:
            ValueError: If no character sets are selected or length is too short.
        """
        if length < 4:
            raise ValueError("Password length must be at least 4 characters")
        charset = ""
        if use_lower:
            charset += string.ascii_lowercase
        if use_upper:
            charset += string.ascii_uppercase
        if use_digits:
            charset += string.digits
        if use_symbols:
            charset += string.punctuation
        if not charset:
            raise ValueError("At least one character set must be enabled")

        # Ensure at least one character from each selected set
        password_chars = []
        if use_lower:
            password_chars.append(secrets.choice(string.ascii_lowercase))
        if use_upper:
            password_chars.append(secrets.choice(string.ascii_uppercase))
        if use_digits:
            password_chars.append(secrets.choice(string.digits))
        if use_symbols:
            password_chars.append(secrets.choice(string.punctuation))

        while len(password_chars) < length:
            password_chars.append(secrets.choice(charset))

        secrets.SystemRandom().shuffle(password_chars)
        return "".join(password_chars)