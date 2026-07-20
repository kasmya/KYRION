import base64
import getpass
import hashlib
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import secrets
import string

class PasswordManager:
    """
    A secure password manager with AES encryption and master password authentication.
    """

    def __init__(self, master_password: str, salt: bytes = None):
        """
        Initialize the password manager with a master password.

        :param master_password: The master password to encrypt and decrypt passwords.
        :param salt: The salt to use for key derivation. If None, a random salt will be generated.
        """
        self.master_password = master_password
        self.salt = salt or os.urandom(16)
        self.kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
            backend=default_backend()
        )
        self.key = base64.urlsafe_b64encode(self.kdf.derive(self.master_password.encode()))
        self.f = Fernet(self.key)

    def add_password(self, name: str, password: str) -> None:
        """
        Add a new password entry.

        :param name: The name of the password entry.
        :param password: The password to store.
        """
        try:
            with open("passwords.txt", "r+") as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith(name + ":"):
                        print("Password entry already exists.")
                        return
                file.seek(0)
                file.write(name + ":" + self.f.encrypt(password.encode()).decode() + "\n")
                file.truncate()
        except FileNotFoundError:
            with open("passwords.txt", "w") as file:
                file.write(name + ":" + self.f.encrypt(password.encode()).decode() + "\n")

    def edit_password(self, name: str, new_password: str) -> None:
        """
        Edit an existing password entry.

        :param name: The name of the password entry.
        :param new_password: The new password to store.
        """
        try:
            with open("passwords.txt", "r+") as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith(name + ":"):
                        lines[i] = name + ":" + self.f.encrypt(new_password.encode()).decode() + "\n"
                        file.seek(0)
                        file.writelines(lines)
                        file.truncate()
                        return
                print("Password entry not found.")
        except FileNotFoundError:
            print("No password entries exist.")

    def delete_password(self, name: str) -> None:
        """
        Delete a password entry.

        :param name: The name of the password entry.
        """
        try:
            with open("passwords.txt", "r+") as file:
                lines = file.readlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith(name + ":"):
                        lines.pop(i)
                        file.seek(0)
                        file.writelines(lines)
                        file.truncate()
                        return
                print("Password entry not found.")
        except FileNotFoundError:
            print("No password entries exist.")

    def get_password(self, name: str) -> str:
        """
        Get a password entry.

        :param name: The name of the password entry.
        :return: The password.
        """
        try:
            with open("passwords.txt", "r") as file:
                for line in file.readlines():
                    if line.strip().startswith(name + ":"):
                        return self.f.decrypt(line.strip().split(":")[1].encode()).decode()
                print("Password entry not found.")
                return ""
        except FileNotFoundError:
            print("No password entries exist.")
            return ""

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a random password.

        :param length: The length of the password.
        :return: The generated password.
        """
        characters = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(characters) for _ in range(length))


def main() -> None:
    master_password = getpass.getpass("Enter master password: ")
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
            name = input("Enter password name: ")
            password = getpass.getpass("Enter password: ")
            password_manager.add_password(name, password)
        elif choice == "2":
            name = input("Enter password name: ")
            new_password = getpass.getpass("Enter new password: ")
            password_manager.edit_password(name, new_password)
        elif choice == "3":
            name = input("Enter password name: ")
            password_manager.delete_password(name)
        elif choice == "4":
            name = input("Enter password name: ")
            print(password_manager.get_password(name))
        elif choice == "5":
            length = int(input("Enter password length: "))
            print(password_manager.generate_password(length))
        elif choice == "6":
            break
        else:
            print("Invalid option. Please choose again.")

if __name__ == "__main__":
    main()