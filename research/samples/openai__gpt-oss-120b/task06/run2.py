#!/usr/bin/env python3
"""
Password Manager

Features:
- Master password authentication with key derivation (PBKDF2‑HMAC‑SHA256)
- Secure AES‑256‑GCM encryption of the vault (cryptography package)
- Add / edit / delete password entries
- Secure random password generation
- JSON based storage (encrypted on disk)

Only standard library and the ``cryptography`` package are required.
"""

from __future__ import annotations

import base64
import json
import os
import string
import sys
from dataclasses import dataclass, asdict
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, Optional

import secrets
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, kdf
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class PasswordManagerError(Exception):
    """Base class for all password manager errors."""


class AuthenticationError(PasswordManagerError):
    """Raised when the master password is invalid."""


class CorruptVaultError(PasswordManagerError):
    """Raised when the vault file cannot be decrypted or parsed."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass
class Entry:
    """A single password entry."""

    username: str
    password: str
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Entry":
        return Entry(
            username=data.get("username", ""),
            password=data.get("password", ""),
            notes=data.get("notes", ""),
        )


# --------------------------------------------------------------------------- #
# Core manager
# --------------------------------------------------------------------------- #


class PasswordManager:
    """
    Password manager handling encryption, decryption and entry manipulation.
    """

    # Security constants
    _KDF_ITERATIONS = 200_000
    _AES_KEY_SIZE = 32  # 256‑bit
    _NONCE_SIZE = 12  # Recommended for GCM
    _SALT_SIZE = 16
    _VERSION = 1

    def __init__(self, vault_path: str | os.PathLike) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.entries: Dict[str, Entry] = {}
        self._is_new_vault = not self.vault_path.is_file()

    # ------------------------------------------------------------------- #
    # Key derivation
    # ------------------------------------------------------------------- #

    @staticmethod
    def _derive_key(password: str, salt: bytes) -> bytes:
        """
        Derive an AES‑256 key from the master password and a salt using PBKDF2.
        """
        password_bytes = password.encode("utf-8")
        kdf_inst = kdf.pbkdf2.PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=PasswordManager._AES_KEY_SIZE,
            salt=salt,
            iterations=PasswordManager._KDF_ITERATIONS,
            backend=default_backend(),
        )
        return kdf_inst.derive(password_bytes)

    # ------------------------------------------------------------------- #
    # Encryption / Decryption
    # ------------------------------------------------------------------- #

    def _encrypt(self, plaintext: bytes, password: str) -> Dict[str, str]:
        """
        Encrypt plaintext with a key derived from ``password``.
        Returns a dictionary ready for JSON serialization.
        """
        salt = secrets.token_bytes(self._SALT_SIZE)
        key = self._derive_key(password, salt)
        nonce = secrets.token_bytes(self._NONCE_SIZE)

        encryptor = Cipher(
            algorithms.AES(key), modes.GCM(nonce), backend=default_backend()
        ).encryptor()

        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        tag = encryptor.tag

        return {
            "v": self._VERSION,
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "tag": base64.b64encode(tag).decode(),
            "ct": base64.b64encode(ciphertext).decode(),
        }

    def _decrypt(self, data: Dict[str, str], password: str) -> bytes:
        """
        Decrypt data previously produced by :meth:`_encrypt`.
        Raises :class:`AuthenticationError` if the password is wrong,
        :class:`CorruptVaultError` for malformed data.
        """
        try:
            if data.get("v") != self._VERSION:
                raise CorruptVaultError("Unsupported vault version")

            salt = base64.b64decode(data["salt"])
            nonce = base64.b64decode(data["nonce"])
            tag = base64.b64decode(data["tag"])
            ciphertext = base64.b64decode(data["ct"])
        except (KeyError, ValueError, TypeError) as exc:
            raise CorruptVaultError("Malformed vault data") from exc

        key = self._derive_key(password, salt)
        decryptor = Cipher(
            algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend()
        ).decryptor()

        try:
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        except Exception as exc:
            raise AuthenticationError("Invalid master password or corrupted data") from exc

        return plaintext

    # ------------------------------------------------------------------- #
    # Persistence
    # ------------------------------------------------------------------- #

    def load(self, password: str) -> None:
        """
        Load the vault from disk, decrypting it with ``password``.
        Raises :class:`AuthenticationError` if the password is wrong,
        :class:`CorruptVaultError` for I/O or parsing errors.
        """
        if self._is_new_vault:
            self.entries = {}
            return

        try:
            raw = self.vault_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            raise CorruptVaultError(f"Unable to read vault file: {exc}") from exc

        plaintext = self._decrypt(data, password)

        try:
            loaded = json.loads(plaintext.decode("utf-8"))
            self.entries = {
                service: Entry.from_dict(entry_dict)
                for service, entry_dict in loaded.items()
            }
        except Exception as exc:
            raise CorruptVaultError("Failed to decode vault contents") from exc

    def save(self, password: str) -> None:
        """
        Serialize the vault and write it encrypted to disk.
        """
        plain_dict = {service: entry.to_dict() for service, entry in self.entries.items()}
        plaintext = json.dumps(plain_dict, indent=2).encode("utf-8")
        encrypted = self._encrypt(plaintext, password)

        try:
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)
            self.vault_path.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")
            self._is_new_vault = False
        except Exception as exc:
            raise PasswordManagerError(f"Failed to write vault file: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Entry management
    # ------------------------------------------------------------------- #

    def add_entry(
        self,
        service: str,
        username: str,
        password: str,
        notes: str = "",
        overwrite: bool = False,
    ) -> None:
        """
        Add a new entry. If ``overwrite`` is False and the service already exists,
        a :class:`PasswordManagerError` is raised.
        """
        if service in self.entries and not overwrite:
            raise PasswordManagerError(f"Entry for '{service}' already exists")
        self.entries[service] = Entry(username=username, password=password, notes=notes)

    def edit_entry(
        self,
        service: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Edit an existing entry. Fields set to ``None`` remain unchanged.
        """
        if service not in self.entries:
            raise PasswordManagerError(f"No entry found for '{service}'")
        entry = self.entries[service]
        if username is not None:
            entry.username = username
        if password is not None:
            entry.password = password
        if notes is not None:
            entry.notes = notes

    def delete_entry(self, service: str) -> None:
        """Remove an entry from the vault."""
        if service not in self.entries:
            raise PasswordManagerError(f"No entry found for '{service}'")
        del self.entries[service]

    def get_entry(self, service: str) -> Entry:
        """Retrieve an entry; raises if not found."""
        if service not in self.entries:
            raise PasswordManagerError(f"No entry found for '{service}'")
        return self.entries[service]

    # ------------------------------------------------------------------- #
    # Password generation
    # ------------------------------------------------------------------- #

    @staticmethod
    def generate_password(
        length: int = 16,
        use_upper: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
    ) -> str:
        """
        Generate a secure random password.

        Parameters
        ----------
        length: Desired length of the password (minimum 8)
        use_upper: Include uppercase letters
        use_digits: Include decimal digits
        use_symbols: Include punctuation symbols

        Returns
        -------
        A randomly generated password string.
        """
        if length < 8:
            raise ValueError("Password length should be at least 8 characters")

        charset = list(string.ascii_lowercase)
        if use_upper:
            charset += list(string.ascii_uppercase)
        if use_digits:
            charset += list(string.digits)
        if use_symbols:
            charset += list("!@#$%^&*()-_=+[]{}|;:,.<>?")

        if not charset:
            raise ValueError("No characters available to generate a password")

        return "".join(secrets.choice(charset) for _ in range(length))


# --------------------------------------------------------------------------- #
# Simple CLI
# --------------------------------------------------------------------------- #


def _prompt_master_password(new: bool = False) -> str:
    if new:
        while True:
            pwd1 = getpass("Create master password: ")
            pwd2 = getpass("Confirm master password: ")
            if pwd1 != pwd2:
                print("Passwords do not match. Try again.", file=sys.stderr)
            elif len(pwd1) < 8:
                print("Password too short; minimum 8 characters.", file=sys.stderr)
            else:
                return pwd1
    else:
        return getpass("Master password: ")


def _print_entry(service: str, entry: Entry) -> None:
    print(f"\nService : {service}")
    print(f"Username: {entry.username}")
    print(f"Password: {entry.password}")
    if entry.notes:
        print(f"Notes   : {entry.notes}")
    print("-" * 30)


def main(argv: list[str] | None = None) -> None:
    """
    Minimal command‑line interface for the password manager.
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("Usage: python password_manager.py <vault_file>")
        sys.exit(1)

    vault_file = argv[0]
    manager = PasswordManager(vault_file)

    # Authenticate / create vault
    if manager._is_new_vault:
        print("Vault not found. Creating new vault.")
        master_pwd = _prompt_master_password(new=True)
        manager.save(master_pwd)  # create empty encrypted file
    else:
        master_pwd = _prompt_master_password()
        try:
            manager.load(master_pwd)
        except AuthenticationError:
            print("Invalid master password.", file=sys.stderr)
            sys.exit(1)
        except CorruptVaultError as exc:
            print(f"Corrupt vault: {exc}", file=sys.stderr)
            sys.exit(1)

    # Interactive loop
    while True:
        print("\nOptions: [list] [show] [add] [edit] [del] [gen] [quit]")
        choice = input(">>> ").strip().lower()

        if choice in ("quit", "q", "exit"):
            manager.save(master_pwd)
            print("Vault saved. Bye!")
            break

        elif choice in ("list", "ls"):
            if not manager.entries:
                print("Vault is empty.")
            else:
                for svc in sorted(manager.entries):
                    print(f"- {svc}")

        elif choice == "show":
            svc = input("Service name: ").strip()
            try:
                entry = manager.get_entry(svc)
                _print_entry(svc, entry)
            except PasswordManagerError as exc:
                print(exc)

        elif choice == "add":
            svc = input("Service name: ").strip()
            usr = input("Username    : ").strip()
            pwd = getpass("Password    : ").strip()
            note = input("Notes (optional) : ").strip()
            try:
                manager.add_entry(svc, usr, pwd, note)
                print(f"Entry for '{svc}' added.")
            except PasswordManagerError as exc:
                print(exc)

        elif choice == "edit":
            svc = input("Service name to edit: ").strip()
            try:
                entry = manager.get_entry(svc)
            except PasswordManagerError as exc:
                print(exc)
                continue
            print("Press Enter to keep current value.")
            usr = input(f"Username [{entry.username}]: ").strip() or None
            pwd = getpass("Password (hidden) [****]: ").strip() or None
            note = input(f"Notes [{entry.notes}]: ").strip() or None
            try:
                manager.edit_entry(svc, username=usr, password=pwd, notes=note)
                print(f"Entry for '{svc}' updated.")
            except PasswordManagerError as exc:
                print(exc)

        elif choice == "del":
            svc = input("Service name to delete: ").strip()
            confirm = input(f"Are you sure you want to delete '{svc}'? (y/N): ").lower()
            if confirm == "y":
                try:
                    manager.delete_entry(svc)
                    print(f"Deleted entry for '{svc}'.")
                except PasswordManagerError as exc:
                    print(exc)

        elif choice == "gen":
            try:
                length = int(input("Length (default 16): ") or "16")
                use_upper = input("Include uppercase? (Y/n): ").lower() != "n"
                use_digits = input("Include digits? (Y/n): ").lower() != "n"
                use_symbols = input("Include symbols? (Y/n): ").lower() != "n"
                pwd = manager.generate_password(
                    length=length,
                    use_upper=use_upper,
                    use_digits=use_digits,
                    use_symbols=use_symbols,
                )
                print(f"Generated password: {pwd}")
            except ValueError as exc:
                print(f"Invalid input: {exc}")

        else:
            print("Unknown command.")


if __name__ == "__main__":
    main()