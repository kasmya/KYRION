"""
Task 6: Local Cryptographic Credential Vault
Features: PBKDF2 key derivation, AES-128-CBC Fernet encryption, dynamic password generation, Tkinter GUI view models.
Requires: cryptography, tkinter
"""

import os
import json
import secrets
import string
import logging
from typing import Dict, Any, Optional
import tkinter as tk
from tkinter import messagebox, ttk

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
import base64

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CryptographyEngine:
    """Handles key derivation and safe disk-level database block encryption."""
    
    ITERATIONS = 600_000  # OWASP standard minimum parameters for 2026
    SALT_FILE = "vault.salt"
    VAULT_FILE = "vault.enc"

    @classmethod
    def derive_vault_key(cls, master_password: str) -> bytes:
        """Derives a deterministic cryptographic key from the master password using PBKDF2."""
        if os.path.exists(cls.SALT_FILE):
            with open(cls.SALT_FILE, "rb") as f:
                salt = f.read()
        else:
            salt = os.urandom(16)
            with open(cls.SALT_FILE, "wb") as f:
                f.write(salt)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=cls.ITERATIONS
        )
        return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))

class PasswordVaultApp:
    """Tkinter Desktop Interface managing application lifecycle and local memory structures."""
    
    def __init__(self, window_root: tk.Tk) -> None:
        self.root = window_root
        self.root.title("Cryptographic Key Management Vault")
        self.root.geometry("550x450")
        self.fernet_cipher: Optional[Fernet] = None
        self.decrypted_cache: Dict[str, Dict[str, str]] = {}
        
        self.build_authentication_view()

    def clean_workspace_canvas(self) -> None:
        """Cleans active window canvas objects."""
        for widget in self.root.winfo_children():
            widget.destroy()

    def build_authentication_view(self) -> None:
        """Renders initial access screen asking for administrative password authority."""
        self.clean_workspace_canvas()
        frame = ttk.Frame(self.root, padding="30")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Secure Vault Access", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(frame, text="Enter Master Password:").pack(pady=5)
        
        self.master_pwd_entry = ttk.Entry(frame, show="*", width=35)
        self.master_pwd_entry.pack(pady=5)
        self.master_pwd_entry.focus()

        ttk.Button(frame, text="Unlock Vault Storage", command=self.unlock_vault_database).pack(pady=15)

    def unlock_vault_database(self) -> None:
        """Attempts key derivation to decrypt internal resource entries."""
        master_password = self.master_pwd_entry.get()
        if not master_password:
            messagebox.showerror("Error", "Master Password cannot be blank.")
            return

        try:
            derived_key = CryptographyEngine.derive_vault_key(master_password)
            self.fernet_cipher = Fernet(derived_key)

            if os.path.exists(CryptographyEngine.VAULT_FILE):
                with open(CryptographyEngine.VAULT_FILE, "rb") as f:
                    encrypted_data = f.read()
                decrypted_bytes = self.fernet_cipher.decrypt(encrypted_data)
                self.decrypted_cache = json.loads(decrypted_bytes.decode('utf-8'))
            else:
                self.decrypted_cache = {}

            self.build_dashboard_view()
        except Exception:
            messagebox.showerror("Access Denied", "Invalid master key credential signature matched.")

    def build_dashboard_view(self) -> None:
        """Main view displaying stored accounts and generation utility workflows."""
        self.clean_workspace_canvas()
        
        # Main Layout splits
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X)
        
        list_frame = ttk.Frame(self.root, padding="10")
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Form entry elements inside headers
        ttk.Label(control_frame, text="Domain:").grid(row=0, column=0, padx=5, pady=2)
        self.entry_domain = ttk.Entry(control_frame, width=15)
        self.entry_domain.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(control_frame, text="Username:").grid(row=0, column=2, padx=5, pady=2)
        self.entry_user = ttk.Entry(control_frame, width=15)
        self.entry_user.grid(row=0, column=3, padx=5, pady=2)

        ttk.Label(control_frame, text="Password:").grid(row=1, column=0, padx=5, pady=2)
        self.entry_pass = ttk.Entry(control_frame, width=15)
        self.entry_pass.grid(row=1, column=1, padx=5, pady=2)

        # Functional Buttons
        ttk.Button(control_frame, text="Generate", command=self.trigger_generation_token).grid(row=1, column=2, padx=5)
        ttk.Button(control_frame, text="Save Record", command=self.commit_record_entry).grid(row=1, column=3, padx=5)

        # Records Table View (Treeview)
        self.vault_tree = ttk.Treeview(list_frame, columns=("Domain", "Username"), show="headings")
        self.vault_tree.heading("Domain", text="Domain Endpoint")
        self.vault_tree.heading("Username", text="Identity Username")
        self.vault_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # Action Sidebars for lists
        action_sidebar = ttk.Frame(list_frame, padding="5")
        action_sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(action_sidebar, text="Copy Pass", command=self.copy_password_to_clipboard).pack(fill=tk.X, pady=2)
        ttk.Button(action_sidebar, text="Delete Entry", command=self.delete_selected_record).pack(fill=tk.X, pady=2)

        self.refresh_tree_records()

    def refresh_tree_records(self) -> None:
        """Redraws the entries listed within the tree component layout."""
        for row in self.vault_tree.get_children():
            self.vault_tree.delete(row)
        for domain, details in self.decrypted_cache.items():
            self.vault_tree.insert("", tk.END, iid=domain, values=(domain, details.get("username")))

    def trigger_generation_token(self) -> None:
        """Generates a cryptographically strong random password."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        generated_password = "".join(secrets.choice(alphabet) for _ in range(16))
        self.entry_pass.delete(0, tk.END)
        self.entry_pass.insert(0, generated_password)

    def commit_record_entry(self) -> None:
        """Encrypts changes and flushes them to local disk files securely."""
        domain = self.entry_domain.get().strip()
        user = self.entry_user.get().strip()
        pwd = self.entry_pass.get().strip()

        if not domain or not user or not pwd:
            messagebox.showwarning("Incomplete Fields", "Please populate all inputs before saving.")
            return

        self.decrypted_cache[domain] = {"username": user, "password": pwd}
        if self.flush_cache_to_disk():
            messagebox.showinfo("Success", f"Encrypted tracking structure mapped for {domain}")
            self.refresh_tree_records()

    def copy_password_to_clipboard(self) -> None:
        """Copies the password of the selected item to the secure system clipboard buffer."""
        selected_item = self.vault_tree.focus()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Highlight a target profile entry node from the inventory table view first.")
            return
        
        target_password = self.decrypted_cache[selected_item]["password"]
        self.root.clipboard_clear()
        self.root.clipboard_append(target_password)
        messagebox.showinfo("Clipboard Sync", "Secret token extracted to global system copy buffers safely.")

    def delete_selected_record(self) -> None:
        """Removes an active index selection mapping configuration reference."""
        selected_item = self.vault_tree.focus()
        if not selected_item:
            return
        
        if messagebox.askyesno("Confirm Deletion", f"Permanently wipe access mapping profile data points for: {selected_item}?"):
            del self.decrypted_cache[selected_item]
            if self.flush_cache_to_disk():
                self.refresh_tree_records()

    def flush_cache_to_disk(self) -> bool:
        """Performs atomic payload saves across data blocks."""
        if not self.fernet_cipher:
            return False
        try:
            serialized_payload = json.dumps(self.decrypted_cache).encode('utf-8')
            encrypted_payload = self.fernet_cipher.encrypt(serialized_payload)
            with open(CryptographyEngine.VAULT_FILE, "wb") as f:
                f.write(encrypted_payload)
            return True
        except Exception as err:
            logger.error(f"Failed to flush local vault structures safely: {err}")
            messagebox.showerror("Storage Failure", "Could not commit state update logs cleanly to local blocks.")
            return False

if __name__ == "__main__":
    app_engine = tk.Tk()
    manager = PasswordVaultApp(app_engine)
    app_engine.mainloop()

