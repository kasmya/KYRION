from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from getpass import getpass
import binascii
import hashlib
import os
import base64
import json

class PasswordManager:
    """Secure Password Manager with AES Encryption and Master Password Authentication"""

    def __init__(self, data_file: str = 'passwords.dat', master_password_file: str = 'master_password.dat'):
        """
        Initialize Password Manager

        :param data_file: File to store encrypted password data
        :param master_password_file: File to store hashed master password
        """
        self.data_file = data_file
        self.master_password_file = master_password_file
        self.master_password = None
        self.key = None
        self.iv = None

    def setup_master_password(self) -> None:
        """Setup Master Password for the First Time"""
        if os.path.exists(self.master_password_file):
            print("Master password already set. Please login.")
            return
        master_password = getpass("Enter new master password: ")
        confirm_password = getpass("Confirm master password: ")
        if master_password != confirm_password:
            print("Passwords do not match. Setup failed.")
            return
        hashed_password = hashlib.sha256(master_password.encode()).digest()
        with open(self.master_password_file, 'wb') as f:
            f.write(hashed_password)

    def login(self) -> bool:
        """Authenticate with Master Password"""
        if not os.path.exists(self.master_password_file):
            print("No master password set. Please setup.")
            return False
        master_password = getpass("Enter master password: ")
        with open(self.master_password_file, 'rb') as f:
            stored_hash = f.read()
        if hashlib.sha256(master_password.encode()).digest() != stored_hash:
            print("Incorrect master password.")
            return False
        self.master_password = master_password
        # Derive key and iv from master password for AES
        self.key = hashlib.sha256(master_password.encode()).digest()[:32]
        self.iv = hashlib.sha256(self.key).digest()[:16]
        return True

    def _encrypt(self, data: bytes) -> bytes:
        """Encrypt Data using AES-CBC"""
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
        encryptor = cipher.encryptor()
        return encryptor.update(padded_data) + encryptor.finalize()

    def _decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt Data using AES-CBC"""
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(decrypted_padded_data) + unpadder.finalize()

    def _load_data(self) -> dict:
        """Load Encrypted Password Data"""
        if not os.path.exists(self.data_file):
            return {}
        with open(self.data_file, 'rb') as f:
            encrypted_data = f.read()
        return json.loads(self._decrypt(encrypted_data).decode())

    def _save_data(self, data: dict) -> None:
        """Save Encrypted Password Data"""
        encrypted_data = self._encrypt(json.dumps(data).encode())
        with open(self.data_file, 'wb') as f:
            f.write(encrypted_data)

    def add_password(self, service: str, username: str, password: str) -> None:
        """Add New Password Entry"""
        if not self.master_password:
            print("Please login first.")
            return
        data = self._load_data()
        if service in data:
            print("Service already exists. Use edit instead.")
            return
        data[service] = {'username': username, 'password': password}
        self._save_data(data)
        print("Password added successfully.")

    def edit_password(self, service: str, new_service: str = None, new_username: str = None, new_password: str = None) -> None:
        """Edit Existing Password Entry"""
        if not self.master_password:
            print("Please login first.")
            return
        data = self._load_data()
        if service not in data:
            print("Service not found.")
            return
        if new_service:
            data[new_service] = data.pop(service)
            service = new_service
        if new_username:
            data[service]['username'] = new_username
        if new_password:
            data[service]['password'] = new_password
        self._save_data(data)
        print("Password updated successfully.")

    def delete_password(self, service: str) -> None:
        """Delete Password Entry"""
        if not self.master_password:
            print("Please login first.")
            return
        data = self._load_data()
        if service not in data:
            print("Service not found.")
            return
        del data[service]
        self._save_data(data)
        print("Password deleted successfully.")

    def generate_password(self, length: int = 12) -> str:
        """Generate Random Password"""
        if length < 8:
            print("Password length should be at least 8 characters.")
            return ""
        characters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()'
        return ''.join(os.urandom(length).hex()[:length])  # Simple hex for readability, adjust as needed

    def list_services(self) -> None:
        """List All Service Names"""
        if not self.master_password:
            print("Please login first.")
            return
        data = self._load_data()
        print(list(data.keys()))

def main():
    pm = PasswordManager()
    
    if not os.path.exists(pm.master_password_file):
        print("First time setup detected. Setting up master password...")
        pm.setup_master_password()
    
    if not pm.login():
        print("Authentication failed. Exiting.")
        return
    
    while True:
        print("\n1. Add Password\n2. Edit Password\n3. Delete Password\n4. Generate Password\n5. List Services\n6. Quit")
        choice = input("Choose an option: ")
        
        if choice == "1":
            service = input("Enter service name: ")
            username = input("Enter username: ")
            password = input("Enter password: ")
            pm.add_password(service, username, password)
        elif choice == "2":
            service = input("Enter service name to edit: ")
            new_service = input("Enter new service name (leave blank for no change): ") or None
            new_username = input("Enter new username (leave blank for no change): ") or None
            new_password = input("Enter new password (leave blank for no change): ") or None
            pm.edit_password(service, new_service, new_username, new_password)
        elif choice == "3":
            service = input("Enter service name to delete: ")
            pm.delete_password(service)
        elif choice == "4":
            length = int(input("Enter password length (default=12): ") or 12)
            print("Generated Password:", pm.generate_password(length))
        elif choice == "5":
            pm.list_services()
        elif choice == "6":
            break
        else:
            print("Invalid choice. Please choose again.")

if __name__ == "__main__":
    main()