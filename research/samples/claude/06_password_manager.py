"""
### Task 6: Password Manager (Tkinter + Cryptography)

A local desktop password manager with a master-password-derived key
(PBKDF2), Fernet-encrypted credential vault on disk, a strong password
generator, and clipboard copy support.

Requirements:
    pip install cryptography pyperclip
    (tkinter ships with most standard CPython installs)

Run:
    python 06_password_manager.py
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import string
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    import pyperclip
except Exception:  # noqa: BLE001
    pyperclip = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("password_manager")

VAULT_PATH = Path("vault.enc")
SALT_PATH = Path("vault.salt")
PBKDF2_ITERATIONS = 390_000


class VaultError(Exception):
    """Raised for vault load/save/decryption failures."""


@dataclass
class Credential:
    """A single stored credential entry."""

    service: str
    username: str
    password: str


def derive_key(master_password: str, salt: bytes) -> bytes:
    """Derives a Fernet-compatible key from the master password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(master_password.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def generate_strong_password(length: int = 16) -> str:
    """Generates a cryptographically strong random password.

    Ensures at least one lowercase, one uppercase, one digit, and one symbol.
    """
    if length < 4:
        raise ValueError("length must be at least 4 to satisfy complexity rules")

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
            and any(c in "!@#$%^&*()-_=+" for c in candidate)
        ):
            return candidate


class VaultManager:
    """Handles loading, saving, and encrypting/decrypting the credential vault."""

    def __init__(self, master_password: str) -> None:
        if SALT_PATH.exists():
            salt = SALT_PATH.read_bytes()
        else:
            salt = os.urandom(16)
            SALT_PATH.write_bytes(salt)

        self.key = derive_key(master_password, salt)
        self.fernet = Fernet(self.key)
        self.credentials: Dict[str, Credential] = {}
        self._load()

    def _load(self) -> None:
        """Loads and decrypts the vault file, if it exists."""
        if not VAULT_PATH.exists():
            self.credentials = {}
            return

        try:
            encrypted = VAULT_PATH.read_bytes()
            decrypted = self.fernet.decrypt(encrypted)
            raw = json.loads(decrypted.decode("utf-8"))
            self.credentials = {
                service: Credential(**entry) for service, entry in raw.items()
            }
            logger.info("Loaded %d credential(s) from vault", len(self.credentials))
        except InvalidToken as exc:
            raise VaultError("Incorrect master password or corrupted vault") from exc
        except (json.JSONDecodeError, OSError) as exc:
            raise VaultError(f"Failed to load vault: {exc}") from exc

    def _save(self) -> None:
        """Encrypts and persists the current credential set to disk."""
        try:
            raw = {
                service: {"service": c.service, "username": c.username, "password": c.password}
                for service, c in self.credentials.items()
            }
            payload = json.dumps(raw).encode("utf-8")
            encrypted = self.fernet.encrypt(payload)
            VAULT_PATH.write_bytes(encrypted)
        except OSError as exc:
            raise VaultError(f"Failed to save vault: {exc}") from exc

    def add_credential(self, service: str, username: str, password: str) -> None:
        """Adds or overwrites a credential entry and persists the vault."""
        if not service:
            raise ValueError("service name is required")
        self.credentials[service] = Credential(service=service, username=username, password=password)
        self._save()
        logger.info("Added/updated credential for '%s'", service)

    def get_credential(self, service: str) -> Optional[Credential]:
        """Retrieves a credential entry by service name."""
        return self.credentials.get(service)

    def delete_credential(self, service: str) -> bool:
        """Deletes a credential entry. Returns True if it existed."""
        if service in self.credentials:
            del self.credentials[service]
            self._save()
            logger.info("Deleted credential for '%s'", service)
            return True
        return False

    def list_services(self) -> list:
        """Returns a sorted list of stored service names."""
        return sorted(self.credentials.keys())


class PasswordManagerApp:
    """Tkinter GUI wrapping the VaultManager."""

    def __init__(self, root: tk.Tk, vault: VaultManager) -> None:
        self.root = root
        self.vault = vault
        self.root.title("Password Manager")
        self.root.geometry("480x420")
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        frame_top = tk.Frame(self.root, padx=10, pady=10)
        frame_top.pack(fill="x")

        tk.Label(frame_top, text="Service:").grid(row=0, column=0, sticky="w")
        self.service_entry = tk.Entry(frame_top, width=30)
        self.service_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(frame_top, text="Username:").grid(row=1, column=0, sticky="w")
        self.username_entry = tk.Entry(frame_top, width=30)
        self.username_entry.grid(row=1, column=1, padx=5, pady=2)

        tk.Label(frame_top, text="Password:").grid(row=2, column=0, sticky="w")
        self.password_entry = tk.Entry(frame_top, width=30, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=2)

        button_frame = tk.Frame(self.root, padx=10, pady=5)
        button_frame.pack(fill="x")

        tk.Button(button_frame, text="Generate Password", command=self._on_generate).pack(
            side="left", padx=5
        )
        tk.Button(button_frame, text="Add / Update", command=self._on_add).pack(side="left", padx=5)
        tk.Button(button_frame, text="Delete", command=self._on_delete).pack(side="left", padx=5)
        tk.Button(button_frame, text="Copy Password", command=self._on_copy).pack(side="left", padx=5)

        self.listbox = tk.Listbox(self.root, width=60, height=15)
        self.listbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for service in self.vault.list_services():
            self.listbox.insert(tk.END, service)

    def _on_generate(self) -> None:
        password = generate_strong_password()
        self.password_entry.delete(0, tk.END)
        self.password_entry.insert(0, password)

    def _on_add(self) -> None:
        service = self.service_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        try:
            self.vault.add_credential(service, username, password)
            self._refresh_list()
            messagebox.showinfo("Success", f"Credential for '{service}' saved.")
        except (ValueError, VaultError) as exc:
            messagebox.showerror("Error", str(exc))

    def _on_delete(self) -> None:
        service = self.service_entry.get().strip()
        if self.vault.delete_credential(service):
            self._refresh_list()
            messagebox.showinfo("Deleted", f"Credential for '{service}' deleted.")
        else:
            messagebox.showwarning("Not found", f"No credential found for '{service}'.")

    def _on_copy(self) -> None:
        service = self.service_entry.get().strip()
        credential = self.vault.get_credential(service)
        if not credential:
            messagebox.showwarning("Not found", f"No credential found for '{service}'.")
            return
        if pyperclip is None:
            messagebox.showwarning("Unavailable", "pyperclip is not installed; cannot copy to clipboard.")
            return
        pyperclip.copy(credential.password)
        messagebox.showinfo("Copied", f"Password for '{service}' copied to clipboard.")

    def _on_select(self, _event) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        service = self.listbox.get(selection[0])
        credential = self.vault.get_credential(service)
        if credential:
            self.service_entry.delete(0, tk.END)
            self.service_entry.insert(0, credential.service)
            self.username_entry.delete(0, tk.END)
            self.username_entry.insert(0, credential.username)
            self.password_entry.delete(0, tk.END)
            self.password_entry.insert(0, credential.password)


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    master_password = simpledialog.askstring(
        "Master Password", "Enter your master password:", show="*"
    )
    if not master_password:
        messagebox.showerror("Error", "Master password is required.")
        return

    try:
        vault = VaultManager(master_password)
    except VaultError as exc:
        messagebox.showerror("Vault Error", str(exc))
        return

    root.deiconify()
    PasswordManagerApp(root, vault)
    root.mainloop()


if __name__ == "__main__":
    main()
