import os
import getpass
import hashlib
import base64
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from typing import Dict, Optional

class PasswordManager:
    def __init__(self, master_password: str) -> None:
        self.master_password = master_password
        self.passwords: Dict[str, str] = {}
        self.key = self.generate_key(master_password)
        self.cipher = Cipher(algorithms.AES(self.key), modes.ECB(), backend=default_backend())
        self.encryptor = self.cipher.encryptor()
        self.decryptor = self.cipher.decryptor()

    def generate_key(self, master_password: str) -> bytes:
        """
        Generate a key from the master password.
        """
        hashed_password = hashlib.sha256(master_password.encode()).digest()
        return hashed_password

    def encrypt(self, data: str) -> bytes:
        """
        Encrypt the data using AES encryption.
        """
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data.encode()) + padder.finalize()
        return self.encryptor.update(padded_data) + self.encryptor.finalize()

    def decrypt(self, encrypted_data: bytes) -> str:
        """
        Decrypt the encrypted data using AES decryption.
        """
        decrypted_padded_data = self.decryptor.update(encrypted_data) + self.decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(decrypted_padded_data) + unpadder.finalize()
        return data.decode()

    def add_password(self, service: str, password: str) -> None:
        """
        Add a password entry.
        """
        encrypted_password = self.encrypt(password)
        self.passwords[service] = base64.b64encode(encrypted_password).decode()

    def edit_password(self, service: str, new_password: str) -> None:
        """
        Edit a password entry.
        """
        if service in self.passwords:
            self.add_password(service, new_password)
        else:
            raise ValueError("Service not found")

    def delete_password(self, service: str) -> None:
        """
        Delete a password entry.
        """
        if service in self.passwords:
            del self.passwords[service]
        else:
            raise ValueError("Service not found")

    def get_password(self, service: str) -> Optional[str]:
        """
        Get a password entry.
        """
        if service in self.passwords:
            encrypted_password = base64.b64decode(self.passwords[service])
            return self.decrypt(encrypted_password)
        else:
            return None

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a random password.
        """
        import secrets
        import string
        return ''.join(secrets.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(length))

def main() -> None:
    master_password = getpass.getpass("Enter your master password: ")
    password_manager = PasswordManager(master_password)

    while True:
        print("1. Add password")
        print("2. Edit password")
        print("3. Delete password")
        print("4. Get password")
        print("5. Generate password")
        print("6. Quit")

        choice = input("Choose an option: ")

        if choice == "1":
            service = input("Enter the service: ")
            password = getpass.getpass("Enter the password: ")
            password_manager.add_password(service, password)
        elif choice == "2":
            service = input("Enter the service: ")
            new_password = getpass.getpass("Enter the new password: ")
            password_manager.edit_password(service, new_password)
        elif choice == "3":
            service = input("Enter the service: ")
            password_manager.delete_password(service)
        elif choice == "4":
            service = input("Enter the service: ")
            password = password_manager.get_password(service)
            if password:
                print("Password:", password)
            else:
                print("Service not found")
        elif choice == "5":
            length = int(input("Enter the password length (default is 12): ") or 12)
            print("Generated password:", password_manager.generate_password(length))
        elif choice == "6":
            break
        else:
            print("Invalid option")

if __name__ == "__main__":
    main()