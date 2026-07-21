"""
Secure Password Manager Module

This module provides a password manager with AES-encrypted storage,
master-password authentication, and CRUD operations for password entries.
It includes a secure password generator and follows security best practices.

Dependencies: pycryptodome (PyCryptodome) for AES encryption, pbkdf2, and secure random operations.
"""

import os
import json
import base64
import hashlib
import secrets
import string
import time
from typing import Dict, List, Optional, Tuple, Any
from getpass import getpass
from dataclasses import dataclass, field, asdict

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes
from Crypto.Hash import SHA256
from Crypto.Util.Padding import pad, unpad


# Constants
SALT_SIZE = 32
KEY_SIZE = 32  # 256-bit AES key
IV_SIZE = 16
PBKDF2_ITERATIONS = 1_000_000
TAG_SIZE = 16
VAULT_FILE_PERMISSIONS = 0o600
MASTER_PASSWORD_MIN_LENGTH = 12
PASSWORD_GENERATION_LENGTH = 20
MAX_ENTRY_NAME_LENGTH = 100
MAX_PASSWORD_LENGTH = 256
MAX_USERNAME_LENGTH = 256
MAX_URL_LENGTH = 2048
MAX_NOTES_LENGTH = 4096


class PasswordManagerError(Exception):
    """Base exception for password manager errors."""
    pass


class AuthenticationError(PasswordManagerError):
    """Raised when master password authentication fails."""
    pass


class VaultIntegrityError(PasswordManagerError):
    """Raised when the vault file is corrupted or tampered with."""
    pass


class EntryNotFoundError(PasswordManagerError):
    """Raised when a requested entry is not found."""
    pass


class ValidationError(PasswordManagerError):
    """Raised when input validation fails."""
    pass


@dataclass
class PasswordEntry:
    """Represents a single password entry.

    Attributes:
        name: Unique identifier for the entry.
        username: Associated username.
        password: The encrypted password string.
        url: Optional URL associated with the entry.
        notes: Optional notes.
        created_at: Timestamp of creation.
        updated_at: Timestamp of last update.
    """
    name: str
    username: str
    password: str
    url: Optional[str] = None
    notes: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        """Validate entry fields against constraints.

        Raises:
            ValidationError: If any field violates constraints.
        """
        if not self.name or len(self.name) > MAX_ENTRY_NAME_LENGTH:
            raise ValidationError(f"Entry name must be 1-{MAX_ENTRY_NAME_LENGTH} characters.")
        if not self.username or len(self.username) > MAX_USERNAME_LENGTH:
            raise ValidationError(f"Username must be 1-{MAX_USERNAME_LENGTH} characters.")
        if not self.password or len(self.password) > MAX_PASSWORD_LENGTH:
            raise ValidationError(f"Password must be 1-{MAX_PASSWORD_LENGTH} characters.")
        if self.url is not None and len(self.url) > MAX_URL_LENGTH:
            raise ValidationError(f"URL must be at most {MAX_URL_LENGTH} characters.")
        if self.notes is not None and len(self.notes) > MAX_NOTES_LENGTH:
            raise ValidationError(f"Notes must be at most {MAX_NOTES_LENGTH} characters.")


class PasswordManager:
    """A secure password manager with AES-GCM encryption.

    Attributes:
        vault_path: Path to the encrypted vault file.
        master_key: Derived encryption key from master password.
    """

    def __init__(self, vault_path: str = "vault.enc") -> None:
        """Initialize the PasswordManager.

        Args:
            vault_path: Path where the encrypted vault will be stored.
        """
        self.vault_path: str = vault_path
        self.master_key: Optional[bytes] = None
        self._entries: Dict[str, PasswordEntry] = {}

    def create_vault(self, master_password: str) -> None:
        """Create a new encrypted vault with a master password.

        Args:
            master_password: The master password to secure the vault.

        Raises:
            ValidationError: If the master password does not meet complexity requirements.
            PasswordManagerError: If the vault already exists.
        """
        if os.path.exists(self.vault_path):
            raise PasswordManagerError("Vault already exists. Use unlock() instead.")

        self._validate_master_password(master_password)
        salt = get_random_bytes(SALT_SIZE)
        self.master_key = self._derive_key(master_password, salt)

        # Create initial empty vault and save
        self._entries = {}
        self._save_vault(salt)

    def unlock(self, master_password: str) -> None:
        """Unlock an existing vault using the master password.

        Args:
            master_password: The master password to unlock the vault.

        Raises:
            FileNotFoundError: If the vault file does not exist.
            AuthenticationError: If the master password is incorrect.
            VaultIntegrityError: If the vault data is corrupted.
        """
        if not os.path.exists(self.vault_path):
            raise FileNotFoundError(f"Vault file not found: {self.vault_path}")

        with open(self.vault_path, "rb") as f:
            data = f.read()

        if len(data) < SALT_SIZE + IV_SIZE + TAG_FILE_SIZE:
            raise VaultIntegrityError("Vault file appears corrupted (too small).")

        salt = data[:SALT_SIZE]
        iv = data[SALT_SIZE:SALT_SIZE + IV_SIZE]
        tag = data[SALT_SIZE + IV_SIZE:SALT_SIZE + IV_SIZE + TAG_FILE_SIZE]
        ciphertext = data[SALT_SIZE + IV_SIZE + TAG_FILE_SIZE:]

        key = self._derive_key(master_password, salt)
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        except (ValueError, KeyError) as e:
            raise AuthenticationError("Incorrect master password or vault tampered.") from e

        try:
            vault_data = json.loads(plaintext.decode("utf-8"))
            self._entries = {}
            for entry_dict in vault_data.get("entries", []):
                entry = PasswordEntry(**entry_dict)
                entry.validate()
                self._entries[entry.name] = entry
        except (json.JSONDecodeError, TypeError, ValidationError) as e:
            raise VaultIntegrityError(f"Vault data is corrupted: {e}") from e

        self.master_key = key
        return True

    def lock(self) -> None:
        """Lock the vault by clearing the master key and entries from memory."""
        self.master_key = None
        self._entries.clear()

    def is_unlocked(self) -> bool:
        """Check if the vault is currently unlocked.

        Returns:
            True if the vault is unlocked, False otherwise.
        """
        return self.master_key is not None

    def add_entry(self, entry: PasswordEntry) -> None:
        """Add a new password entry to the vault.

        Args:
            entry: The password entry to add.

        Raises:
            PasswordManagerError: If the vault is locked.
            ValidationError: If the entry is invalid.
            EntryExistsError: If an entry with the same name already exists.
        """
        self._ensure_unlocked()
        entry.validate()
        if entry.name in self._entries:
            raise ValidationError(f"Entry '{entry.name}' already exists.")
        entry.created_at = time.time()
        entry.updated_at = time.time()
        self._entries[entry.name] = entry
        self._save_vault()

    def get_entry(self, name: str) -> PasswordEntry:
        """Retrieve a password entry by name.

        Args:
            name: The name of the entry to retrieve.

        Returns:
            The PasswordEntry object.

        Raises:
            EntryNotFoundError: If the entry does not exist.
        """
        self._ensure_unlocked()
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found.")
        return self._entries[name]

    def update_entry(self, name: str, **kwargs: Any) -> None:
        """Update fields of an existing password entry.

        Args:
            name: The name of the entry to update.
            **kwargs: Fields to update (username, password, url, notes).

        Raises:
            EntryNotFoundError: If the entry does not exist.
            ValidationError: If the new values are invalid.
        """
        self._ensure_unlocked()
        entry = self.get_entry(name)
        for field, value in kwargs.items():
            if field in ("username", "password", "url", "notes"):
                setattr(entry, field, value)
            else:
                raise ValidationError(f"Unknown field: {field}")
        entry.updated_at = time.time()
        entry.validate()
        self._save_vault()

    def delete_entry(self, name: str) -> None:
        """Delete a password entry from the vault.

        Args:
            name: The name of the entry to delete.

        Raises:
            EntryNotFoundError: If the entry does not exist.
        """
        self._ensure_unlocked()
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found.")
        del self._entries[name]
        self._save_vault()

    def list_entries(self) -> List[str]:
        """List all entry names in the vault.

        Returns:
            A list of entry names.
        """
        self._ensure_unlocked()
        return list(self._entries.keys())

    def change_master_password(self, old_password: str, new_password: str) -> None:
        """Change the master password for the vault.

        Args:
            old_password: The current master password.
            new_password: The new master password.

        Raises:
            AuthenticationError: If the old password is incorrect.
            ValidationError: If the new password does not meet requirements.
        """
        self._ensure_unlocked()
        # Verify old password by trying to re-derive key with existing salt
        with open(self.vault_path, "rb") as f:
            salt = f.read(SALT_SIZE)
        key = self._derive_key(old_password, salt)
        if key != self.master_key:
            raise AuthenticationError("Incorrect old master password.")

        self._validate_master_password(new_password)
        self.master_key = self._derive_key(new_password, salt)
        self._save_vault()

    @staticmethod
    def generate_password(
        length: int = PASSWORD_GENERATION_LENGTH,
        include_uppercase: bool = True,
        include_digits: bool = True,
        include_symbols: bool = True,
    ) -> str:
        """Generate a cryptographically secure random password.

        Args:
            length: Desired password length (minimum 8).
            include_uppercase: Include uppercase letters.
            include_digits: Include digits.
            include_symbols: Include special symbols.

        Returns:
            A random password string.

        Raises:
            ValidationError: If length is less than 8.
        """
        if length < 8:
            raise ValidationError("Password length must be at least 8 characters.")

        char_pool = string.ascii_lowercase
        if include_uppercase:
            char_pool += string.ascii_uppercase
        if include_digits:
            char_pool += string.digits
        if include_symbols:
            char_pool += "!@#$%^&*()_+-=[]{}|;:,.<>?/~"

        password = ''.join(secrets.choice(char_pool) for _ in range(length))
        return password

    def _ensure_unlocked(self) -> None:
        """Check that the vault is unlocked, raising an error if not.

        Raises:
            PasswordManagerError: If the vault is locked.
        """
        if not self.is_unlocked():
            raise PasswordManagerError("Vault is locked. Call unlock() first.")

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive a 256-bit key from the master password and salt using PBKDF2-HMAC-SHA256.

        Args:
            password: The master password.
            salt: Random salt.

        Returns:
            A 32-byte derived key.
        """
        key = PBKDF2(
            password,
            salt,
            dkLen=32,
            count=PBKDF2_ITERATIONS,
            hmac_hash_module=SHA256,
        )
        return key

    @staticmethod
    def _validate_master_password(password: str) -> None:
        """Validate the master password complexity.

        Args:
            password: The master password to validate.

        Raises:
            ValidationError: If the password is too short or lacks complexity.
        """
        if len(password) < MASTER_PASSWORD_MIN_LENGTH:
            raise ValidationError(
                f"Master password must be at least {MASTER_PASSWORD_MIN_LENGTH} characters long."
            )
        if not any(c.isupper() for c in password):
            raise ValidationError("Master password must contain at least one uppercase letter.")
        if not any(c.islower() for c in password):
            raise ValidationError("Master password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in password):
            raise ValidationError("Master password must contain at least one digit.")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/" for c in password):
            raise ValidationError("Master password must contain at least one special character.")

    def _save_vault(self) -> None:
        """Encrypt and write the vault to disk.

        Uses AES-256-GCM with a random IV. The file format is:
        [SALT][IV][TAG][CIPHERTEXT]
        """
        if not self.master_key:
            raise PasswordManagerError("Cannot save vault without a master key.")

        plaintext = json.dumps([asdict(entry) for entry in self._entries.values()]).encode("utf-8")
        iv = get_random_bytes(IV_SIZE)
        cipher = AES.new(self.master_key, AES.MODE_GCM, nonce=iv)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)

        # Read existing salt from file if available, otherwise use a new one
        if os.path.exists(self.vault_path):
            with open(self.vault_path, "rb") as f:
                salt = f.read(SALT_SIZE)
        else:
            salt = get_random_bytes(SALT_SIZE)

        with open(self.vault_path, "wb") as f:
            f.write(salt + iv + tag + ciphertext)
        os.chmod(self.vault_path, VAULT_FILE_PERMISSIONS)


def main() -> None:
    """Simple command-line interface for the password manager."""
    print("=== Secure Password Manager ===")
    vault_file = input("Vault file path [vault.enc]: ").strip() or "vault.enc"
    pm = PasswordManager(vault_file)

    if not os.path.exists(vault_file):
        print("No existing vault found. Creating a new one.")
        master_password = getpass("Set master password: ")
        confirm = getpass("Confirm master password: ")
        if master_password != confirm:
            print("Passwords do not match.")
            return
        try:
            pm.create_vault(master_password)
            print("Vault created and unlocked.")
        except ValidationError as e:
            print(f"Error: {e}")
            return
    else:
        master_password = getpass("Master password: ")
        try:
            if pm.unlock(master_password):
                print("Vault unlocked.")
        except (AuthenticationError, VaultIntegrityError) as e:
            print(f"Error: {e}")
            return

    while True:
        print("\nCommands: list, add, get, update, delete, generate, lock, exit")
        cmd = input("> ").strip().lower()

        if cmd == "list":
            try:
                entries = pm.list_entries()
                if not entries:
                    print("No entries.")
                else:
                    for name in entries:
                        print(f" - {name}")
            except PasswordManagerError as e:
                print(f"Error: {e}")

        elif cmd == "add":
            name = input("Entry name: ")
            username = input("Username: ")
            password = getpass("Password (leave blank to generate): ")
            if not password:
                password = PasswordManager.generate_password()
                print(f"Generated password: {password}")
            url = input("URL (optional): ") or None
            notes = input("Notes (optional): ") or None
            try:
                entry = PasswordEntry(name=name, username=username, password=password, url=url, notes=notes)
                pm.add_entry(entry)
                print("Entry added.")
            except (ValidationError, PasswordManagerError) as e:
                print(f"Error: {e}")

        elif cmd == "get":
            name = input("Entry name: ")
            try:
                entry = pm.get_entry(name)
                print(f"Name: {entry.name}")
                print(f"Username: {entry.username}")
                print(f"Password: {entry.password}")
                if entry.url:
                    print(f"URL: {entry.url}")
                if entry.notes:
                    print(f"Notes: {entry.notes}")
            except (EntryNotFoundError, PasswordManagerError) as e:
                print(f"Error: {e}")

        elif cmd == "update":
            name = input("Entry name to update: ")
            try:
                entry = pm.get_entry(name)
                print("Leave blank to keep current value.")
                username = input(f"Username [{entry.username}]: ") or entry.username
                password = getpass(f"Password (leave blank to keep current): ") or entry.password
                url = input(f"URL [{entry.url or ''}]: ") or entry.url
                notes = input(f"Notes [{entry.notes or ''}]: ") or entry.notes
                pm.update_entry(name, username=username, password=password, url=url, notes=notes)
                print("Entry updated.")
            except (EntryNotFoundError, ValidationError, PasswordManagerError) as e:
                print(f"Error: {e}")

        elif cmd == "delete":
            name = input("Entry name to delete: ")
            try:
                pm.delete_entry(name)
                print("Entry deleted.")
            except (EntryNotFoundError