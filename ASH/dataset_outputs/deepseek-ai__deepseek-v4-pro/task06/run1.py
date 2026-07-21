"""
Password Manager Module

A secure password manager that provides AES-encrypted storage, master password
authentication, and CRUD operations for password entries with password generation.

Uses AES-256-GCM for authenticated encryption and PBKDF2 for key derivation.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import struct
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Union

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag


# Constants for security parameters
SALT_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16
PBKDF2_ITERATIONS = 600_000
KEY_SIZE = 32  # AES-256
HMAC_KEY_SIZE = 32
PEPPER = b"password_manager_v1_global_pepper"  # In production, store securely externally


@dataclass
class PasswordEntry:
    """Represents a single password entry stored in the manager."""
    id: str
    site: str
    username: str
    password: str
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        """Convert entry to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "PasswordEntry":
        """Create a PasswordEntry from a dictionary."""
        return cls(**data)


class CryptoError(Exception):
    """Base exception for cryptographic operations."""
    pass


class AuthenticationError(Exception):
    """Raised when master password authentication fails."""
    pass


class EntryNotFoundError(Exception):
    """Raised when a password entry is not found."""
    pass


class PasswordManager:
    """
    Secure password manager with AES-256-GCM encryption and master password authentication.

    Features:
    - Master password authentication with key derivation (PBKDF2-HMAC-SHA256)
    - Encrypted storage using AES-256-GCM for confidentiality and integrity
    - Add, edit, delete, and list password entries
    - Secure random password generation
    - Protection against tampering via HMAC over ciphertext

    The data format stores:
    - Salt for key derivation
    - Encrypted JSON blob containing all entries
    - HMAC for integrity verification of the encrypted data
    """

    def __init__(self, storage_path: str = "passwords.enc"):
        """
        Initialize the password manager with a storage file path.

        Args:
            storage_path: Path to the encrypted storage file.
        """
        self.storage_path = storage_path
        self._entries: Dict[str, PasswordEntry] = {}
        self._authenticated = False
        self._encryption_key: Optional[bytes] = None
        self._hmac_key: Optional[bytes] = None

    def _derive_keys(self, master_password: str, salt: bytes) -> Tuple[bytes, bytes]:
        """
        Derive encryption and HMAC keys from the master password using PBKDF2.

        Uses a global pepper for additional security.

        Args:
            master_password: The master password string.
            salt: Random salt bytes.

        Returns:
            Tuple of (encryption_key, hmac_key) both 32 bytes.

        Raises:
            CryptoError: If key derivation fails.
        """
        try:
            # Combine password with pepper
            peppered = master_password.encode("utf-8") + PEPPER

            # Derive 64 bytes: first 32 for encryption, last 32 for HMAC
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=KEY_SIZE + HMAC_KEY_SIZE,
                salt=salt,
                iterations=PBKDF2_ITERATIONS,
                backend=default_backend(),
            )
            key_material = kdf.derive(peppered)

            return key_material[:KEY_SIZE], key_material[KEY_SIZE:]
        except Exception as e:
            raise CryptoError(f"Key derivation failed: {e}") from e

    def _encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypt data using AES-256-GCM.

        Args:
            plaintext: Data to encrypt.

        Returns:
            Nonce + ciphertext + tag concatenated.

        Raises:
            CryptoError: If encryption fails.
        """
        if self._encryption_key is None:
            raise CryptoError("No encryption key available. Authenticate first.")

        try:
            nonce = os.urandom(NONCE_SIZE)
            aesgcm = AESGCM(self._encryption_key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            return nonce + ciphertext
        except Exception as e:
            raise CryptoError(f"Encryption failed: {e}") from e

    def _decrypt(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt data using AES-256-GCM.

        Args:
            encrypted_data: Nonce + ciphertext + tag.

        Returns:
            Decrypted plaintext.

        Raises:
            CryptoError: If decryption fails (wrong key or tampered data).
        """
        if self._encryption_key is None:
            raise CryptoError("No encryption key available. Authenticate first.")

        try:
            nonce = encrypted_data[:NONCE_SIZE]
            ciphertext = encrypted_data[NONCE_SIZE:]
            aesgcm = AESGCM(self._encryption_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext
        except InvalidTag as e:
            raise CryptoError("Decryption failed: Invalid authentication tag. "
                              "Data may be tampered or wrong master password.") from e
        except Exception as e:
            raise CryptoError(f"Decryption failed: {e}") from e

    def _compute_hmac(self, data: bytes) -> bytes:
        """
        Compute HMAC-SHA256 over the given data using the HMAC key.

        Args:
            data: Data to authenticate.

        Returns:
            HMAC digest bytes.

        Raises:
            CryptoError: If HMAC key is not available.
        """
        if self._hmac_key is None:
            raise CryptoError("No HMAC key available. Authenticate first.")
        return hmac.new(self._hmac_key, data, hashlib.sha256).digest()

    def _verify_hmac(self, data: bytes, expected_hmac: bytes) -> bool:
        """
        Verify HMAC using constant-time comparison.

        Args:
            data: Data to verify.
            expected_hmac: Expected HMAC digest.

        Returns:
            True if valid, False otherwise.
        """
        if self._hmac_key is None:
            return False
        computed = self._compute_hmac(data)
        return hmac.compare_digest(computed, expected_hmac)

    def _load_entries(self) -> None:
        """
        Load entries from the encrypted storage file.

        Raises:
            FileNotFoundError: If storage file doesn't exist (treated as empty).
            CryptoError: If decryption or integrity verification fails.
        """
        if not os.path.exists(self.storage_path):
            self._entries = {}
            return

        try:
            with open(self.storage_path, "rb") as f:
                data = f.read()

            # Format: salt (32) | hmac (32) | nonce + ciphertext + tag
            if len(data) < SALT_KEY + 32 + NONCE_SIZE + TAG_SIZE:
                raise CryptoError("Storage file is corrupted or invalid format.")

            salt = data[:SALT_KEY]
            stored_hmac = data[SALT_KEY:SALT_KEY + 32]
            encrypted_payload = data[SALT_KEY + 32:]

            # Verify integrity
            if not self._verify_hmac(salt + encrypted_payload, stored_hmac):
                raise AuthenticationError(
                    "Data integrity check failed. File may be tampered or wrong master password."
                )

            plaintext = self._decrypt(encrypted_payload)
            entries_data = json.loads(plaintext.decode("utf-8"))

            self._entries = {}
            for entry_id, entry_dict in entries_data.items():
                self._entries[entry_id] = PasswordEntry.from_dict(entry_dict)

        except (json.JSONDecodeError, KeyError) as e:
            raise CryptoError(f"Failed to parse password data: {e}") from e
        except AuthenticationError:
            raise
        except Exception as e:
            raise CryptoError(f"Failed to load passwords: {e}") from e

    def _save_storage(self) -> None:
        """
        Encrypt and save entries to the storage file with integrity protection.
        """
        if self._encryption_key is None or self._hmac_key is None:
            raise CryptoError("Cannot save: not authenticated.")

        try:
            # Serialize entries
            entries_dict = {
                entry_id: entry.to_dict() for entry_id, entry in self._entries.items()
            }
            plaintext = json.dumps(entries_dict, indent=2).encode("utf-8")

            # Generate new salt for this save (enhances security)
            salt = os.urandom(SALT_KEY)

            # Re-derive keys with new salt (optional but recommended for key rotation)
            # For simplicity, we use the existing keys but include salt in HMAC
            encrypted_payload = self._encrypt(plaintext)
            hmac_digest = self._compute_hmac(salt + encrypted_payload)

            # Write: salt + hmac + encrypted_payload
            with open(self.storage_path, "wb") as f:
                f.write(salt + hmac_digest + encrypted_payload)

        except Exception as e:
            raise CryptoError(f"Failed to save passwords: {e}") from e

    def authenticate(self, master_password: str) -> bool:
        """
        Authenticate with the master password and load entries.

        Args:
            master_password: The master password.

        Returns:
            True if authentication successful.

        Raises:
            AuthenticationError: If authentication fails.
        """
        if not master_password:
            raise AuthenticationError("Master password cannot be empty.")

        try:
            # If file exists, try to load with the password
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "rb") as f:
                    data = f.read()
                if len(data) < SALT_KEY:
                    raise CryptoError("Invalid storage file format.")

                salt = data[:SALT_KEY]
                self._encryption_key, self._hmac_key = self._derive_key(
                    master_password, salt
                )
                self._load_storage()
            else:
                # Create new vault with fresh salt
                salt = os.urandom(SALT_KEY)
                self._encryption_key, self._hmac_key = self._derive_key(
                    master_password, salt
                )
                self._entries = {}
                self._save_storage()

            self._authenticated = True
            return True

        except AuthenticationError:
            self._encryption_key = None
            self._hmac_key = None
            self._authenticated = False
            raise
        except Exception as e:
            self._encryption_key = None
            self._hmac_key = None
            self._authenticated = False
            raise AuthenticationError(f"Authentication failed: {e}") from e

    def is_authenticated(self) -> bool:
        """Check if the manager is currently authenticated."""
        return self._authenticated

    def _check_auth(self) -> None:
        """Raise if not authenticated."""
        if not self._authenticated:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")

    def add_entry(
        self,
        site: str,
        username: str,
        password: str,
        notes: str = "",
        entry_id: Optional[str] = None,
    ) -> str:
        """
        Add a new password entry.

        Args:
            site: Website or service name.
            username: Username for the site.
            password: Password for the site.
            notes: Optional notes.
            entry_id: Optional custom ID (auto-generated if not provided).

        Returns:
            The entry ID.

        Raises:
            ValueError: If required fields are empty.
        """
        self._check_auth()

        if not site.strip():
            raise ValueError("Site name cannot be empty.")
        if not username.strip():
            raise ValueError("Username cannot be empty.")
        if not password:
            raise ValueError("Password cannot be empty.")

        if entry_id is None:
            entry_id = secrets.token_hex(8)

        if entry_id in self._entries:
            raise ValueError(f"Entry with ID '{entry_id}' already exists.")

        entry = PasswordEntry(
            id=entry_id,
            site=site.strip(),
            username=username.strip(),
            password=password,
            notes=notes.strip() if notes else "",
        )
        self._entries[entry_id] = entry
        self._save_storage()
        return entry_id

    def edit_entry(
        self,
        entry_id: str,
        site: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Edit an existing password entry.

        Args:
            entry_id: ID of the entry to edit.
            site: New site name (if provided).
            username: New username (if provided).
            password: New password (if provided).
            notes: New notes (if provided).

        Raises:
            EntryNotFoundError: If the entry doesn't exist.
            ValueError: If no fields to update are provided.
        """
        self._check_auth()

        if entry_id not in self._entries:
            raise EntryNotFoundError(f"Entry with ID '{entry_id}' not found.")

        entry = self._entries[entry_id]
        updated = False

        if site is not None and site.strip():
            entry.site = site.strip()
            updated = True
        if username is not None and username.strip():
            entry.username = username.strip()
            updated = True
        if password is not None:
            entry.password = password
            updated = True
        if notes is not None:
            entry.notes = notes.strip() if notes else ""
            updated = True

        if not updated:
            raise ValueError("At least one field must be provided for update.")

        entry.modified_at = time.time()
        self._save_storage()

    def delete_entry(self, entry_id: str) -> None:
        """
        Delete a password entry.

        Args:
            entry_id: ID of the entry to delete.

        Raises:
            EntryNotFoundError: If the entry doesn't exist.
        """
        self._check_auth()

        if entry_id not in self._entries:
            raise EntryNotFoundError(f"Entry with ID '{entry_id}' not found.")

        del self._entries[entry_id]
        self._save_storage()

    def get_entry(self, entry_id: str) -> PasswordEntry:
        """
        Get a specific entry by ID.

        Args:
            entry_id: The entry ID.

        Returns:
            The PasswordEntry object.

        Raises:
            EntryNotFoundError: If the entry doesn't exist.
        """
        self._check_auth()

        if entry_id not in self._entries:
            raise EntryNotFoundError(f"Entry with ID '{entry_id}' not found.")

        return self._entries[entry_id]

    def list_entries(self) -> List[PasswordEntry]:
        """
        List all stored entries (without passwords for safety).

        Returns:
            List of PasswordEntry objects (passwords masked).

        Note:
            Passwords are not included in the returned entries for safety.
            Use get_entry() to retrieve the actual password.
        """
        self._check_auth()

        entries = []
        for entry in self._entries.values():
            # Return a copy with masked password
            safe_entry = PasswordEntry(
                id=entry.id,
                site=entry.site,
                username=entry.username,
                password="********",
                notes=entry.notes,
                created_at=entry.created_at,
                modified_at=entry.modified_at,
            )
            entries.append(safe_entry)
        return entries

    def search_entries(self, query: str) -> List[PasswordEntry]:
        """
        Search entries by site substring match.

        Args:
            query: Search string to match against site names.

        Returns:
            List of matching PasswordEntry objects.
        """
        self._check_auth()

        query_lower = query.lower()
        results = []
        for entry in self._entries.values():
            if query_lower in entry.site.lower():
                results.append(entry)
        return results

    @staticmethod
    def generate_password(
        length: int = 20,
        include_uppercase: bool = True,
        include_lowercase: bool = True,
        include_digits: bool = True,
        include_symbols: bool = True,
        min_uppercase: int = 1,
        min_lowercase: int = 1,
        min_digits: int = 1,
        min_symbols: int = 1,
    ) -> str:
        """
        Generate a cryptographically secure random password.

        Args:
            length: Total password length (minimum 8).
            include_uppercase: Include uppercase letters.
            include_lowercase: Include lowercase letters.
            include_digits: Include digits.
            include_symbols: Include symbols.
            min_uppercase: Minimum number of uppercase letters.
            min_lowercase: Minimum number of lowercase letters.
            min_digits: Minimum number of digits.
            min_symbols: Minimum number of symbols.

        Returns:
            Generated password string.

        Raises:
            ValueError: If constraints cannot be met.
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters.")

        # Build character sets
        uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if include_uppercase else ""
        lowercase = "abcdefghijklmnopqrstuvwxyz" if include_lowercase else ""
        digits = "0123456789" if include_digits else ""
        symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?" if include_symbols else ""

        all_chars = uppercase + lowercase + digits + symbols
        if not all_chars:
            raise ValueError("At least one character set must be included