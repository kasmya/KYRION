"""Tkinter Password Manager with Fernet encryption and PBKDF2."""
import os, json, secrets, logging
import tkinter as tk
from tkinter import messagebox, simpledialog
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import pyperclip # Requires: pip install pyperclip

logging.basicConfig(level=logging.INFO)
VAULT_FILE = "vault.enc"
SALT_FILE = "salt.bin"

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

import base64

class PasswordManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Secure Vault")
        self.fernet = None
        self.vault = {}
        self.setup_ui()
        self.init_vault()

    def setup_ui(self):
        tk.Label(self.root, text="Password Manager", font=("Arial", 16)).pack(pady=10)
        self.listbox = tk.Listbox(self.root, width=50, height=15)
        self.listbox.pack(pady=10)
        
        btn_frame = tk.Frame(self.root)
        btn_frame.pack()
        tk.Button(btn_frame, text="Add", command=self.add_entry).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="Retrieve", command=self.retrieve_entry).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="Delete", command=self.delete_entry).grid(row=0, column=2, padx=5)
        tk.Button(btn_frame, text="Generate", command=self.generate_password).grid(row=0, column=3, padx=5)

    def init_vault(self):
        if os.path.exists(SALT_FILE) and os.path.exists(VAULT_FILE):
            with open(SALT_FILE, 'rb') as f: salt = f.read()
            pw = simpledialog.askstring("Login", "Enter Master Password:", show='*')
            if not pw: self.root.destroy(); return
            key = derive_key(pw, salt)
            self.fernet = Fernet(key)
            try:
                with open(VAULT_FILE, 'rb') as f:
                    self.vault = json.loads(self.fernet.decrypt(f.read()))
            except Exception:
                messagebox.showerror("Error", "Invalid master password.")
                self.root.destroy()
        else:
            pw = simpledialog.askstring("Setup", "Create Master Password:", show='*')
            if not pw: self.root.destroy(); return
            salt = secrets.token_bytes(16)
            with open(SALT_FILE, 'wb') as f: f.write(salt)
            key = derive_key(pw, salt)
            self.fernet = Fernet(key)
            self.save_vault()

    def save_vault(self):
        if not self.fernet: return
        with open(VAULT_FILE, 'wb') as f:
            f.write(self.fernet.encrypt(json.dumps(self.vault).encode()))

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for site in self.vault.keys():
            self.listbox.insert(tk.END, site)

    def add_entry(self):
        site = simpledialog.askstring("Add", "Website/Service:")
        user = simpledialog.askstring("Add", "Username:")
        pw = simpledialog.askstring("Add", "Password:", show='*')
        if site and user and pw:
            self.vault[site] = {"user": user, "pass": pw}
            self.save_vault()
            self.refresh_list()

    def retrieve_entry(self):
        sel = self.listbox.get(tk.ACTIVE)
        if sel in self.vault:
            pyperclip.copy(self.vault[sel]['pass'])
            messagebox.showinfo("Retrieved", f"Copied password for {sel} to clipboard.")

    def delete_entry(self):
        sel = self.listbox.get(tk.ACTIVE)
        if sel in self.vault:
            del self.vault[sel]
            self.save_vault()
            self.refresh_list()

    def generate_password(self):
        pw = secrets.token_urlsafe(16)
        messagebox.showinfo("Generated", f"Password: {pw}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PasswordManager(root)
    root.mainloop()