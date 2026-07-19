"""
Password Manager using Tkinter and Cryptography.
Features:
- Master password with PBKDF2 key derivation
- Fernet encryption of credential vault
- Add/retrieve/delete credentials
- Strong password generator
- Copy password to clipboard
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
import os
import json
import base64
import secrets
import string
import logging
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
from typing import Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)

VAULT_FILE = "vault.json"
SALT_FILE = "salt.bin"


def generate_key(master_password: str, salt: bytes) -> bytes:
    """Generate encryption key from master password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend(),
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))


def load_salt() -> bytes:
    """Load or generate salt for key derivation."""
    if not os.path.exists(SALT_FILE):
        salt = os.urandom(16)
        with open(SALT_FILE, "wb") as f:
            f.write(salt)
        return salt
    with open(SALT_FILE, "rb") as f:
        return f.read()


def load_vault() -> Dict[str, str]:
    """Load encrypted vault file."""
    if not os.path.exists(VAULT_FILE):
        return {}
    with open(VAULT_FILE, "r") as f:
        return json.load(f)


def save_vault(vault: Dict[str, str]) -> None:
    """Save encrypted vault file."""
    with open(VAULT_FILE, "w") as f:
        json.dump(vault, f)


def generate_password(length: int = 16) -> str:
    """Generate a strong random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PasswordManagerApp:
    """Tkinter GUI for password manager."""

    def __init__(self, master: tk.Tk, fernet: Fernet):
        self.master = master
        self.fernet = fernet
        self.vault = load_vault()

        master.title("🔐 Password Manager")

        tk.Button(master, text="Add Credential", command=self.add_credential).pack(pady=5)
        tk.Button(master, text="Retrieve Credential", command=self.retrieve_credential).pack(pady=5)
        tk.Button(master, text="Delete Credential", command=self.delete_credential).pack(pady=5)
        tk.Button(master, text="Generate Password", command=self.show_generated_password).pack(pady=5)

    def add_credential(self) -> None:
        """Add a new credential to the vault."""
        site = simpledialog.askstring("Input", "Enter site/service name:")
        username = simpledialog.askstring("Input", "Enter username:")
        password = simpledialog.askstring("Input", "Enter password:")
        if not site or not username or not password:
            messagebox.showerror("Error", "All fields required")
            return
        encrypted = self.fernet.encrypt(password.encode()).decode()
        self.vault[site] = json.dumps({"username": username, "password": encrypted})
        save_vault(self.vault)
        messagebox.showinfo("Success", f"Credential for {site} saved.")

    def retrieve_credential(self) -> None:
        """Retrieve a credential from the vault."""
        site = simpledialog.askstring("Input", "Enter site/service name:")
        if site not in self.vault:
            messagebox.showerror("Error", "Credential not found")
            return
        data = json.loads(self.vault[site])
        decrypted = self.fernet.decrypt(data["password"].encode()).decode()
        self.master.clipboard_clear()
        self.master.clipboard_append(decrypted)
        messagebox.showinfo("Credential", f"Username: {data['username']}\nPassword copied to clipboard.")

    def delete_credential(self) -> None:
        """Delete a credential from the vault."""
        site = simpledialog.askstring("Input", "Enter site/service name:")
        if site in self.vault:
            del self.vault[site]
            save_vault(self.vault)
            messagebox.showinfo("Deleted", f"Credential for {site} deleted.")
        else:
            messagebox.showerror("Error", "Credential not found")

    def show_generated_password(self) -> None:
        """Generate and display a strong password."""
        pwd = generate_password()
        self.master.clipboard_clear()
        self.master.clipboard_append(pwd)
        messagebox.showinfo("Generated Password", f"{pwd}\nPassword copied to clipboard.")


def main():
    """Main entry point for password manager."""
    salt = load_salt()
    master_password = simpledialog.askstring("Master Password", "Enter master password:", show="*")
    if not master_password:
        messagebox.showerror("Error", "Master password required")
        return
    try:
        key = generate_key(master_password, salt)
        fernet = Fernet(key)
    except Exception as e:
        logging.error(f"Key generation failed: {e}")
        messagebox.showerror("Error", "Failed to initialize encryption")
        return

    root = tk.Tk()
    app = PasswordManagerApp(root, fernet)
    root.mainloop()


if __name__ == "__main__":
    main()

