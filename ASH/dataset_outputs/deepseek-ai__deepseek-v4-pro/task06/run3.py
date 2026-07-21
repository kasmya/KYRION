"""
Secure Password Manager Module

This module provides a command-line password manager with AES-encrypted storage,
master password authentication, and comprehensive credential management capabilities.
It supports adding, editing, deleting, and generating passwords, all stored securely
using industry-standard encryption with PBKDF2 key derivation.
"""

import os
import json
import base64
import secrets
import string
import hashlib
import getpass
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidKey, InvalidTag


class PasswordManagerError(Exception):
    """Base exception class for password manager errors."""
    pass


class AuthenticationError(PasswordManagerError):
    """Raised when master password authentication fails."""
    pass


class EntryNotFoundError(PasswordManagerError):
    """Raised when a requested entry is not found."""
    pass


class StorageError(PasswordManagerError):
    """Raised when there are issues with storage operations."""
    pass


class PasswordManager:
    """
    A secure password manager that stores encrypted credentials.

    This class provides functionality to manage passwords securely using AES-256-GCM
    encryption with PBKDF2 key derivation. It supports adding, editing, deleting,
    and listing password entries, as well as generating strong random passwords.

    Attributes:
        storage_file (str): Path to the encrypted storage file.
        salt (bytes): Salt used for key derivation.
        _key (Optional[bytes]): Derived encryption key, stored only in memory.
        _entries (Dict[str, Dict[str, Any]]): Decrypted password entries.
    """

    SALT_LENGTH = 32
    IV_LENGTH = 12
    TAG_LENGTH = 16
    PBKDF2_ITERATIONS = 600_000
    KEY_LENGTH = 32

    def __init__(self, storage_file: str = "passwords.enc") -> None:
        """
        Initialize the password manager.

        Args:
            storage_file: Path to the encrypted storage file.

        Raises:
            StorageError: If there are issues with file permissions.
        """
        self.storage_file = storage_file
        self._key: Optional[bytes] = None
        self._entries: Dict[str, Dict[str, Any]] = {}

        try:
            if os.path.exists(storage_file):
                with open(storage_file, 'rb') as f:
                    content = f.read()
                    if len(content) < self.SALT_LENGTH + self.IV_LENGTH:
                        raise StorageError("Corrupted storage file")
        except PermissionError as e:
            raise StorageError(f"Permission denied accessing storage file: {e}")
        except OSError as e:
            raise StorageError(f"OS error accessing storage file: {e}")

    def _derive_key(self, master_password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from master password using PBKDF2.

        Args:
            master_password: The master password string.
            salt: Cryptographic salt bytes.

        Returns:
            Derived encryption key bytes.

        Raises:
            ValueError: If password is empty or salt is invalid.
        """
        if not master_password:
            raise ValueError("Master password cannot be empty")
        if not salt or len(salt) < 16:
            raise ValueError("Salt must be at least 16 bytes")

        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=salt,
            iterations=self.AUTH_KEY_ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(master_password.encode('utf-8'))

    def _encrypt(self, plaintext: bytes) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypt data using AES-256-GCM.

        Args:
            plaintext: Data to encrypt.

        Returns:
            Tuple of (iv, ciphertext, tag).

        Raises:
            ValueError: If key is not set or plaintext is invalid.
        """
        if self._key is None:
            raise ValueError("Encryption key not available. Authenticate first.")

        try:
            iv = os.urandom(self.IV_LENGTH)
            encryptor = Cipher(
                algorithms.AES(self._key),
                modes.GCM(iv),
                backend=default_backend()
            ).encryptor()

            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(plaintext) + padder.finalize()

            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            return (iv, ciphertext, encryptor.tag)
        except Exception as e:
            raise StorageError(f"Encryption failed: {e}")

    def _decrypt(self, iv: bytes, ciphertext: bytes, tag: bytes) -> bytes:
        """
        Decrypt data using AES-256-GCM.

        Args:
            iv: Initialization vector.
            ciphertext: Encrypted data.
            tag: Authentication tag.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            ValueError: If key is not available or decryption fails.
        """
        if self._key is None:
            raise ValueError("Encryption key not available. Authenticate first.")

        try:
            decryptor = Cipher(
                algorithms.AES(self._key),
                modes.GCM(iv, tag),
                backend=default_backend()
            ).decryptor()

            padded_data = decryptor.update(ciphertext) + decryptor.finalize()

            unpadder = padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded_data) + unpadder.finalize()
            return plaintext
        except InvalidTag:
            raise ValueError("Authentication failed: data may be corrupted or tampered")
        except Exception as e:
            raise StorageError(f"Decryption failed: {e}")

    def authenticate(self, master_password: str) -> bool:
        """
        Authenticate with master password and load entries.

        Args:
            master_password: Master password for authentication.

        Returns:
            True if authentication successful.

        Raises:
            AuthenticationError: If authentication fails.
            StorageError: If storage operations fail.
        """
        if not master_password:
            raise AuthenticationError("Master password cannot be empty")

        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'rb') as f:
                    content = f.read()

                if len(content) < self.SALT_LENGTH:
                    raise StorageError("Storage file corrupted")

                salt = content[:self.SALT_LENGTH]
                self._key = self._derive_key(master_password, salt)

                encrypted_data = content[self.SALT_LENGTH:]
                if encrypted_data:
                    try:
                        decrypted = self._decrypt(encrypted_data)
                        self._entries = json.loads(decrypted.decode('utf-8'))
                    except (json.JSONDecodeError, ValueError) as e:
                        raise AuthenticationError(f"Invalid master password or corrupted data: {e}")
                else:
                    self._entries = {}
            else:
                salt = os.urandom(self.SALT_LENGTH)
                self._key = self._derive_key(master_password, salt)
                self._entries = {}

                with open(self.storage_file, 'wb') as f:
                    f.write(salt)

            return True
        except AuthenticationError:
            raise
        except Exception as e:
            raise StorageError(f"Authentication failed: {e}")

    def save(self) -> None:
        """
        Save encrypted entries to storage file.

        Raises:
            StorageError: If save operation fails.
            ValueError: If not authenticated.
        """
        if self._key is None:
            raise ValueError("Not authenticated. Call authenticate() first.")

        try:
            plaintext = json.dumps(self._entries, indent=2).encode('utf-8')
            iv, ciphertext, tag = self._encrypt(plaintext)

            with open(self.storage_file, 'rb') as f:
                salt = f.read(self.SALT_LENGTH)

            with open(self.storage_file, 'wb') as f:
                f.write(salt)
                f.write(iv)
                f.write(tag)
                f.write(ciphertext)
        except PermissionError as e:
            raise StorageError(f"Permission denied writing to storage: {e}")
        except OSError as e:
            raise StorageError(f"Error writing to storage: {e}")
        except Exception as e:
            raise StorageError(f"Save failed: {e}")

    def add_entry(self, name: str, username: str, password: str, url: str = "", notes: str = "") -> bool:
        """
        Add a new password entry.

        Args:
            name: Entry name/identifier.
            username: Username for the account.
            password: Password for the account.
            url: Optional URL.
            notes: Optional notes.

        Returns:
            True if entry was added successfully.

        Raises:
            ValueError: If name is empty or already exists.
            StorageError: If save operation fails.
        """
        if not name:
            raise ValueError("Entry name cannot be empty")
        if name in self._entries:
            raise ValueError(f"Entry '{name}' already exists")

        self._entries[name] = {
            'username': username,
            'password': password,
            'url': url,
            'notes': notes,
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat()
        }
        self.save()
        return True

    def edit_entry(self, name: str, **kwargs: Any) -> bool:
        """
        Edit an existing password entry.

        Args:
            name: Name of the entry to edit.
            **kwargs: Fields to update (username, password, url, notes).

        Returns:
            True if entry was edited successfully.

        Raises:
            EntryNotFoundError: If entry doesn't exist.
            ValueError: If no valid fields provided.
            StorageError: If save operation fails.
        """
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found")

        valid_fields = {'username', 'password', 'url', 'notes'}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}

        if not updates:
            raise ValueError("No valid fields to update")

        self._entries[name].update(updates)
        self._entries[name]['modified'] = datetime.now().isoformat()
        self.save()
        return True

    def delete_entry(self, name: str) -> bool:
        """
        Delete a password entry.

        Args:
            name: Name of the entry to delete.

        Returns:
            True if entry was deleted.

        Raises:
            EntryNotFoundError: If entry doesn't exist.
            StorageError: If save operation fails.
        """
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found")

        del self._entries[name]
        self.save()
        return True

    def get_entry(self, name: str) -> Dict[str, Any]:
        """
        Retrieve a password entry.

        Args:
            name: Name of the entry to retrieve.

        Returns:
            Dictionary containing the entry details.

        Raises:
            EntryNotFoundError: If entry doesn't exist.
        """
        if name not in self._entries:
            raise EntryNotFoundError(f"Entry '{name}' not found")
        return self._entries[name].copy()

    def list_entries(self) -> List[str]:
        """
        List all entry names.

        Returns:
            List of entry names.
        """
        return list(self._entries.keys())

    @staticmethod
    def generate_password(length: int = 20, use_special: bool = True) -> str:
        """
        Generate a cryptographically secure random password.

        Args:
            length: Desired password length (minimum 8).
            use_special: Whether to include special characters.

        Returns:
            Generated password string.

        Raises:
            ValueError: If length is less than 8.
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters")

        alphabet = string.ascii_letters + string.digits
        if use_special:
            alphabet += "!@#$%^&*()-_=+[]{}|;:,.<>?"

        password = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits)
        ]
        if use_special:
            password.append(secrets.choice("!@#$%^&*()-_=+[]{}|;:,.<>?"))

        remaining = length - len(password)
        for _ in range(remaining):
            password.append(secrets.choice(alphabet))

        secrets.SystemRandom().shuffle(password)
        return ''.join(password)


def main() -> None:
    """
    Command-line interface for the password manager.

    This function provides an interactive menu-driven interface for managing
    passwords securely. It handles user input, authentication, and all
    password management operations.
    """
    import sys

    try:
        pm = PasswordManager("passwords.enc")

        print("=== Secure Password Manager ===")
        master_password = getpass.getpass("Enter master password: ")
        pm.authenticate(master_password)
        print("Authentication successful!")

        while True:
            print("\n--- Menu ---")
            print("1. Add entry")
            print("2. Edit entry")
            print("3. Delete entry")
            print("4. View entry")
            print("5. List entries")
            print("6. Generate password")
            print("7. Exit")

            choice = input("Enter choice (1-7): ").strip()

            try:
                if choice == '1':
                    name = input("Entry name: ").strip()
                    username = input("Username: ").strip()
                    password = getpass.getpass("Password (leave blank to generate): ").strip()
                    if not password:
                        length = input("Password length [20]: ").strip()
                        length = int(length) if length else 20
                        special = input("Include special characters? (y/n) [y]: ").strip().lower() != 'n'
                        password = pm.generate_password(length, special)
                        print(f"Generated password: {password}")
                    url = input("URL (optional): ").strip()
                    notes = input("Notes (optional): ").strip()
                    pm.add_entry(name, username, password, url, notes)
                    print(f"Entry '{name}' added successfully!")

                elif choice == '2':
                    name = input("Entry name to edit: ").strip()
                    entry = pm.get_entry(name)
                    print(f"Editing entry: {name}")
                    username = input(f"Username [{entry['username']}]: ").strip()
                    password = getpass.getpass(f"Password (leave blank to keep current): ").strip()
                    url = input(f"URL [{entry.get('url', '')}]: ").strip()
                    notes = input(f"Notes [{entry.get('notes', '')}]: ").strip()

                    updates = {}
                    if username: updates['username'] = username
                    if password: updates['password'] = password
                    if url: updates['url'] = url
                    if notes: updates['notes'] = notes

                    if updates:
                        pm.edit_entry(name, **updates)
                        print("Entry updated successfully!")
                    else:
                        print("No changes made.")

                elif choice == '3':
                    name = input("Entry name to delete: ").strip()
                    confirm = input(f"Are you sure you want to delete '{name}'? (y/n): ").strip().lower()
                    if confirm == 'y':
                        pm.delete_entry(name)
                        print("Entry deleted successfully!")

                elif choice == '4':
                    name = input("Entry name to view: ").strip()
                    entry = pm.get_entry(name)
                    print(f"\n--- {name} ---")
                    print(f"Username: {entry['username']}")
                    print(f"Password: {entry['password']}")
                    print(f"URL: {entry.get('url', 'N/A')}")
                    print(f"Notes: {entry.get('notes', 'N/A')}")
                    print(f"Created: {entry.get('created', 'Unknown')}")
                    print(f"Modified: {entry.get('modified', 'Unknown')}")

                elif choice == '5':
                    entries = pm.list_entries()
                    if entries:
                        print("\nStored entries:")
                        for entry in entries:
                            print(f"  - {entry}")
                    else:
                        print("No entries stored.")

                elif choice == '6':
                    length = input("Password length [20]: ").strip()
                    length = int(length) if length else 20
                    special = input("Include special characters? (y/n) [y]: ").strip().lower() != 'n'
                    password = pm.generate_password(length, special)
                    print(f"Generated password: {password}")

                elif choice == '7':
                    print("Exiting password manager. Stay secure!")
                    break

                else:
                    print("Invalid choice. Please enter 1-7.")

            except ValueError as e:
                print(f"Error: {e}")
            except EntryNotFoundError as e:
                print(f"Error: {e}")
            except StorageError as e:
                print(f"Storage error: {e}")

    except AuthenticationError as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nExiting password manager.")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()