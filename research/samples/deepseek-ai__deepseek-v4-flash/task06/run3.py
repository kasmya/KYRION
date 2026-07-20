import os
import json
import base64
import secrets
import string
from typing import Optional, List, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend


class PasswordManager:
    """
    A secure password manager that stores encrypted passwords using AES (Fernet).
    Master password authentication is enforced via PBKDF2 key derivation.
    """

    SALT_LENGTH = 16
    KEY_LENGTH = 32
    ITERATIONS = 100_000
    DATA_FILE_EXT = ".json"
    SALT_FILE_EXT = ".salt"

    def __init__(self, master_password: str, file_path: str = "passwords.json") -> None:
        """
        Initialize the password manager.

        Args:
            master_password: The master password used to derive the encryption key.
            file_path: Path to the encrypted password storage file.

        Raises:
            ValueError: If file_path does not end with .json.
        """
        if not file_path.endswith(self.DATA_FILE_EXT):
            raise ValueError("Data file must have .json extension")
        self._file_path = file_path
        self._salt_path = file_path.replace(self.DATA_FILE_EXT, self.SALT_FILE_EXT)

        # Derive the key using the master password and stored salt.
        self._salt = self._load_or_create_salt()
        self._key = self._derive_key(master_password)
        self._fernet = Fernet(self._key)

    def _load_or_create_salt(self) -> bytes:
        """Load existing salt from file or create a new one and save it."""
        try:
            with open(self._salt_path, "rb") as f:
                salt = f.read()
            if len(salt) != self.SALT_LENGTH:
                raise ValueError("Corrupted salt file")
        except (FileNotFoundError, ValueError):
            salt = os.urandom(self.SALT_LENGTH)
            with open(self._salt_path, "wb") as f:
                f.write(salt)
        return salt

    def _derive_key(self, master_password: str) -> bytes:
        """Derive a 32-byte encryption key from the master password using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=self._salt,
            iterations=self.ITERATIONS,
            backend=default_backend(),
        )
        return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))

    def _load_entries(self) -> Dict[str, Dict[str, str]]:
        """
        Load and decrypt the password entries from the data file.

        Returns:
            A dictionary mapping site names to entries containing 'username' and 'password'.

        Raises:
            PermissionError: If the decryption fails (wrong master password or tampered data).
        """
        try:
            with open(self._file_path, "rb") as f:
                encrypted_data = f.read()
            if not encrypted_data:
                return {}
            decrypted_data = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except FileNotFoundError:
            return {}
        except Exception as e:
            raise PermissionError(
                "Failed to decrypt data. Check master password or file integrity."
            ) from e

    def _save_entries(self, entries: Dict[str, Dict[str, str]]) -> None:
        """Encrypt and save the password entries to the data file."""
        json_data = json.dumps(entries, indent=2).encode()
        encrypted_data = self._fernet.encrypt(json_data)
        with open(self._file_path, "wb") as f:
            f.write(encrypted_data)

    def add_entry(self, site: str, username: str, password: Optional[str] = None) -> str:
        """
        Add a new entry. If no password is provided, a secure random one is generated.

        Args:
            site: The service or site name (unique key).
            username: The username for the account.
            password: Optional plaintext password. If omitted, a 20-character password is generated.

        Returns:
            The password (generated or provided) in plaintext.

        Raises:
            ValueError: If an entry for this site already exists.
        """
        if not password:
            password = self.generate_password()
        entries = self._load_entries()
        if site in entries:
            raise ValueError(f"Entry for '{site}' already exists. Use edit_entry to modify.")
        encrypted_password = self._encrypt_password(password)
        entries[site] = {"username": username, "password": encrypted_password}
        self._save_entries(entries)
        return password

    def get_entry(self, site: str) -> Optional[Dict[str, str]]:
        """
        Retrieve a password entry for the given site.

        Args:
            site: The site name.

        Returns:
            A dict with keys 'username' and 'password' (decrypted), or None if not found.
        """
        entries = self._load_entries()
        if site not in entries:
            return None
        entry = entries[site]
        return {
            "username": entry["username"],
            "password": self._decrypt_password(entry["password"]),
        }

    def edit_entry(
        self, site: str, username: Optional[str] = None, password: Optional[str] = None
    ) -> bool:
        """
        Edit an existing entry. Only provided fields are updated.

        Args:
            site: The site name to edit.
            username: New username (optional).
            password: New password (optional). If omitted, the password remains unchanged.

        Returns:
            True if the entry was found and updated, False otherwise.
        """
        entries = self._load_entries()
        if site not in entries:
            return False
        if username is not None:
            entries[site]["username"] = username
        if password is not None:
            entries[site]["password"] = self._encrypt_password(password)
        self._save_entries(entries)
        return True

    def delete_entry(self, site: str) -> bool:
        """
        Delete an entry by site name.

        Args:
            site: The site name to remove.

        Returns:
            True if deleted, False if not found.
        """
        entries = self._load_entries()
        if site not in entries:
            return False
        del entries[site]
        self._save_entries(entries)
        return True

    def list_entries(self) -> List[str]:
        """Return a list of all stored site names."""
        entries = self._load_entries()
        return list(entries.keys())

    @staticmethod
    def generate_password(length: int = 20) -> str:
        """
        Generate a cryptographically secure random password.

        Args:
            length: Length of the password (default 20).

        Returns:
            A string containing random characters (uppercase, lowercase, digits, punctuation).
        """
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _encrypt_password(self, plaintext: str) -> str:
        """Encrypt a plaintext password and return a base64-encoded string."""
        return base64.urlsafe_b64encode(self._fernet.encrypt(plaintext.encode())).decode()

    def _decrypt_password(self, encrypted: str) -> str:
        """Decrypt a base64-encoded encrypted password and return plaintext."""
        return self._fernet.decrypt(base64.urlsafe_b64decode(encrypted)).decode()


def main() -> None:
    """Simple CLI interface for the password manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Secure Password Manager")
    parser.add_argument("master_password", help="Master password")
    parser.add_argument("command", choices=["add", "get", "edit", "delete", "list", "gen"])
    parser.add_argument("--site", help="Site name")
    parser.add_argument("--username", help="Username")
    parser.add_argument("--password", help="Password (optional)")
    parser.add_argument("--file", default="passwords.json", help="Data file path")
    args = parser.parse_args()

    pm = PasswordManager(args.master_password, args.file)

    if args.command == "add":
        if not args.site or not args.username:
            print("Error: --site and --username are required for add")
            return
        try:
            pwd = pm.add_entry(args.site, args.username, args.password)
            print(f"Password for '{args.site}': {pwd}")
        except ValueError as e:
            print(f"Error: {e}")

    elif args.command == "get":
        if not args.site:
            print("Error: --site is required for get")
            return
        entry = pm.get_entry(args.site)
        if entry:
            print(f"Username: {entry['username']}")
            print(f"Password: {entry['password']}")
        else:
            print(f"No entry found for site '{args.site}'")

    elif args.command == "edit":
        if not args.site:
            print("Error: --site is required for edit")
            return
        success = pm.edit_entry(args.site, args.username, args.password)
        if success:
            print(f"Entry for '{args.site}' updated.")
        else:
            print(f"No entry found for site '{args.site}'")

    elif args.command == "delete":
        if not args.site:
            print("Error: --site is required for delete")
            return
        success = pm.delete_entry(args.site)
        if success:
            print(f"Entry for '{args.site}' deleted.")
        else:
            print(f"No entry found for site '{args.site}'")

    elif args.command == "list":
        sites = pm.list_entries()
        if sites:
            print("Stored sites:")
            for s in sites:
                print(f"  - {s}")
        else:
            print("No entries stored.")

    elif args.command == "gen":
        length = 20
        if args.password:
            try:
                length = int(args.password)
            except ValueError:
                print("Invalid length, using default 20")
        print(pm.generate_password(length))


if __name__ == "__main__":
    main()