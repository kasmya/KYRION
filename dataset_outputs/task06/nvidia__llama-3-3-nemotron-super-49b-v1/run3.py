import getpass
import hashlib
import os
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from typing import Dict, Tuple

class PasswordManager:
    """
    A secure password manager with master password authentication, 
    encryption (AES), and password generation capabilities.
    """

    def __init__(self, data_file: str = "passwords.dat", key_file: str = "master.key"):
        """
        Initialize the PasswordManager.

        :param data_file: File to store encrypted password data (default: passwords.dat)
        :param key_file: File to store the master key (default: master.key)
        """
        self.data_file = data_file
        self.key_file = key_file
        self.master_key: bytes = self.load_master_key()
        self.passwords: Dict[str, str] = self.load_passwords()

    def load_master_key(self) -> bytes:
        """
        Load or generate the master key.

        :return: The master key
        """
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                return f.read()
        else:
            key = hashlib.sha256(getpass.getpass("Create master password: ").encode()).digest()
            confirm = hashlib.sha256(getpass.getpass("Confirm master password: ").encode()).digest()
            if key != confirm:
                raise ValueError("Passwords do not match")
            with open(self.key_file, "wb") as f:
                f.write(key)
            return key

    def authenticate(self) -> bool:
        """
        Authenticate using the master password.

        :return: True if authentication succeeds, False otherwise
        """
        input_key = hashlib.sha256(getpass.getpass("Enter master password: ").encode()).digest()
        return input_key == self.master_key

    def load_passwords(self) -> Dict[str, str]:
        """
        Load encrypted passwords from file.

        :return: Dictionary of decrypted passwords
        """
        if not os.path.exists(self.data_file):
            return {}
        with open(self.data_file, "rb") as f:
            encrypted_data = f.read()
        cipher = Cipher(algorithms.AES(self.master_key), modes.EFB(self.master_key), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
        # Assuming passwords are stored as JSON or similar, for simplicity, using plain text here
        # In a real application, use a secure format like JSON with separate salted hashes for each entry
        passwords = {}
        for line in decrypted_data.decode().splitlines():
            site, password = line.split(":", 1)
            passwords[site] = password
        return passwords

    def save_passwords(self) -> None:
        """
        Save passwords to file, encrypted.
        """
        encrypted_data = "\n".join(f"{site}:{password}" for site, password in self.passwords.items()).encode()
        cipher = Cipher(algorithms.AES(self.master_key), modes.EFB(self.master_key), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(encrypted_data) + encryptor.finalize()
        with open(self.data_file, "wb") as f:
            f.write(encrypted_data)

    def add_password(self, site: str, password: str) -> None:
        """
        Add a new password entry.

        :param site: Site name
        :param password: Password to store
        """
        if site in self.passwords:
            raise ValueError("Site already has a password stored")
        self.passwords[site] = password
        self.save_passwords()

    def edit_password(self, site: str, new_password: str) -> None:
        """
        Edit an existing password entry.

        :param site: Site name
        :param new_password: New password
        """
        if site not in self.passwords:
            raise ValueError("No password stored for this site")
        self.passwords[site] = new_password
        self.save_passwords()

    def delete_password(self, site: str) -> None:
        """
        Delete a password entry.

        :param site: Site name
        """
        if site not in self.passwords:
            raise ValueError("No password stored for this site")
        del self.passwords[site]
        self.save_passwords()

    def generate_password(self, length: int = 12) -> str:
        """
        Generate a random password.

        :param length: Password length (default: 12)
        :return: Generated password
        """
        # For simplicity, using only ascii_letters and digits. 
        # Consider adding more characters for stronger passwords
        import random; import string
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

def main():
    manager = PasswordManager()
    
    if not manager.authenticate():
        print("Authentication failed")
        return
    
    while True:
        print("\n1. Add Password\n2. Edit Password\n3. Delete Password\n4. Generate Password\n5. Quit")
        choice = input("Choose an option: ")
        
        if choice == "1":
            site = input("Enter site: ")
            password = input("Enter password (leave blank for generation): ")
            if not password:
                password = manager.generate_password()
                print(f"Generated Password: {password}")
            manager.add_password(site, password)
        elif choice == "2":
            site = input("Enter site: ")
            new_password = input("Enter new password (leave blank for generation): ")
            if not new_password:
                new_password = manager.generate_password()
                print(f"Generated Password: {new_password}")
            manager.edit_password(site, new_password)
        elif choice == "3":
            site = input("Enter site: ")
            manager.delete_password(site)
        elif choice == "4":
            length = int(input("Enter password length (default=12): ") or 12)
            print(f"Generated Password: {manager.generate_password(length)}")
        elif choice == "5":
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()