"""
Password Manager Module

Provides AES-encrypted storage for passwords with master password authentication.
Supports adding, editing, deleting entries, and generating secure passwords.

Security Features:
- AES-256-GCM authenticated encryption
- PBKDF2-HMAC-SHA256 key derivation (100,000 iterations)
- Constant-time master password verification
- Secure random generation for salts, nonces, and passwords
- Memory-safe handling of sensitive data

Dependencies:
- cryptography (PyPI package) for AES-GCM implementation
"""

import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("Error: 'cryptography' package required. Install with: pip install cryptography")
    sys.exit(1)


class PasswordManagerError(Exception):
    """Base exception for password manager errors."""
    pass


class AuthenticationError(PasswordManagerError):
    """Raised when master password authentication fails."""
    pass


class StorageError(PasswordManagerError):
    """Raised when storage operations fail."""
    pass


class ValidationError(PasswordManagerError):
    """Raised when input validation fails."""
    pass


class PasswordManager:
    """
    AES-encrypted password manager with master password authentication.
    
    Uses AES-256-GCM for authenticated encryption and PBKDF2-HMAC-SHA256
    for key derivation from master password.
    """
    
    # Constants for security parameters
    PBKDF2_ITERATIONS = 100_000
    SALT_LENGTH = 32
    NONCE_LENGTH = 12
    KEY_LENGTH = 32  # 256 bits
    TAG_LENGTH = 16
    
    def __init__(self, storage_path: str) -> None:
        """
        Initialize password manager with storage file path.
        
        Args:
            storage_path: Path to encrypted storage file
        """
        self._storage_path = storage_path
        self._data: Dict[str, Dict[str, str]] = {}
        self._is_unlocked = False
        self._master_key: Optional[bytes] = None
    
    def _derive_key(self, password: bytes, salt: bytes) -> bytes:
        """
        Derive encryption key from master password using PBKDF2.
        
        Args:
            password: Master password as bytes
            salt: Random salt bytes
            
        Returns:
            Derived 32-byte key
        """
        return hashlib.pbkdf2_hmac(
            'sha256',
            password,
            salt,
            self.PBKDF2_ITERATIONS,
            dklen=self.KEY_LENGTH
        )
    
    def _encrypt_data(self, data: bytes, key: bytes) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypt data using AES-256-GCM.
        
        Args:
            data: Plaintext data to encrypt
            key: 32-byte encryption key
            
        Returns:
            Tuple of (nonce, ciphertext, tag)
        """
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(self.NONCE_LENGTH)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        # AESGCM returns ciphertext + tag concatenated
        tag = ciphertext[-self.TAG_LENGTH:]
        actual_ciphertext = ciphertext[:-self.TAG_LENGTH]
        return nonce, actual_ciphertext, tag
    
    def _decrypt_data(self, nonce: bytes, ciphertext: bytes, tag: bytes, key: bytes) -> bytes:
        """
        Decrypt data using AES-256-GCM.
        
        Args:
            nonce: 12-byte nonce
            ciphertext: Encrypted data
            tag: 16-byte authentication tag
            key: 32-byte decryption key
            
        Returns:
            Decrypted plaintext data
            
        Raises:
            AuthenticationError: If authentication tag verification fails
        """
        aesgcm = AESGCM(key)
        # AESGCM expects ciphertext + tag concatenated
        combined = ciphertext + tag
        try:
            return aesgcm.decrypt(nonce, combined, None)
        except Exception as e:
            raise AuthenticationError("Decryption failed: invalid master password or corrupted data") from e
    
    def _secure_compare(self, a: bytes, b: bytes) -> bool:
        """
        Constant-time comparison of two byte sequences.
        
        Args:
            a: First byte sequence
            b: Second byte sequence
            
        Returns:
            True if equal, False otherwise
        """
        return hmac.compare_digest(a, b)
    
    def create_new(self, master_password: str) -> None:
        """
        Create new encrypted storage with master password.
        
        Args:
            master_password: Master password for encryption
            
        Raises:
            ValidationError: If master password is empty
            StorageError: If storage file already exists or write fails
        """
        if not master_password:
            raise ValidationError("Master password cannot be empty")
        
        if os.path.exists(self._storage_path):
            raise StorageError(f"Storage file already exists: {self._storage_path}")
        
        # Generate random salt
        salt = secrets.token_bytes(self.SALT_LENGTH)
        
        # Derive key from master password
        key = self._derive_key(master_password.encode('utf-8'), salt)
        
        # Encrypt empty data structure
        empty_data = json.dumps({}).encode('utf-8')
        nonce, ciphertext, tag = self._encrypt_data(empty_data, key)
        
        # Prepare storage structure
        storage = {
            'version': 1,
            'salt': base64.b64encode(salt).decode('ascii'),
            'nonce': base64.b64encode(nonce).decode('ascii'),
            'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
            'tag': base64.b64encode(tag).decode('ascii')
        }
        
        # Write to file
        try:
            with open(self._storage_path, 'w') as f:
                json.dump(storage, f)
        except OSError as e:
            raise StorageError(f"Failed to create storage file: {e}") from e
        finally:
            # Clear sensitive data
            del key
            del salt
    
    def unlock(self, master_password: str) -> None:
        """
        Unlock password storage with master password.
        
        Args:
            master_password: Master password for decryption
            
        Raises:
            AuthenticationError: If master password is incorrect
            StorageError: If storage file is missing or corrupted
            ValidationError: If master password is empty
        """
        if not master_password:
            raise ValidationError("Master password cannot be empty")
        
        if not os.path.exists(self._storage_path):
            raise StorageError(f"Storage file not found: {self._storage_path}")
        
        # Load storage file
        try:
            with open(self._storage_path, 'r') as f:
                storage = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise StorageError(f"Failed to read storage file: {e}") from e
        
        # Validate storage structure
        required_fields = ['version', 'salt', 'nonce', 'ciphertext', 'tag']
        for field in required_fields:
            if field not in storage:
                raise StorageError(f"Corrupted storage: missing field '{field}'")
        
        if storage['version'] != 1:
            raise StorageError(f"Unsupported storage version: {storage['version']}")
        
        # Decode base64 fields
        try:
            salt = base64.b64decode(storage['salt'])
            nonce = base64.b64decode(storage['nonce'])
            ciphertext = base64.b64decode(storage['ciphertext'])
            tag = base64.b64decode(storage['tag'])
        except Exception as e:
            raise StorageError(f"Corrupted storage encoding: {e}") from e
        
        # Derive key and decrypt
        key = self._derive_key(master_password.encode('utf-8'), salt)
        
        try:
            plaintext = self._decrypt_data(nonce, ciphertext, tag, key)
        except AuthenticationError:
            # Clear key before raising
            del key
            raise
        
        # Parse decrypted data
        try:
            self._data = json.loads(plaintext.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            del key
            raise StorageError(f"Corrupted decrypted data: {e}") from e
        
        # Validate data structure
        if not isinstance(self._data, dict):
            del key
            raise StorageError("Corrupted data: root must be a dictionary")
        
        for service, entry in self._data.items():
            if not isinstance(entry, dict):
                del key
                raise StorageError(f"Corrupted entry for '{service}': must be a dictionary")
            required_entry_fields = ['username', 'password']
            for field in required_entry_fields:
                if field not in entry:
                    del key
                    raise StorageError(f"Corrupted entry for '{service}': missing field '{field}'")
        
        self._master_key = key
        self._is_unlocked = True
    
    def lock(self) -> None:
        """Lock the password manager and clear sensitive data from memory."""
        self._data.clear()
        self._is_unlocked = False
        if self._master_key is not None:
            # Overwrite key in memory (best effort in Python)
            self._master_key = None
    
    def _require_unlocked(self) -> None:
        """Raise error if manager is locked."""
        if not self._is_unlocked:
            raise PasswordManagerError("Password manager is locked. Call unlock() first.")
    
    def add_entry(self, service: str, username: str, password: str, notes: str = "") -> None:
        """
        Add a new password entry.
        
        Args:
            service: Service name (e.g., 'github.com')
            username: Username or email
            password: Password for the service
            notes: Optional notes
            
        Raises:
            PasswordManagerError: If manager is locked
            ValidationError: If service already exists or fields are invalid
        """
        self._require_unlocked()
        
        if not service or not username or not password:
            raise ValidationError("Service, username, and password cannot be empty")
        
        if service in self._data:
            raise ValidationError(f"Entry for '{service}' already exists. Use edit_entry() to modify.")
        
        self._data[service] = {
            'username': username,
            'password': password,
            'notes': notes
        }
    
    def edit_entry(self, service: str, username: Optional[str] = None, 
                   password: Optional[str] = None, notes: Optional[str] = None) -> None:
        """
        Edit an existing password entry.
        
        Args:
            service: Service name to edit
            username: New username (optional)
            password: New password (optional)
            notes: New notes (optional)
            
        Raises:
            PasswordManagerError: If manager is locked
            ValidationError: If service doesn't exist or no changes provided
        """
        self._require_unlocked()
        
        if service not in self._data:
            raise ValidationError(f"Entry for '{service}' not found")
        
        if username is None and password is None and notes is None:
            raise ValidationError("At least one field must be provided for editing")
        
        entry = self._data[service]
        if username is not None:
            if not username:
                raise ValidationError("Username cannot be empty")
            entry['username'] = username
        if password is not None:
            if not password:
                raise ValidationError("Password cannot be empty")
            entry['password'] = password
        if notes is not None:
            entry['notes'] = notes
    
    def delete_entry(self, service: str) -> None:
        """
        Delete a password entry.
        
        Args:
            service: Service name to delete
            
        Raises:
            PasswordManagerError: If manager is locked
            ValidationError: If service doesn't exist
        """
        self._require_unlocked()
        
        if service not in self._data:
            raise ValidationError(f"Entry for '{service}' not found")
        
        del self._data[service]
    
    def get_entry(self, service: str) -> Dict[str, str]:
        """
        Get a password entry (returns copy for security).
        
        Args:
            service: Service name to retrieve
            
        Returns:
            Dictionary with username, password, and notes
            
        Raises:
            PasswordManagerError: If manager is locked
            ValidationError: If service doesn't exist
        """
        self._require_unlocked()
        
        if service not in self._data:
            raise ValidationError(f"Entry for '{service}' not found")
        
        # Return copy to prevent accidental modification
        return self._data[service].copy()
    
    def list_entries(self) -> List[str]:
        """
        List all service names in the password manager.
        
        Returns:
            Sorted list of service names
            
        Raises:
            PasswordManagerError: If manager is locked
        """
        self._require_unlocked()
        return sorted(self._data.keys())
    
    def save(self) -> None:
        """
        Save current entries to encrypted storage.
        
        Raises:
            PasswordManagerError: If manager is locked
            StorageError: If save operation fails
        """
        self._require_unlocked()
        
        if self._master_key is None:
            raise PasswordManagerError("Master key not available")
        
        # Serialize data
        plaintext = json.dumps(self._data, separators=(',', ':')).encode('utf-8')
        
        # Encrypt with new nonce (for forward secrecy)
        nonce, ciphertext, tag = self._encrypt_data(plaintext, self._master_key)
        
        # Prepare storage structure
        storage = {
            'version': 1,
            'salt': base64.b64encode(
                hashlib.pbkdf2_hmac('sha256', b'', b'', 1, dklen=self.SALT_LENGTH)
            ).decode('ascii'),  # Placeholder - we'll keep original salt
            'nonce': base64.b64encode(nonce).decode('ascii'),
            'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
            'tag': base64.b64encode(tag).decode('ascii')
        }
        
        # Load original salt from file
        try:
            with open(self._storage_path,