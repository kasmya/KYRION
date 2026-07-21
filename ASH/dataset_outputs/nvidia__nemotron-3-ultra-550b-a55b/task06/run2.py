"""
Password Manager Module

This module provides a secure password manager with AES-256-GCM encrypted storage,
master password authentication, and password generation capabilities.

Security Features:
- PBKDF2-HMAC-SHA256 with 100,000 iterations for key derivation
- AES-256-GCM for authenticated encryption
- Constant-time master password verification
- Secure random generation for salts, nonces, and passwords
- Memory-safe handling of sensitive data

Usage:
    manager = PasswordManager("master_password")
    manager.add_entry("example.com", "user", "password123")
    entry = manager.get_entry("example.com", "user")
    manager.save("vault.enc")
"""

import json
import os
import secrets
import string
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


# Constants
SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32  # 256 bits
PBKDF2_ITERATIONS = 100_000
VAULT_VERSION = 1


class PasswordManagerError(Exception):
    """Base exception for password manager errors."""
    pass


class MasterPasswordError(PasswordManagerError):
    """Raised when master password verification fails."""
    pass


class VaultError(PasswordManagerError):
    """Raised when vault operations fail."""
    pass


class EntryNotFoundError(PasswordManagerError):
    """Raised when an entry is not found."""
    pass


class EntryExistsError(PasswordManagerError):
    """Raised when attempting to add a duplicate entry."""
    pass


@dataclass
class PasswordEntry:
    """Represents a single password entry."""
    service: str
    username: str
    password: str
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        """Convert entry to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "PasswordEntry":
        """Create entry from dictionary."""
        return cls(
            service=data["service"],
            username=data["username"],
            password=data["password"],
            notes=data.get("notes", "")
        )


def derive_key(master_password: str, salt: bytes) -> bytes:
    """
    Derive encryption key from master password using PBKDF2-HMAC-SHA256.

    Args:
        master_password: The master password string.
        salt: Cryptographic salt bytes.

    Returns:
        Derived 32-byte key.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(master_password.encode("utf-8"))


def verify_key(master_password: str, salt: bytes, expected_key: bytes) -> bool:
    """
    Verify master password against derived key using constant-time comparison.

    Args:
        master_password: The master password string.
        salt: Cryptographic salt bytes.
        expected_key: Expected derived key bytes.

    Returns:
        True if password matches, False otherwise.
    """
    derived_key = derive_key(master_password, salt)
    return secrets.compare_digest(derived_key, expected_key)


def encrypt_data(data: bytes, key: bytes) -> tuple[bytes, bytes]:
    """
    Encrypt data using AES-256-GCM.

    Args:
        data: Plaintext data to encrypt.
        key: 32-byte encryption key.

    Returns:
        Tuple of (nonce, ciphertext_with_tag).
    """
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce, ciphertext


def decrypt_data(nonce: bytes, ciphertext: bytes, key: bytes) -> bytes:
    """
    Decrypt data using AES-256-GCM.

    Args:
        nonce: 12-byte nonce.
        ciphertext: Ciphertext with authentication tag.
        key: 32-byte encryption key.

    Returns:
        Decrypted plaintext data.

    Raises:
        InvalidTag: If authentication tag verification fails.
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def generate_secure_password(
    length: int = 16,
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    exclude_ambiguous: bool = True
) -> str:
    """
    Generate a cryptographically secure random password.

    Args:
        length: Password length (minimum 8).
        use_uppercase: Include uppercase letters.
        use_lowercase: Include lowercase letters.
        use_digits: Include digits.
        use_symbols: Include symbols.
        exclude_ambiguous: Exclude ambiguous characters (l, I, 1, 0, O, etc.).

    Returns:
        Generated password string.

    Raises:
        ValueError: If length < 8 or no character sets selected.
    """
    if length < 8:
        raise ValueError("Password length must be at least 8 characters")

    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    if exclude_ambiguous:
        ambiguous = "lI10Oo"
        uppercase = "".join(c for c in uppercase if c not in ambiguous)
        lowercase = "".join(c for c in lowercase if c not in ambiguous)
        digits = "".join(c for c in digits if c not in ambiguous)
        symbols = "".join(c for c in symbols if c not in ambiguous)

    charset = ""
    if use_uppercase:
        charset += uppercase
    if use_lowercase:
        charset += lowercase
    if use_digits:
        charset += digits
    if use_symbols:
        charset += symbols

    if not charset:
        raise ValueError("At least one character set must be selected")

    # Ensure at least one character from each selected set
    password_chars = []
    if use_uppercase:
        password_chars.append(secrets.choice(uppercase))
    if use_lowercase:
        password_chars.append(secrets.choice(lowercase))
    if use_digits:
        password_chars.append(secrets.choice(digits))
    if use_symbols:
        password_chars.append(secrets.choice(symbols))

    # Fill remaining length
    remaining = length - len(password_chars)
    password_chars.extend(secrets.choice(charset) for _ in range(remaining))

    # Shuffle to avoid predictable pattern
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


class PasswordManager:
    """
    Secure password manager with encrypted storage.

    Attributes:
        _entries: List of password entries.
        _master_key: Derived encryption key (None if locked).
        _salt: Salt used for key derivation.
        _verified: Whether master password has been verified.
    """

    def __init__(self, master_password: Optional[str] = None) -> None:
        """
        Initialize password manager.

        Args:
            master_password: Optional master password to unlock immediately.
        """
        self._entries: List[PasswordEntry] = []
        self._master_key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._verified = False

        if master_password is not None:
            self.unlock(master_password)

    def _ensure_unlocked(self) -> None:
        """Ensure vault is unlocked before operations."""
        if not self._verified or self._master_key is None:
            raise VaultError("Vault is locked. Call unlock() first.")

    def _generate_new_salt(self) -> bytes:
        """Generate new cryptographic salt."""
        return secrets.token_bytes(SALT_SIZE)

    def unlock(self, master_password: str) -> None:
        """
        Unlock vault with master password (for new vault).

        Args:
            master_password: Master password string.

        Raises:
            ValueError: If master password is empty.
        """
        if not master_password:
            raise ValueError("Master password cannot be empty")

        self._salt = self._generate_new_salt()
        self._master_key = derive_key(master_password, self._salt)
        self._verified = True
        self._entries = []

    def lock(self) -> None:
        """Lock vault and clear sensitive data from memory."""
        self._master_key = None
        self._verified = False
        self._entries = []

    def is_locked(self) -> bool:
        """Check if vault is locked."""
        return not self._verified

    def add_entry(
        self,
        service: str,
        username: str,
        password: str,
        notes: str = ""
    ) -> None:
        """
        Add a new password entry.

        Args:
            service: Service name (e.g., "github.com").
            username: Username or email.
            password: Password string.
            notes: Optional notes.

        Raises:
            VaultError: If vault is locked.
            EntryExistsError: If entry already exists.
            ValueError: If service or username is empty.
        """
        self._ensure_unlocked()

        if not service or not username:
            raise ValueError("Service and username cannot be empty")

        # Check for duplicate
        for entry in self._entries:
            if entry.service == service and entry.username == username:
                raise EntryExistsError(f"Entry for {service}/{username} already exists")

        entry = PasswordEntry(service, username, password, notes)
        self._entries.append(entry)

    def edit_entry(
        self,
        service: str,
        username: str,
        new_password: Optional[str] = None,
        new_notes: Optional[str] = None
    ) -> None:
        """
        Edit an existing password entry.

        Args:
            service: Service name.
            username: Username.
            new_password: New password (optional).
            new_notes: New notes (optional).

        Raises:
            VaultError: If vault is locked.
            EntryNotFoundError: If entry not found.
            ValueError: If service or username is empty.
        """
        self._ensure_unlocked()

        if not service or not username:
            raise ValueError("Service and username cannot be empty")

        for entry in self._entries:
            if entry.service == service and entry.username == username:
                if new_password is not None:
                    entry.password = new_password
                if new_notes is not None:
                    entry.notes = new_notes
                return

        raise EntryNotFoundError(f"Entry for {service}/{username} not found")

    def delete_entry(self, service: str, username: str) -> None:
        """
        Delete a password entry.

        Args:
            service: Service name.
            username: Username.

        Raises:
            VaultError: If vault is locked.
            EntryNotFoundError: If entry not found.
            ValueError: If service or username is empty.
        """
        self._ensure_unlocked()

        if not service or not username:
            raise ValueError("Service and username cannot be empty")

        for i, entry in enumerate(self._entries):
            if entry.service == service and entry.username == username:
                del self._entries[i]
                return

        raise EntryNotFoundError(f"Entry for {service}/{username} not found")

    def get_entry(self, service: str, username: str) -> PasswordEntry:
        """
        Get a password entry.

        Args:
            service: Service name.
            username: Username.

        Returns:
            PasswordEntry object.

        Raises:
            VaultError: If vault is locked.
            EntryNotFoundError: If entry not found.
            ValueError: If service or username is empty.
        """
        self._ensure_unlocked()

        if not service or not username:
            raise ValueError("Service and username cannot be empty")

        for entry in self._entries:
            if entry.service == service and entry.username == username:
                return entry

        raise EntryNotFoundError(f"Entry for {service}/{username} not found")

    def list_entries(self) -> List[PasswordEntry]:
        """
        List all password entries (without passwords for security).

        Returns:
            List of PasswordEntry objects with passwords masked.

        Raises:
            VaultError: If vault is locked.
        """
        self._ensure_unlocked()
        # Return copies with masked passwords for security
        return [
            PasswordEntry(e.service, e.username, "***MASKED***", e.notes)
            for e in self._entries
        ]

    def get_all_entries(self) -> List[PasswordEntry]:
        """
        Get all entries with actual passwords (use with caution).

        Returns:
            List of all PasswordEntry objects.

        Raises:
            VaultError: If vault is locked.
        """
        self._ensure_unlocked()
        return self._entries.copy()

    def save(self, filepath: str | Path) -> None:
        """
        Save encrypted vault to file.

        Args:
            filepath: Path to vault file.

        Raises:
            VaultError: If vault is locked or save fails.
        """
        self._ensure_unlocked()

        if self._salt is None or self._master_key is None:
            raise VaultError("Vault not properly initialized")

        try:
            # Prepare vault data
            vault_data = {
                "version": VAULT_VERSION,
                "entries": [entry.to_dict() for entry in self._entries]
            }
            plaintext = json.dumps(vault_data, separators=(",", ":")).encode("utf-8")

            # Encrypt
            nonce, ciphertext = encrypt_data(plaintext, self._master_key)

            # Write file: salt + nonce + ciphertext
            with open(filepath, "wb") as f:
                f.write(self._salt)
                f.write(nonce)
                f.write(ciphertext)

        except (OSError, json.JSONDecodeError) as e:
            raise VaultError(f"Failed to save vault: {e}") from e

    @classmethod
    def load(cls, filepath: str | Path, master_password: str) -> "PasswordManager":
        """
        Load and decrypt vault from file.

        Args:
            filepath: Path to vault file.
            master_password: Master password to decrypt vault.

        Returns:
            Unlocked PasswordManager instance.

        Raises:
            VaultError: If file not found, corrupt, or wrong password.
            MasterPasswordError: If master password is incorrect.
        """
        if not master_password:
            raise ValueError("Master password cannot be empty")

        try:
            with open(filepath, "rb") as f:
                data = f.read()
        except OSError as e:
            raise VaultError(f"Failed to read vault file: {e}") from e

        if len(data) < SALT_SIZE + NONCE_SIZE:
            raise VaultError("Vault file is corrupt or empty")

        # Parse file format: salt + nonce + ciphertext
        salt = data[:SALT_SIZE]
        nonce = data[SALT_SIZE:SALT_SIZE + NON