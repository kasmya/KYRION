from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import getpass
import os
import secrets

class PasswordManager:
    def __init__(self, master_password: str, salt: bytes = None):
        """
        Initialize the password manager with a master password.
        
        :param master_password: The master password for the password manager.
        :param salt: The salt for the key derivation function.
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        self.salt = salt
        self.key = self._derive_key(master_password, salt)
        self.passwords = {}

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive a key from a password using PBKDF2HMAC.
        
        :param password: The password to derive the key from.
        :param salt: The salt for the key derivation function.
        :return: The derived key.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(password.encode())

    def _encrypt(self, plaintext: bytes) -> bytes:
        """
        Encrypt the plaintext using AES-256-CBC.
        
        :param plaintext: The plaintext to encrypt.
        :return: The encrypted ciphertext.
        """
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(secrets.token_bytes(16)), backend=default_backend())
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        return encryptor.update(padded_data) + encryptor.finalize()

    def _decrypt(self, ciphertext: bytes) -> bytes:
        """
        Decrypt the ciphertext using AES-256-CBC.
        
        :param ciphertext: The ciphertext to decrypt.
        :return: The decrypted plaintext.
        """
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(ciphertext[:16]), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded_data = decryptor.update(ciphertext[16:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(decrypted_padded_data) + unpadder.finalize()

    def add_password(self, account: str, password: str) -> None:
        """
        Add a new password entry.
        
        :param account: The account for the password entry.
        :param password: The password for the password entry.
        """
        self.passwords[account] = self._encrypt(password.encode())

    def edit_password(self, account: str, new_password: str) -> None:
        """
        Edit an existing password entry.
        
        :param account: The account for the password entry.
        :param new_password: The new password for the password entry.
        """
        if account in self.passwords:
            self.passwords[account] = self._encrypt(new_password.encode())
        else:
            raise ValueError("Account not found")

    def delete_password(self, account: str) -> None:
        """
        Delete a password entry.
        
        :param account: The account for the password entry.
        """
        if account in self.passwords:
            del self.passwords[account]
        else:
            raise ValueError("Account not found")

    def get_password(self, account: str) -> str:
        """
        Get the password for a given account.
        
        :param account: The account for the password entry.
        :return: The password for the account.
        """
        if account in self.passwords:
            return self._decrypt(self.passwords[account]).decode()
        else:
            raise ValueError("Account not found")

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a new password.
        
        :param length: The length of the password.
        :return: The generated password.
        """
        return ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()') for _ in range(length))

def main() -> None:
    master_password = getpass.getpass("Enter your master password: ")
    password_manager = PasswordManager(master_password)

    while True:
        print("1. Add password")
        print("2. Edit password")
        print("3. Delete password")
        print("4. Get password")
        print("5. Generate password")
        print("6. Exit")
        choice = input("Choose an option: ")

        if choice == "1":
            account = input("Enter the account: ")
            password = getpass.getpass("Enter the password: ")
            password_manager.add_password(account, password)
        elif choice == "2":
            account = input("Enter the account: ")
            new_password = getpass.getpass("Enter the new password: ")
            password_manager.edit_password(account, new_password)
        elif choice == "3":
            account = input("Enter the account: ")
            password_manager.delete_password(account)
        elif choice == "4":
            account = input("Enter the account: ")
            try:
                print(password_manager.get_password(account))
            except ValueError as e:
                print(e)
        elif choice == "5":
            length = int(input("Enter the length of the password (default=12): ") or 12)
            print(password_manager.generate_password(length))
        elif choice == "6":
            break
        else:
            print("Invalid option")

if __name__ == "__main__":
    main()