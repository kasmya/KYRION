from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import getpass
import hashlib
import os
import secrets
import string

class PasswordManager:
    def __init__(self, master_password: str, salt: bytes):
        """
        Initialize the password manager with a master password and salt.

        Args:
            master_password (str): The master password for authentication.
            salt (bytes): The salt for key derivation.
        """
        self.master_password = master_password
        self.salt = salt
        self.key = self._derive_key(master_password, salt)
        self.cipher = Cipher(algorithms.AES(self.key), modes.ECB(), backend=default_backend())
        self.passwords = {}

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive a key from a password and salt using PBKDF2.

        Args:
            password (str): The password to derive a key from.
            salt (bytes): The salt for key derivation.

        Returns:
            bytes: The derived key.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(password.encode())

    def _encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt a plaintext using the derived key.

        Args:
            plaintext (str): The plaintext to encrypt.

        Returns:
            bytes: The encrypted ciphertext.
        """
        encryptor = self.cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext.encode()) + padder.finalize()
        return encryptor.update(padded_data) + encryptor.finalize()

    def _decrypt(self, ciphertext: bytes) -> str:
        """
        Decrypt a ciphertext using the derived key.

        Args:
            ciphertext (bytes): The ciphertext to decrypt.

        Returns:
            str: The decrypted plaintext.
        """
        decryptor = self.cipher.decryptor()
        decrypted_padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(decrypted_padded_data) + unpadder.finalize()

    def add_password(self, name: str, password: str) -> None:
        """
        Add a new password entry.

        Args:
            name (str): The name of the password entry.
            password (str): The password to store.
        """
        self.passwords[name] = self._encrypt(password)

    def edit_password(self, name: str, new_password: str) -> None:
        """
        Edit an existing password entry.

        Args:
            name (str): The name of the password entry.
            new_password (str): The new password to store.
        """
        if name in self.passwords:
            self.passwords[name] = self._encrypt(new_password)
        else:
            raise ValueError("Password entry not found")

    def delete_password(self, name: str) -> None:
        """
        Delete a password entry.

        Args:
            name (str): The name of the password entry.
        """
        if name in self.passwords:
            del self.passwords[name]
        else:
            raise ValueError("Password entry not found")

    def get_password(self, name: str) -> str:
        """
        Get a stored password.

        Args:
            name (str): The name of the password entry.

        Returns:
            str: The stored password.
        """
        if name in self.passwords:
            return self._decrypt(self.passwords[name]).decode()
        else:
            raise ValueError("Password entry not found")

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a random password.

        Args:
            length (int): The length of the password. Defaults to 12.

        Returns:
            str: The generated password.
        """
        characters = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(characters) for _ in range(length))

def main() -> None:
    salt = secrets.token_bytes(16)
    master_password = getpass.getpass("Enter master password: ")
    pm = PasswordManager(master_password, salt)

    while True:
        print("1. Add password")
        print("2. Edit password")
        print("3. Delete password")
        print("4. Get password")
        print("5. Generate password")
        print("6. Quit")

        choice = input("Choose an option: ")

        if choice == "1":
            name = input("Enter password name: ")
            password = getpass.getpass("Enter password: ")
            pm.add_password(name, password)
        elif choice == "2":
            name = input("Enter password name: ")
            new_password = getpass.getpass("Enter new password: ")
            pm.edit_password(name, new_password)
        elif choice == "3":
            name = input("Enter password name: ")
            pm.delete_password(name)
        elif choice == "4":
            name = input("Enter password name: ")
            print(pm.get_password(name))
        elif choice == "5":
            length = int(input("Enter password length (default 12): ") or 12)
            print(pm.generate_password(length))
        elif choice == "6":
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()