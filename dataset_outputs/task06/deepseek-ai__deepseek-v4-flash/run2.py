#!/usr/bin/env python3
"""
Password Manager
Securely stores passwords using AES encryption (via Fernet).
Supports master password authentication, CRUD operations, and password generation.
"""

import argparse
import json
import os
import secrets
import string
import sys
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SALT_LENGTH = 16
KEY_LENGTH = 32
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
VAULT_FILE = "vault.pm"
VERIFICATION_PLAINTEXT = b"vault_ok"


class PasswordManager:
    """Manages encrypted password vault."""

    def __init__(self, vault_file: str = VAULT_FILE) -> None:
        self.vault_file = vault_file
        self.salt: Optional[bytes] = None
        self.fernet: Optional[Fernet] = None
        self.entries: Dict[str, Dict[str, str]] = {}

    def _derive_key(self, master_password: str, salt: bytes) -> bytes:
        """Derive a 32-byte key from master password using scrypt."""
        kdf = Scrypt(
            salt=salt,
            length=KEY_LENGTH,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        return kdf.derive(master_password.encode("utf-8"))

    def _key_to_fernet(self, key_bytes: bytes) -> Fernet:
        """Convert raw key bytes to Fernet instance."""
        return Fernet(base64.urlsafe_b64encode(key_bytes))

    def initialize_vault(self, master_password: str) -> None:
        """Create a new vault with master password."""
        self.salt = os.urandom(SALT_LENGTH)
        key = self._derive_key(master_password, self.salt)
        self.fernet = self._key_to_fernet(key)
        # Store verification token
        verification_token = self.fernet.encrypt(VERIFICATION_PLAINTEXT)
        self.entries = {}
        self._save_vault(verification_token)

    def _save_vault(self, verification_token: Optional[bytes] = None) -> None:
        """Serialize and encrypt entries, then write to file."""
        if verification_token is None:
            verification_token = self.verification_token
        data = json.dumps(self.entries, ensure_ascii=False).encode("utf-8")
        encrypted_data = self.fernet.encrypt(data)
        vault_content = {
            "salt": self.salt,
            "verification": verification_token,
            "data": encrypted_data,
        }
        # Use a temp file and replace for atomicity
        temp_file = self.vault_file + ".tmp"
        try:
            with open(temp_file, "wb") as f:
                # Write as pickle? Not needed. Use JSON with base64 bytes.
                # Simpler: use json.dumps with base64 encoding
                import base64
                serialized = json.dumps({
                    "salt": base64.b64encode(self.salt).decode("ascii"),
                    "verification": base64.b64encode(verification_token).decode("ascii"),
                    "data": base64.b64encode(encrypted_data).decode("ascii"),
                })
                f.write(serialized.encode("utf-8"))
            os.replace(temp_file, self.vault_file)
        except Exception as e:
            # Cleanup temp file on error
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise RuntimeError(f"Failed to save vault: {e}")

    def load_vault(self, master_password: str) -> bool:
        """Load and decrypt vault. Returns True if successful, False otherwise."""
        if not os.path.exists(self.vault_file):
            return False
        try:
            with open(self.vault_file, "rb") as f:
                raw = f.read().decode("utf-8")
            import base64
            content = json.loads(raw)
            self.salt = base64.b64decode(content["salt"])
            verification_token = base64.b64decode(content["verification"])
            encrypted_data = base64.b64decode(content["data"])
        except (json.JSONDecodeError, KeyError, base64.binascii.Error) as e:
            raise RuntimeError(f"Corrupted vault file: {e}")

        key = self._derive_key(master_password, self.salt)
        self.fernet = self._key_to_fernet(key)

        # Verify master password by decrypting verification token
        try:
            decrypted_verification = self.fernet.decrypt(verification_token)
            if decrypted_verification != VERIFICATION_PLAINTEXT:
                return False
        except InvalidToken:
            return False

        # Decrypt entries
        try:
            decrypted_data = self.fernet.decrypt(encrypted_data)
            self.entries = json.loads(decrypted_data.decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to decrypt vault: {e}")

        self.verification_token = verification_token
        return True

    def add_entry(self, service: str, username: str, password: str, notes: str = "") -> None:
        """Add a new entry. Raises ValueError if service already exists."""
        if service in self.entries:
            raise ValueError(f"Entry '{service}' already exists. Use edit instead.")
        self.entries[service] = {
            "username": username,
            "password": password,
            "notes": notes,
        }
        self._save_vault()

    def edit_entry(self, service: str, username: Optional[str] = None,
                   password: Optional[str] = None, notes: Optional[str] = None) -> None:
        """Modify an existing entry. Raises KeyError if service not found."""
        if service not in self.entries:
            raise KeyError(f"No entry found for '{service}'")
        entry = self.entries[service]
        if username is not None:
            entry["username"] = username
        if password is not None:
            entry["password"] = password
        if notes is not None:
            entry["notes"] = notes
        self._save_vault()

    def delete_entry(self, service: str) -> None:
        """Delete an entry. Raises KeyError if service not found."""
        if service not in self.entries:
            raise KeyError(f"No entry found for '{service}'")
        del self.entries[service]
        self._save_vault()

    def get_entry(self, service: str) -> Optional[Dict[str, str]]:
        """Return entry dict or None."""
        return self.entries.get(service)

    def list_services(self) -> list:
        """Return sorted list of service names."""
        return sorted(self.entries.keys())

    def display_entry(self, service: str) -> None:
        """Print entry details."""
        entry = self.get_entry(service)
        if entry:
            print(f"Service: {service}")
            print(f"Username: {entry['username']}")
            print(f"Password: {entry['password']}")
            if entry.get("notes"):
                print(f"Notes: {entry['notes']}")
        else:
            print(f"No entry found for '{service}'")


def generate_password(length: int = 16, use_digits: bool = True,
                      use_special: bool = True) -> str:
    """Generate a cryptographically random password."""
    characters = string.ascii_letters
    if use_digits:
        characters += string.digits
    if use_special:
        characters += string.punctuation

    if length < 1:
        raise ValueError("Password length must be at least 1")

    password = ''.join(secrets.choice(characters) for _ in range(length))

    # Ensure at least one character from each selected category
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password) if use_digits else True
    has_special = any(c in string.punctuation for c in password) if use_special else True

    # If missing, replace a random position with a required character
    if not (has_lower and has_upper and has_digit and has_special):
        password_list = list(password)
        if not has_lower:
            password_list[secrets.randbelow(length)] = secrets.choice(string.ascii_lowercase)
        if not has_upper:
            password_list[secrets.randbelow(length)] = secrets.choice(string.ascii_uppercase)
        if use_digits and not has_digit:
            password_list[secrets.randbelow(length)] = secrets.choice(string.digits)
        if use_special and not has_special:
            password_list[secrets.randbelow(length)] = secrets.choice(string.punctuation)
        password = ''.join(password_list)

    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Password Manager")
    parser.add_argument("action", choices=["init", "add", "edit", "delete", "get", "list", "generate"],
                        help="Action to perform")
    parser.add_argument("--service", help="Service name")
    parser.add_argument("--username", help="Username")
    parser.add_argument("--password", help="Password")
    parser.add_argument("--notes", help="Notes", default="")
    parser.add_argument("--length", type=int, default=16, help="Generated password length")
    parser.add_argument("--no-digits", action="store_true", help="Exclude digits in generated password")
    parser.add_argument("--no-special", action="store_true", help="Exclude special characters")
    args = parser.parse_args()

    pm = PasswordManager()

    if args.action == "init":
        if os.path.exists(VAULT_FILE):
            print("Vault already exists. Delete it first if you want to reinitialize.")
            sys.exit(1)
        master_pw = input("Enter new master password: ")
        confirm = input("Confirm master password: ")
        if master_pw != confirm:
            print("Passwords do not match.")
            sys.exit(1)
        pm.initialize_vault(master_pw)
        print("Vault initialized successfully.")
        return

    # All other actions require an existing vault and master password
    if not os.path.exists(VAULT_FILE):
        print("No vault found. First run 'init' to create one.")
        sys.exit(1)

    master_pw = input("Enter master password: ")
    if not pm.load_vault(master_pw):
        print("Incorrect master password.")
        sys.exit(1)

    if args.action == "add":
        service = args.service
        if not service:
            print("--service is required for add.")
            sys.exit(1)
        username = args.username or input("Username: ")
        password = args.password
        if not password:
            generate = input("Generate a strong password? (y/n): ").lower().startswith('y')
            if generate:
                password = generate_password(args.length, not args.no_digits, not args.no_special)
                print(f"Generated password: {password}")
            else:
                password = input("Password: ")
        notes = args.notes or input("Notes (optional): ")
        try:
            pm.add_entry(service, username, password, notes)
            print(f"Added entry for '{service}'.")
        except ValueError as e:
            print(e)
            sys.exit(1)

    elif args.action == "edit":
        service = args.service
        if not service:
            print("--service is required for edit.")
            sys.exit(1)
        existing = pm.get_entry(service)
        if not existing:
            print(f"No entry for '{service}'.")
            sys.exit(1)
        print("Leave blank to keep current value.")
        username = input(f"Username [{existing['username']}]: ") or existing['username']
        password = input(f"Password [{existing['password']}]: ") or existing['password']
        notes = input(f"Notes [{existing.get('notes','')}]: ") or existing.get('notes', '')
        try:
            pm.edit_entry(service, username=username, password=password, notes=notes)
            print(f"Updated entry for '{service}'.")
        except KeyError as e:
            print(e)
            sys.exit(1)

    elif args.action == "delete":
        service = args.service
        if not service:
            print("--service is required for delete.")
            sys.exit(1)
        confirm = input(f"Delete entry for '{service}'? (y/n): ")
        if confirm.lower() == 'y':
            try:
                pm.delete_entry(service)
                print(f"Deleted entry for '{service}'.")
            except KeyError as e:
                print(e)
                sys.exit(1)

    elif args.action == "get":
        service = args.service
        if not service:
            print("--service is required for get.")
            sys.exit(1)
        pm.display_entry(service)

    elif args.action == "list":
        services = pm.list_services()
        if services:
            print("Stored services:")
            for s in services:
                print(f"  - {s}")
        else:
            print("No entries in vault.")

    elif args.action == "generate":
        password = generate_password(args.length, not args.no_digits, not args.no_special)
        print(password)


if __name__ == "__main__":
    main()