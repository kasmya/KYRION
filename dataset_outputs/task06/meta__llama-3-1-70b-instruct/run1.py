from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import os
import getpass
import secrets

class PasswordManager:
    def __init__(self, master_password: str, salt: bytes = None) -> None:
        """Initialize the password manager with a master password."""
        if salt is None:
            salt = os.urandom(16)
        self.salt = salt
        self.master_password = master_password
        self.kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        self.key = base64.urlsafe_b64encode(self.kdf.derive(master_password.encode()))
        self.iv = os.urandom(16)
        self.cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
        self.passwords = self.load_passwords()

    def load_passwords(self) -> dict:
        """Load the passwords from the storage file."""
        try:
            with open("passwords.dat", "rb") as f:
                encrypted_data = f.read()
            decryptor = self.cipher.decryptor()
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(encrypted_data) + padder.finalize()
            return eval(decryptor.update(padded_data) + decryptor.finalize())
        except FileNotFoundError:
            return {}

    def save_passwords(self) -> None:
        """Save the passwords to the storage file."""
        encryptor = self.cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        data = str(self.passwords).encode()
        padded_data = padder.update(data) + padder.finalize()
        with open("passwords.dat", "wb") as f:
            f.write(encryptor.update(padded_data) + encryptor.finalize())

    def add_password(self, name: str, password: str) -> None:
        """Add a new password entry."""
        self.passwords[name] = password
        self.save_passwords()

    def edit_password(self, name: str, password: str) -> None:
        """Edit an existing password entry."""
        if name in self.passwords:
            self.passwords[name] = password
            self.save_passwords()
        else:
            raise ValueError("Password entry not found")

    def delete_password(self, name: str) -> None:
        """Delete a password entry."""
        if name in self.passwords:
            del self.passwords[name]
            self.save_passwords()
        else:
            raise ValueError("Password entry not found")

    def generate_password(self, length: int = 12) -> str:
        """Generate a random password."""
        return secrets.token_urlsafe(length)

def main() -> None:
    """Main function."""
    master_password = getpass.getpass("Enter the master password: ")
    pm = PasswordManager(master_password)
    while True:
        print("1. Add password")
        print("2. Edit password")
        print("3. Delete password")
        print("4. Generate password")
        print("5. Quit")
        choice = input("Choose an option: ")
        if choice == "1":
            name = input("Enter the password name: ")
            password = getpass.getpass("Enter the password: ")
            pm.add_password(name, password)
        elif choice == "2":
            name = input("Enter the password name: ")
            password = getpass.getpass("Enter the new password: ")
            pm.edit_password(name, password)
        elif choice == "3":
            name = input("Enter the password name: ")
            pm.delete_password(name)
        elif choice == "4":
            length = int(input("Enter the password length: "))
            print(pm.generate_password(length))
        elif choice == "5":
            break
        else:
            print("Invalid option")

if __name__ == "__main__":
    main()