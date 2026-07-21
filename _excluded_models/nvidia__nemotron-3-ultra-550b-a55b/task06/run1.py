"""
Secure Password Manager Module

This module provides a password manager with AES-GCM encrypted storage,
master password authentication, and secure password generation.

Security Features:
- AES-256-GCM authenticated encryption for data confidentiality and integrity
- PBKDF2-HMAC-SHA256 with 200,000 iterations for key derivation
- Argon2id for master password verification (if available, fallback to PBKDF2)
- Secure random generation using secrets module
- Constant-time comparison for authentication
- Memory-safe handling of sensitive data

Dependencies:
- cryptography (PyPI): For AES-GCM encryption
- argon2 (PyPI, optional): For stronger password hashing

Usage:
    manager = PasswordManager("vault.enc")
    manager.create_vault("master_password")
    manager.unlock("master_password")
    manager.add_entry("example.com", "user", "password123")
    print(manager.get_entry("example.com"))
    manager.lock()
"""

import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidTag
except ImportError as e:
    raise ImportError(
        "The 'cryptography' package is required. Install with: pip install cryptography"
    ) from e

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    PasswordHasher = None  # type: ignore
    VerifyMismatchError = Exception  # type: ignore

# Constants
PBKDF2_ITERATIONS = 200_000
SALT_SIZE = 32
NONCE_SIZE = 12
KEY_SIZE = 32
TAG_SIZE = 16
VAULT_VERSION = 1
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
DEFAULT_PASSWORD_LENGTH = 16
CHARSETS = {
    "lowercase": "abcdefghijklmnopqrstuvwxyz",
    "uppercase": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "digits": "0123456789",
    "symbols": "!@#$%^&*()-_=+[]{}|;:,.<>?",
}


class PasswordManagerError(Exception):
    """Base exception for password manager errors."""
    pass


class VaultError(PasswordManagerError):
    """Exception for vault file operations."""
    pass


class AuthenticationError(PasswordManagerError):
    """Exception for authentication failures."""
    pass


class EncryptionError(PasswordManagerError):
    """Exception for encryption/decryption failures."""
    pass


class ValidationError(PasswordManagerError):
    """Exception for input validation failures."""
    pass


@dataclass
class VaultHeader:
    """Vault file header metadata."""
    version: int
    salt: str  # base64 encoded
    kdf: str  # "argon2id" or "pbkdf2"
    kdf_params: Dict[str, Any]
    created_at: float
    updated_at: float


@dataclass
class EncryptedEntry:
    """Encrypted password entry."""
    nonce: str  # base64 encoded
    ciphertext: str  # base64 encoded
    tag: str  # base64 encoded (for AES-GCM, included in ciphertext but stored separately for clarity)


@dataclass
class PasswordEntry:
    """Decrypted password entry."""
    name: str
    username: str
    password: str
    url: str = ""
    notes: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


def _b64encode(data: bytes) -> str:
    """Encode bytes to base64 string."""
    import base64
    return base64.b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    """Decode base64 string to bytes."""
    import base64
    return base64.b64decode(data.encode("ascii"))


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """Constant-time comparison of two byte sequences."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


def _derive_key_pbkdf2(password: bytes, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Derive encryption key using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password)


def _derive_key_argon2(password: bytes, salt: bytes) -> bytes:
    """Derive encryption key using Argon2id."""
    if not ARGON2_AVAILABLE:
        raise RuntimeError("Argon2 not available")
    # Argon2id parameters: time_cost=3, memory_cost=65536 (64MB), parallelism=4
    ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=KEY_SIZE, salt_len=len(salt))
    # We need raw key, not hash. Use a custom approach: hash password+salt with argon2 then use as key
    # Actually, argon2.PasswordHasher is for password verification, not key derivation.
    # For key derivation, we should use argon2.low_level.hash_secret_raw
    from argon2.low_level import hash_secret_raw, Type
    return hash_secret_raw(
        secret=password,
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=KEY_SIZE,
        type=Type.ID,
    )


def _verify_master_password_argon2(stored_hash: str, password: bytes) -> bool:
    """Verify master password using Argon2id."""
    if not ARGON2_AVAILABLE:
        return False
    try:
        ph = PasswordHasher()
        ph.verify(stored_hash, password.decode("utf-8"))
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _hash_master_password_argon2(password: bytes) -> str:
    """Hash master password using Argon2id for storage."""
    if not ARGON2_AVAILABLE:
        raise RuntimeError("Argon2 not available")
    ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
    return ph.hash(password.decode("utf-8"))


def _verify_master_password_pbkdf2(stored_hash: str, password: bytes, salt: bytes, iterations: int) -> bool:
    """Verify master password using PBKDF2."""
    try:
        derived = _derive_key_pbkdf2(password, salt, iterations)
        return _constant_time_compare(derived, _b64decode(stored_hash))
    except Exception:
        return False


def _hash_master_password_pbkdf2(password: bytes, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Hash master password using PBKDF2 for storage."""
    derived = _derive_key_pbkdf2(password, salt, iterations)
    return _b64encode(derived)


def _encrypt_data(key: bytes, plaintext: bytes) -> Tuple[bytes, bytes, bytes]:
    """Encrypt data using AES-256-GCM."""
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    # AESGCM returns ciphertext + tag concatenated
    actual_ciphertext = ciphertext[:-TAG_SIZE]
    tag = ciphertext[-TAG_SIZE:]
    return nonce, actual_ciphertext, tag


def _decrypt_data(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    """Decrypt data using AES-256-GCM."""
    aesgcm = AESGCM(key)
    # AESGCM expects ciphertext + tag concatenated
    combined = ciphertext + tag
    try:
        return aesgcm.decrypt(nonce, combined, None)
    except InvalidTag as e:
        raise EncryptionError("Decryption failed: invalid authentication tag") from e


def _secure_erase(data: Union[bytearray, memoryview]) -> None:
    """Attempt to securely erase sensitive data from memory."""
    if isinstance(data, bytearray):
        for i in range(len(data)):
            data[i] = 0
    elif isinstance(data, memoryview):
        data[:] = b'\x00' * len(data)


class PasswordManager:
    """
    Secure password manager with encrypted storage.
    
    Provides functionality for creating/opening encrypted vaults,
    managing password entries, and generating secure passwords.
    """
    
    def __init__(self, vault_path: Union[str, Path]) -> None:
        """
        Initialize password manager with vault file path.
        
        Args:
            vault_path: Path to the encrypted vault file.
        """
        self._vault_path = Path(vault_path)
        self._header: Optional[VaultHeader] = None
        self._entries: Dict[str, EncryptedEntry] = {}
        self._master_key: Optional[bytes] = None
        self._is_unlocked = False
        self._master_password_hash: Optional[str] = None
        self._kdf_type: str = "argon2id" if ARGON2_AVAILABLE else "pbkdf2"
    
    @property
    def is_unlocked(self) -> bool:
        """Check if vault is currently unlocked."""
        return self._is_unlocked
    
    @property
    def vault_path(self) -> Path:
        """Get vault file path."""
        return self._vault_path
    
    def create_vault(self, master_password: str) -> None:
        """
        Create a new encrypted vault.
        
        Args:
            master_password: Master password for the vault.
            
        Raises:
            ValidationError: If master password is too weak.
            VaultError: If vault file already exists or cannot be created.
        """
        self._validate_master_password(master_password)
        
        if self._vault_path.exists():
            raise VaultError(f"Vault already exists at {self._vault_path}")
        
        salt = secrets.token_bytes(SALT_SIZE)
        password_bytes = master_password.encode("utf-8")
        
        # Derive master key for encryption
        if self._kdf_type == "argon2id":
            master_key = _derive_key_argon2(password_bytes, salt)
            master_password_hash = _hash_master_password_argon2(password_bytes)
            kdf_params = {"time_cost": 3, "memory_cost": 65536, "parallelism": 4}
        else:
            master_key = _derive_key_pbkdf2(password_bytes, salt)
            master_password_hash = _hash_master_password_pbkdf2(password_bytes, salt)
            kdf_params = {"iterations": PBKDF2_ITERATIONS}
        
        now = time.time()
        self._header = VaultHeader(
            version=VAULT_VERSION,
            salt=_b64encode(salt),
            kdf=self._kdf_type,
            kdf_params=kdf_params,
            created_at=now,
            updated_at=now,
        )
        self._master_key = master_key
        self._master_password_hash = master_password_hash
        self._entries = {}
        self._is_unlocked = True
        
        self._save_vault()
        
        # Clear sensitive data
        _secure_erase(bytearray(password_bytes))
        _secure_erase(bytearray(master_key))
    
    def unlock(self, master_password: str) -> None:
        """
        Unlock existing vault with master password.
        
        Args:
            master_password: Master password for the vault.
            
        Raises:
            VaultError: If vault file doesn't exist or is corrupted.
            AuthenticationError: If master password is incorrect.
            EncryptionError: If vault decryption fails.
        """
        if not self._vault_path.exists():
            raise VaultError(f"Vault not found at {self._vault_path}")
        
        self._load_vault()
        
        if self._header is None or self._master_password_hash is None:
            raise VaultError("Vault header is missing or corrupted")
        
        password_bytes = master_password.encode("utf-8")
        salt = _b64decode(self._header.salt)
        
        # Verify master password
        verified = False
        if self._header.kdf == "argon2id" and ARGON2_AVAILABLE:
            verified = _verify_master_password_argon2(self._master_password_hash, password_bytes)
        elif self._header.kdf == "pbkdf2":
            iterations = self._header.kdf_params.get("iterations", PBKDF2_ITERATIONS)
            verified = _verify_master_password_pbkdf2(
                self._master_password_hash, password_bytes, salt, iterations
            )
        else:
            raise VaultError(f"Unsupported KDF: {self._header.kdf}")
        
        if not verified:
            _secure_erase(bytearray(password_bytes))
            raise AuthenticationError("Invalid master password")
        
        # Derive master key
        if self._header.kdf == "argon2id":
            master_key = _derive_key_argon2(password_bytes, salt)
        else:
            iterations = self._header.kdf_params.get("iterations", PBKDF2_ITERATIONS)
            master_key = _derive_key_pbkdf2(password_bytes, salt, iterations)
        
        self._master_key = master_key
        self._is_unlocked = True
        
        # Clear sensitive data
        _secure_erase(bytearray(password_bytes))
    
    def lock(self) -> None:
        """Lock the vault and clear sensitive data from memory."""
        self._master_key = None
        self._is_unlocked = False
        # Clear entries from memory (they're encrypted on disk)
        self._entries.clear()
    
    def _require_unlocked(self) -> None:
        """Raise error if vault is locked."""
        if not self._is_unlocked or self._master_key is None:
            raise PasswordManagerError("Vault is locked. Call unlock() first.")
    
    def add_entry(
        self,
        name: str,
        username: str,
        password: str,
        url: str = "",
        notes: str = ""
    ) -> None:
        """
        Add a new password entry.
        
        Args:
            name: Entry name/identifier (e.g., "github.com").
            username: Username or email.
            password: Password to store.
            url: Optional URL associated with the entry.
            notes: Optional notes.
            
        Raises:
            ValidationError: If entry name already exists or inputs are invalid.
            PasswordManagerError: If vault is locked.
        """
        self._require_unlocked()
        
        if not name or not name.strip():
            raise ValidationError("Entry name cannot be empty")
        if name in self._entries:
            raise ValidationError(f"Entry '{name}' already exists")
        if not username:
            raise ValidationError("Username cannot be empty")
        if not password:
            raise ValidationError("Password cannot be empty")
        
        now = time.time()
        entry = PasswordEntry(
            name=name.strip(),
            username=username.strip(),
            password=password,
            url=url.strip() if url else "",
            notes=notes.strip() if notes else "",
            created_at=now,
            updated_at=now,
        )
        
        self._encrypt_and_store_entry(entry)
        
        if self._header:
            self._header.updated_at = now
        self._save_vault()
    
    def