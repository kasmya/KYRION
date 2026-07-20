import json
import os
import secrets
import string
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
_STORAGE_FILE = "vault.json"
_SALT_SIZE = 16
_DERIVED_KEY_LENGTH = 32  # 256 bits for Fernet
_PBKDF2_ITERATIONS = 100_000  # Adjust for your security/performance needs
_DEFAULT_PASSWORD_LENGTH = 16


# ------------------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------------------
class PasswordManagerError(Exception):
    """Base exception for password manager errors."""


class AuthenticationError(PasswordManagerError):
    """Raised when master password is incorrect."""


class EntryNotFoundError(PasswordManagerError):
    """Raised when an entry is not found."""


class VaultCorruptedError(PasswordManagerError):
    """Raised when the vault file is corrupted or tampered."""


# ------------------------------------------------------------------------------
# Key derivation utility
# ------------------------------------------------------------------------------
def _derive_key(master_password: str, salt: bytes) -> bytes:
    """Derive a 32-byte key from the master password and salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_DERIVED_KEY_LENGTH,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(master_password.encode("utf-8"))


# ------------------------------------------------------------------------------
# Password manager class
# ------------------------------------------------------------------------------
class PasswordManager:
    """A secure password manager with AES-256 encryption (via Fernet).

    Passwords are encrypted and stored in a local JSON file. Access is protected
    by a master password. The vault file is integrity-protected using the HMAC
    built into Fernet.

    Usage::

        pm = PasswordManager()
        pm.create_vault("my_master_password")  # first time only
        pm.unlock("my_master_password")
        pm.add_entry("example.com", "myuser", "myp@ssw0rd")
        print(pm.get_entry("example.com"))
    """

    def __init__(self, vault_path: Union[str, Path] = _STORAGE_FILE) -> None:
        """Initialize manager with path to vault file.

        Args:
            vault_path: Path to the encrypted vault file (default: ``vault.json``).
        """
        self._vault_path = Path(vault_path)
        self._cipher: Optional[Fernet] = None
        self._data: Dict[str, Dict[str, str]] = {}  # {service: {"username": ..., "password": ...}}

    # --------------------------------------------------------------------------
    # Public API: vault management
    # --------------------------------------------------------------------------
    def create_vault(self, master_password: str) -> None:
        """Create a new vault file with the given master password.

        If the vault already exists, this operation is disallowed to prevent
        accidental overwrites. Delete the file manually if you want to re‑initialize.

        Args:
            master_password: The master password to protect the vault.
                Must be non-empty.

        Raises:
            FileExistsError: If the vault file already exists.
            ValueError: If master_password is empty.
        """
        if not master_password:
            raise ValueError("Master password cannot be empty.")

        if self._vault_path.exists():
            raise FileExistsError(
                f"Vault file '{self._vault_path}' already exists. "
                "Delete it first if you want to re‑initialize."
            )

        # Generate random salt and derive key
        salt = os.urandom(_SALT_SIZE)
        key = _derive_key(master_password, salt)
        fernet = Fernet(self._to_base64(key))

        # Create empty data and encrypt
        data = {}
        serialized = json.dumps(data).encode("utf-8")
        encrypted = fernet.encrypt(serialized)

        # Store salt + encrypted payload
        vault_content = {
            "salt": salt.hex(),
            "encrypted_data": encrypted.decode("utf-8"),
        }
        self._vault_path.write_text(json.dumps(vault_content, indent=2))
        self._cipher = fernet
        self._data = data

    def unlock(self, master_password: str) -> None:
        """Unlock the vault with the master password.

        Args:
            master_password: The master password to authenticate against the vault.

        Raises:
            FileNotFoundError: If the vault file does not exist.
            AuthenticationError: If the master password is wrong.
            VaultCorruptedError: If the vault file is malformed or tampered.
        """
        if not self._vault_path.exists():
            raise FileNotFoundError(
                f"Vault file '{self._vault_path}' not found. "
                "Use create_vault() first."
            )

        try:
            vault_content = json.loads(self._vault_path.read_text())
            salt = bytes.fromhex(vault_content["salt"])
            encrypted_data = vault_content["encrypted_data"].encode("utf-8")
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise VaultCorruptedError("Vault file is malformed.") from exc

        # Derive key and attempt decryption
        key = _derive_key(master_password, salt)
        fernet = Fernet(self._to_base64(key))
        try:
            decrypted = fernet.decrypt(encrypted_data)
        except Exception as exc:
            raise AuthenticationError("Incorrect master password.") from exc

        # Parse the data
        try:
            self._data = json.loads(decrypted.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise VaultCorruptedError("Decrypted data is corrupted.") from exc

        self._cipher = fernet

    # --------------------------------------------------------------------------
    # Public API: entry management
    # --------------------------------------------------------------------------
    def add_entry(self, service: str, username: str, password: str) -> None:
        """Add a new password entry for a service.

        If the service already exists, the entry is overwritten (use update instead).

        Args:
            service: Name of the service (e.g., 'example.com').
            username: Username or email.
            password: Password to store.

        Raises:
            RuntimeError: If vault is not unlocked.
        """
        self._require_unlocked()
        self._data[service] = {"username": username, "password": password}
        self._save()

    def get_entry(self, service: str) -> Dict[str, str]:
        """Retrieve a stored entry by service name.

        Args:
            service: The service name.

        Returns:
            A dict with keys 'username' and 'password'.

        Raises:
            RuntimeError: If vault is not unlocked.
            EntryNotFoundError: If the service does not exist.
        """
        self._require_unlocked()
        if service not in self._data:
            raise EntryNotFoundError(f"No entry found for '{service}'.")
        return dict(self._data[service])

    def edit_entry(self, service: str, username: Optional[str] = None,
                   password: Optional[str] = None) -> Dict[str, str]:
        """Update an existing entry's username and/or password.

        At least one of ``username`` or ``password`` must be provided.
        If a field is ``None`` it will remain unchanged.

        Args:
            service: The service name to update.
            username: New username (or None to keep).
            password: New password (or None to keep).

        Returns:
            The updated entry.

        Raises:
            RuntimeError: If vault is not unlocked.
            EntryNotFoundError: If the service does not exist.
            ValueError: If neither username nor password is provided.
        """
        self._require_unlocked()
        if service not in self._data:
            raise EntryNotFoundError(f"No entry found for '{service}'.")
        if username is None and password is None:
            raise ValueError("At least one of username or password must be provided.")

        entry = self._data[service]
        if username is not None:
            entry["username"] = username
        if password is not None:
            entry["password"] = password
        self._data[service] = entry
        self._save()
        return dict(entry)

    def delete_entry(self, service: str) -> None:
        """Delete a password entry.

        Args:
            service: The service name to delete.

        Raises:
            RuntimeError: If vault is not unlocked.
            EntryNotFoundError: If the service does not exist.
        """
        self._require_unlocked()
        if service not in self._data:
            raise EntryNotFoundError(f"No entry found for '{service}'.")
        del self._data[service]
        self._save()

    def list_entries(self) -> List[str]:
        """Return a list of all service names stored in the vault.

        Returns:
            List of service names (sorted).

        Raises:
            RuntimeError: If vault is not unlocked.
        """
        self._require_unlocked()
        return sorted(self._data.keys())

    # --------------------------------------------------------------------------
    # Public API: password generation
    # --------------------------------------------------------------------------
    @staticmethod
    def generate_password(length: int = _DEFAULT_PASSWORD_LENGTH,
                          use_digits: bool = True,
                          use_punctuation: bool = True) -> str:
        """Generate a cryptographically secure random password.

        Args:
            length: Length of the password (default 16).
            use_digits: Include digits (0-9).
            use_punctuation: Include special characters (punctuation).

        Returns:
            A randomly generated password string.

        Raises:
            ValueError: If length is less than 4.
        """
        if length < 4:
            raise ValueError("Password length must be at least 4.")

        # Build character pool
        pool = string.ascii_letters  # always include uppercase + lowercase
        if use_digits:
            pool += string.digits
        if use_punctuation:
            pool += string.punctuation

        # Ensure at least one from each selected category for better randomness
        password = []
        if use_digits:
            password.append(secrets.choice(string.digits))
        if use_punctuation:
            password.append(secrets.choice(string.punctuation))
        # Fill the rest
        password += [secrets.choice(pool) for _ in range(length - len(password))]
        secrets.SystemRandom().shuffle(password)  # shuffle to avoid predictable prefix
        return "".join(password)

    # --------------------------------------------------------------------------
    # Private helpers
    # --------------------------------------------------------------------------
    def _require_unlocked(self) -> None:
        """Check if vault is unlocked, else raise RuntimeError."""
        if self._cipher is None:
            raise RuntimeError("Vault is locked. Call unlock() first.")

    def _save(self) -> None:
        """Encrypt current data and write to vault file."""
        serialized = json.dumps(self._data, indent=2).encode("utf-8")
        encrypted = self._cipher.encrypt(serialized)

        # Read existing salt (must still be there)
        try:
            vault_content = json.loads(self._vault_path.read_text())
            salt = vault_content["salt"]
        except (KeyError, json.JSONDecodeError) as exc:
            raise VaultCorruptedError("Vault file is malformed during save.") from exc

        vault_content["encrypted_data"] = encrypted.decode("utf-8")
        self._vault_path.write_text(json.dumps(vault_content, indent=2))

    @staticmethod
    def _to_base64(key: bytes) -> str:
        """Convert a 32-byte key to a base64-encoded string (Fernet format)."""
        from base64 import urlsafe_b64encode
        return urlsafe_b64encode(key).decode("utf-8")