from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import getpass
import os
import secrets
import string

class PasswordManager:
    def __init__(self, master_password: str, salt: bytes = None):
        """
        Initialize the password manager with a master password.

        Args:
            master_password (str): The master password to secure the password manager.
            salt (bytes): The salt to use for key derivation. If None, a random salt will be generated.
        """
        if salt is None:
            salt = os.urandom(16)
        self.salt = salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        self.key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        self.fernet = Fernet(self.key)
        self.passwords = self.load_passwords()

    def load_passwords(self) -> dict:
        """
        Load the password database from the encrypted file.

        Returns:
            dict: The loaded password database.
        """
        if os.path.exists("passwords.dat"):
            with open("passwords.dat", "rb") as f:
                encrypted_data = f.read()
            try:
                decrypted_data = self.fernet.decrypt(encrypted_data)
                return eval(decrypted_data.decode())
            except Exception as e:
                print(f"Error loading passwords: {e}")
                return {}
        else:
            return {}

    def save_passwords(self) -> None:
        """
        Save the password database to the encrypted file.
        """
        encrypted_data = self.fernet.encrypt(str(self.passwords).encode())
        with open("passwords.dat", "wb") as f:
            f.write(encrypted_data)

    def authenticate(self, master_password: str) -> bool:
        """
        Authenticate the master password.

        Args:
            master_password (str): The master password to authenticate.

        Returns:
            bool: True if the master password is correct, False otherwise.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        return derived_key == self.key

    def add_password(self, service: str, username: str, password: str) -> None:
        """
        Add a new password entry.

        Args:
            service (str): The service name.
            username (str): The username.
            password (str): The password.
        """
        self.passwords[service] = {"username": username, "password": password}
        self.save_passwords()

    def edit_password(self, service: str, username: str, password: str) -> None:
        """
        Edit an existing password entry.

        Args:
            service (str): The service name.
            username (str): The username.
            password (str): The password.
        """
        if service in self.passwords:
            self.passwords[service] = {"username": username, "password": password}
            self.save_passwords()
        else:
            print("Service not found.")

    def delete_password(self, service: str) -> None:
        """
        Delete a password entry.

        Args:
            service (str): The service name.
        """
        if service in self.passwords:
            del self.passwords[service]
            self.save_passwords()
        else:
            print("Service not found.")

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a random password.

        Args:
            length (int): The password length. Defaults to 12.

        Returns:
            str: The generated password.
        """
        characters = string.ascii_letters + string.digits + string.punctuation
        password = "".join(secrets.choice(characters) for _ in range(length))
        return password

def main() -> None:
    master_password = getpass.getpass("Enter master password: ")
    password_manager = PasswordManager(master_password)

    while True:
        print("1. Add password")
        print("2. Edit password")
        print("3. Delete password")
        print("4. Generate password")
        print("5. Quit")
        choice = input("Enter choice: ")

        if choice == "1":
            service = input("Enter service: ")
            username = input("Enter username: ")
            password = input("Enter password: ")
            password_manager.add_password(service, username, password)
        elif choice == "2":
            service = input("Enter service: ")
            username = input("Enter username: ")
            password = input("Enter password: ")
            password_manager.edit_password(service, username, password)
        elif choice == "3":
            service = input("Enter service: ")
            password_manager.delete_password(service)
        elif choice == "4":
            length = int(input("Enter password length: "))
            print(password_manager.generate_password(length))
        elif choice == "5":
            break
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()