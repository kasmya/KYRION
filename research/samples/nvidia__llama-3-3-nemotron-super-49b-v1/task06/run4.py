from typing import Dict, Tuple
from getpass import getpass
from hashlib import sha256
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from os import urandom, remove
import base64
import json
import argparse

class PasswordManager:
    def __init__(self, storage_file: str = "passwords.dat", key_file: str = "key.dat"):
        """
        Initialize the PasswordManager.

        :param storage_file: File to store encrypted passwords
        :param key_file: File to store the encrypted master key
        """
        self.storage_file = storage_file
        self.key_file = key_file
        self.master_key: bytes = None
        self.cipher: Cipher = None

    def _derive_key(self, master_password: str) -> bytes:
        """
        Derive a key from the master password using SHA-256.

        :param master_password: Master password
        :return: Derived key
        """
        return sha256(master_password.encode()).digest()

    def _encrypt(self, data: bytes) -> bytes:
        """
        Encrypt the given data using AES-CBC.

        :param data: Data to encrypt
        :return: Encrypted data
        """
        if not self.cipher:
            raise RuntimeError("Cipher not initialized")
        encryptor = self.cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        return encryptor.update(padded_data) + encryptor.finalize()

    def _decrypt(self, data: bytes) -> bytes:
        """
        Decrypt the given data using AES-CBC.

        :param data: Data to decrypt
        :return: Decrypted data
        """
        if not self.cipher:
            raise RuntimeError("Cipher not initialized")
        decryptor = self.cipher.decryptor()
        decrypted_padded_data = decryptor.update(data) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(decrypted_padded_data) + unpadder.finalize()

    def authenticate(self, master_password: str) -> None:
        """
        Authenticate using the master password.

        :param master_password: Master password
        """
        if self.key_file.exists():
            with open(self.key_file, "rb") as f:
                encrypted_master_key = f.read()
            self.master_key = self._decrypt(encrypted_master_key)
        else:
            self.master_key = self._derive_key(master_password)
            with open(self.key_file, "wb") as f:
                f.write(self._encrypt(self.master_key))

        self.cipher = Cipher(algorithms.AES(self.master_key), modes.CBC(urandom(16)), backend=default_backend())

    def load_passwords(self) -> Dict[str, str]:
        """
        Load passwords from the storage file.

        :return: Dictionary of passwords
        """
        if not self.storage_file.exists():
            return {}
        with open(self.storage_file, "rb") as f:
            encrypted_passwords = f.read()
        passwords = json.loads(self._decrypt(encrypted_passwords).decode())
        return passwords

    def save_passwords(self, passwords: Dict[str, str]) -> None:
        """
        Save passwords to the storage file.

        :param passwords: Dictionary of passwords
        """
        with open(self.storage_file, "wb") as f:
            f.write(self._encrypt(json.dumps(passwords).encode()))

    def add_password(self, service: str, password: str) -> None:
        """
        Add a password entry.

        :param service: Service name
        :param password: Password
        """
        passwords = self.load_passwords()
        passwords[service] = password
        self.save_passwords(passwords)

    def edit_password(self, service: str, new_password: str) -> None:
        """
        Edit a password entry.

        :param service: Service name
        :param new_password: New password
        """
        passwords = self.load_passwords()
        if service in passwords:
            passwords[service] = new_password
            self.save_passwords(passwords)
        else:
            raise ValueError(f"Service '{service}' not found")

    def delete_password(self, service: str) -> None:
        """
        Delete a password entry.

        :param service: Service name
        """
        passwords = self.load_passwords()
        if service in passwords:
            del passwords[service]
            self.save_passwords(passwords)
        else:
            raise ValueError(f"Service '{service}' not found")

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a random password.

        :param length: Password length
        :return: Generated password
        """
        characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"
        return "".join(urandom(1).hex() for _ in range(length))

def main():
    parser = argparse.ArgumentParser(description="Password Manager")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize the password manager")
    init_parser.add_argument("--master-password", help="Master password")

    add_parser = subparsers.add_parser("add", help="Add a password entry")
    add_parser.add_argument("--service", help="Service name")
    add_parser.add_argument("--password", help="Password")

    edit_parser = subparsers.add_parser("edit", help="Edit a password entry")
    edit_parser.add_argument("--service", help="Service name")
    edit_parser.add_argument("--new-password", help="New password")

    delete_parser = subparsers.add_parser("delete", help="Delete a password entry")
    delete_parser.add_argument("--service", help="Service name")

    generate_parser = subparsers.add_parser("generate", help="Generate a random password")
    generate_parser.add_argument("--length", type=int, default=12, help="Password length")

    args = parser.parse_args()

    manager = PasswordManager()

    if args.command == "init":
        if not args.master_password:
            args.master_password = getpass("Enter master password: ")
        manager.authenticate(args.master_password)
    elif args.command in ["add", "edit", "delete"]:
        master_password = getpass("Enter master password: ")
        manager.authenticate(master_password)
        if args.command == "add":
            if not args.service or not args.password:
                parser.error("Both --service and --password are required for 'add' command")
            manager.add_password(args.service, args.password)
        elif args.command == "edit":
            if not args.service or not args.new_password:
                parser.error("Both --service and --new-password are required for 'edit' command")
            manager.edit_password(args.service, args.new_password)
        elif args.command == "delete":
            if not args.service:
                parser.error("--service is required for 'delete' command")
            manager.delete_password(args.service)
    elif args.command == "generate":
        print(manager.generate_password(args.length))
    else:
        parser.error("No command specified")

if __name__ == "__main__":
    main()