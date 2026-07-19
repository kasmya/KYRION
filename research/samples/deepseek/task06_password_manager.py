"""
Secure Password Manager with Tkinter GUI and Fernet encryption.

Features:
- Master password with PBKDF2 key derivation
- Fernet encryption for credential vault
- Add, retrieve, delete credentials
- Strong password generator
- Copy to clipboard functionality
"""

import os
import logging
import json
import base64
import secrets
import string
from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import pyperclip

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('password_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PasswordGenerator:
    """Generates strong, random passwords."""
    
    def __init__(self):
        """Initialize password generator."""
        self.lowercase = string.ascii_lowercase
        self.uppercase = string.ascii_uppercase
        self.digits = string.digits
        self.special = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        self.ambiguous = "il1Lo0O"
    
    def generate(
        self,
        length: int = 16,
        use_uppercase: bool = True,
        use_lowercase: bool = True,
        use_digits: bool = True,
        use_special: bool = True,
        exclude_ambiguous: bool = True
    ) -> str:
        """
        Generate a strong password.
        
        Args:
            length: Password length
            use_uppercase: Include uppercase letters
            use_lowercase: Include lowercase letters
            use_digits: Include digits
            use_special: Include special characters
            exclude_ambiguous: Exclude ambiguous characters
            
        Returns:
            Generated password
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters")
        
        # Build character pool
        char_pool = ""
        if use_lowercase:
            char_pool += self.lowercase
        if use_uppercase:
            char_pool += self.uppercase
        if use_digits:
            char_pool += self.digits
        if use_special:
            char_pool += self.special
        
        if not char_pool:
            raise ValueError("At least one character type must be selected")
        
        # Remove ambiguous characters if requested
        if exclude_ambiguous:
            for char in self.ambiguous:
                char_pool = char_pool.replace(char, '')
        
        if not char_pool:
            raise ValueError("Character pool is empty after removing ambiguous characters")
        
        # Generate password ensuring at least one of each required type
        password = []
        
        if use_lowercase:
            password.append(secrets.choice(self.lowercase))
        if use_uppercase:
            password.append(secrets.choice(self.uppercase))
        if use_digits:
            password.append(secrets.choice(self.digits))
        if use_special:
            password.append(secrets.choice(self.special))
        
        # Fill remaining length with random characters
        remaining_length = length - len(password)
        password.extend(secrets.choice(char_pool) for _ in range(remaining_length))
        
        # Shuffle the password
        secrets.SystemRandom().shuffle(password)
        
        return ''.join(password)
    
    def evaluate_strength(self, password: str) -> Dict[str, Any]:
        """
        Evaluate password strength.
        
        Args:
            password: Password to evaluate
            
        Returns:
            Dictionary with strength metrics
        """
        score = 0
        checks = {
            'length': len(password) >= 12,
            'uppercase': any(c.isupper() for c in password),
            'lowercase': any(c.islower() for c in password),
            'digits': any(c.isdigit() for c in password),
            'special': any(c in self.special for c in password),
            'no_repeated': len(set(password)) > len(password) * 0.7
        }
        
        score = sum(checks.values())
        
        strength_map = {
            0: "Very Weak",
            1: "Weak",
            2: "Fair",
            3: "Good",
            4: "Strong",
            5: "Very Strong",
            6: "Excellent"
        }
        
        return {
            'score': score,
            'strength': strength_map.get(score, "Unknown"),
            'max_score': len(checks),
            'checks': checks
        }

class CryptoManager:
    """Manages encryption/decryption using Fernet with PBKDF2 key derivation."""
    
    SALT_SIZE = 32
    ITERATIONS = 100000
    
    def __init__(self):
        """Initialize crypto manager."""
        self._fernet: Optional[Fernet] = None
        self._salt: Optional[bytes] = None
    
    def derive_key(self, master_password: str, salt: Optional[bytes] = None) -> bytes:
        """
        Derive encryption key from master password using PBKDF2.
        
        Args:
            master_password: Master password
            salt: Salt for key derivation (generated if None)
            
        Returns:
            Tuple of (derived_key, salt)
        """
        if salt is None:
            salt = os.urandom(self.SALT_SIZE)
        
        self._salt = salt
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
            backend=default_backend()
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        return key
    
    def initialize_fernet(self, master_password: str, salt: Optional[bytes] = None) -> Fernet:
        """
        Initialize Fernet instance with derived key.
        
        Args:
            master_password: Master password
            salt: Salt for key derivation
            
        Returns:
            Fernet instance
        """
        key = self.derive_key(master_password, salt)
        self._fernet = Fernet(key)
        return self._fernet
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using Fernet."""
        if not self._fernet:
            raise ValueError("Fernet not initialized. Call initialize_fernet first.")
        
        return self._fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext using Fernet."""
        if not self._fernet:
            raise ValueError("Fernet not initialized. Call initialize_fernet first.")
        
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            raise ValueError("Decryption failed. Invalid master password or corrupted data.")
    
    @property
    def salt(self) -> Optional[bytes]:
        """Get current salt."""
        return self._salt

class Vault:
    """Encrypted credential vault."""
    
    def __init__(self, vault_path: str = "vault.enc"):
        """
        Initialize vault.
        
        Args:
            vault_path: Path to vault file
        """
        self.vault_path = Path(vault_path)
        self.entries: Dict[str, Dict[str, str]] = {}
        self.crypto = CryptoManager()
        self.is_unlocked = False
    
    def create(self, master_password: str) -> None:
        """
        Create new vault with master password.
        
        Args:
            master_password: Master password for vault
        """
        if self.vault_path.exists():
            raise FileExistsError("Vault already exists")
        
        self.crypto.initialize_fernet(master_password)
        self.is_unlocked = True
        self._save()
        logger.info("New vault created")
    
    def unlock(self, master_password: str) -> bool:
        """
        Unlock vault with master password.
        
        Args:
            master_password: Master password
            
        Returns:
            True if unlocked successfully, False otherwise
        """
        try:
            if not self.vault_path.exists():
                raise FileNotFoundError("Vault not found")
            
            # Load vault data
            with open(self.vault_path, 'r') as f:
                data = json.load(f)
            
            # Get salt
            salt = base64.b64decode(data['salt'])
            
            # Try to decrypt with master password
            self.crypto.initialize_fernet(master_password, salt)
            
            # Decrypt entries
            if data['entries']:
                decrypted_entries = self.crypto.decrypt(data['entries'])
                self.entries = json.loads(decrypted_entries)
            else:
                self.entries = {}
            
            self.is_unlocked = True
            logger.info("Vault unlocked successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unlock vault: {str(e)}")
            self.is_unlocked = False
            return False
    
    def lock(self) -> None:
        """Lock the vault and clear sensitive data."""
        self.entries.clear()
        self.crypto = CryptoManager()
        self.is_unlocked = False
        logger.info("Vault locked")
    
    def add_entry(self, service: str, username: str, password: str, notes: str = "") -> None:
        """
        Add credential entry to vault.
        
        Args:
            service: Service name
            username: Username/email
            password: Password
            notes: Additional notes
        """
        if not self.is_unlocked:
            raise PermissionError("Vault is locked")
        
        self.entries[service] = {
            'username': username,
            'password': password,
            'notes': notes,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        self._save()
        logger.info(f"Entry added for {service}")
    
    def get_entry(self, service: str) -> Optional[Dict[str, str]]:
        """
        Get credential entry.
        
        Args:
            service: Service name
            
        Returns:
            Entry dictionary or None
        """
        if not self.is_unlocked:
            raise PermissionError("Vault is locked")
        
        return self.entries.get(service)
    
    def delete_entry(self, service: str) -> bool:
        """
        Delete credential entry.
        
        Args:
            service: Service name
            
        Returns:
            True if deleted, False if not found
        """
        if not self.is_unlocked:
            raise PermissionError("Vault is locked")
        
        if service in self.entries:
            del self.entries[service]
            self._save()
            logger.info(f"Entry deleted for {service}")
            return True
        
        return False
    
    def list_services(self) -> List[str]:
        """List all stored services."""
        if not self.is_unlocked:
            raise PermissionError("Vault is locked")
        
        return list(self.entries.keys())
    
    def update_entry(self, service: str, **kwargs) -> bool:
        """
        Update credential entry.
        
        Args:
            service: Service name
            **kwargs: Fields to update
            
        Returns:
            True if updated, False if not found
        """
        if not self.is_unlocked:
            raise PermissionError("Vault is locked")
        
        if service not in self.entries:
            return False
        
        for key, value in kwargs.items():
            if key in self.entries[service]:
                self.entries[service][key] = value
        
        self.entries[service]['updated_at'] = datetime.now().isoformat()
        self._save()
        logger.info(f"Entry updated for {service}")
        return True
    
    def _save(self) -> None:
        """Save encrypted vault to file."""
        if not self.is_unlocked:
            return
        
        data = {
            'salt': base64.b64encode(self.crypto.salt).decode(),
            'entries': self.crypto.encrypt(json.dumps(self.entries))
        }
        
        with open(self.vault_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def change_master_password(self, old_password: str, new_password: str) -> bool:
        """
        Change master password.
        
        Args:
            old_password: Current master password
            new_password: New master password
            
        Returns:
            True if changed successfully
        """
        if not self.is_unlocked:
            raise PermissionError("Vault is locked")
        
        try:
            # Save current entries
            current_entries = self.entries.copy()
            
            # Re-initialize with new password
            self.crypto.initialize_fernet(new_password)
            self.entries = current_entries
            
            # Save with new encryption
            self._save()
            logger.info("Master password changed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to change master password: {str(e)}")
            return False

class PasswordManagerGUI:
    """Tkinter GUI for password manager."""
    
    def __init__(self):
        """Initialize GUI."""
        self.root = tk.Tk()
        self.root.title("Password Manager")
        self.root.geometry("800x600")
        
        self.vault = Vault()
        self.password_gen = PasswordGenerator()
        
        self._create_widgets()
        self._show_login()
    
    def _create_widgets(self) -> None:
        """Create main window widgets."""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Lock Vault", command=self._lock_vault)
        file_menu.add_command(label="Change Master Password", command=self._change_password)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Main container
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
    
    def _clear_frame(self) -> None:
        """Clear all widgets from main frame."""
        for widget in self.main_frame.winfo_children():
            widget.destroy()
    
    def _show_login(self) -> None:
        """Show login/create vault screen."""
        self._clear_frame()
        
        frame = ttk.LabelFrame(self.main_frame, text="Vault Access", padding="20")
        frame.grid(row=0, column=0, padx=20, pady=20)
        
        # Check if vault exists
        vault_exists = self.vault.vault_path.exists()
        
        if vault_exists:
            ttk.Label(frame, text="Enter Master Password to Unlock Vault:").grid(
                row=0, column=0, columnspan=2, pady=10
            )
        else:
            ttk.Label(frame, text="Create New Vault:").grid(
                row=0, column=0, columnspan=2, pady=10
            )
            ttk.Label(frame, text="Choose a strong master password:").grid(
                row=1, column=0, columnspan=2, pady=5
            )
        
        # Password entry
        ttk.Label(frame, text="Master Password:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*", width=30)
        password_entry.grid(row=2, column=1, pady=5)
        
        if not vault_exists:
            ttk.Label(frame, text="Confirm Password:").grid(row=3, column=0, sticky=tk.W, pady=5)
            self.confirm_var = tk.StringVar()
            confirm_entry = ttk.Entry(frame, textvariable=self.confirm_var, show="*", width=30)
            confirm_entry.grid(row=3, column=1, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4 if not vault_exists else 3, column=0, columnspan=2, pady=20)
        
        if vault_exists:
            ttk.Button(
                button_frame, text="Unlock Vault", command=self._unlock_vault
            ).pack(side=tk.LEFT, padx=5)
        else:
            ttk.Button(
                button_frame, text="Create Vault", command=self._create_vault
            ).pack(side=tk.LEFT, padx=5)
    
    def _create_vault(self) -> None:
        """Create new vault."""
        password = self.password_var.get()
        confirm = self.confirm_var.get()
        
        if not password:
            messagebox.showerror("Error", "Please enter a master password")
            return
        
        if len(password) < 8:
            messagebox.showerror("Error", "Master password must be at least 8 characters")
            return
        
        if password != confirm:
            messagebox.showerror("Error", "Passwords do not match")
            return
        
        try:
            self.vault.create(password)
            messagebox.showinfo("Success", "Vault created successfully!")
            self._show_main()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create vault: {str(e)}")
    
    def _unlock_vault(self) -> None:
        """Unlock existing vault."""
        password = self.password_var.get()
        
        if not password:
            messagebox.showerror("Error", "Please enter your master password")
            return
        
        if self.vault.unlock(password):
            self._show_main()
        else:
            messagebox.showerror("Error", "Invalid master password")
    
    def _lock_vault(self) -> None:
        """Lock vault and return to login."""
        self.vault.lock()
        self._show_login()
    
    def _change_password(self) -> None:
        """Change master password."""
        old_password = simpledialog.askstring(
            "Change Password", "Enter current master password:", show='*'
        )
        if not old_password:
            return
        
        new_password = simpledialog.askstring(
            "Change Password", "Enter new master password:", show='*'
        )
        if not new_password:
            return
        
        confirm = simpledialog.askstring(
            "Change Password", "Confirm new master password:", show='*'
        )
        
        if new_password != confirm:
            messagebox.showerror("Error", "Passwords do not match")
            return
        
        if self.vault.change_master_password(old_password, new_password):
            messagebox.showinfo("Success", "Master password changed successfully")
        else:
            messagebox.showerror("Error", "Failed to change master password")
    
    def _show_main(self) -> None:
        """Show main password manager interface."""
        self._clear_frame()
        
        # Create notebook for tabs
        notebook = ttk.Notebook(self.main_frame)
        notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Credentials tab
        cred_frame = ttk.Frame(notebook, padding="10")
        notebook.add(cred_frame, text="Credentials")
        self._setup_credentials_tab(cred_frame)
        
        # Password generator tab
        gen_frame = ttk.Frame(notebook, padding="10")
        notebook.add(gen_frame, text="Password Generator")
        self._setup_generator_tab(gen_frame)
        
        # Configure grid weights for main frame
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(0, weight=1)
    
    def _setup_credentials_tab(self, parent: ttk.Frame) -> None:
        """Setup credentials management tab."""
        # Service list
        left_frame = ttk.LabelFrame(parent, text="Saved Services", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        self.service_listbox = tk.Listbox(left_frame, width=30, height=20)
        self.service_listbox.pack(fill=tk.BOTH, expand=True)
        self.service_listbox.bind('<<ListboxSelect>>', self._on_service_select)
        
        # Refresh list
        self._refresh_service_list()
        
        # Entry details
        right_frame = ttk.LabelFrame(parent, text="Credential Details", padding="10")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        # Form fields
        ttk.Label(right_frame, text="Service:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.service_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.service_var, width=30).grid(
            row=0, column=1, pady=2
        )
        
        ttk.Label(right_frame, text="Username:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.username_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.username_var, width=30).grid(
            row=1, column=1, pady=2
        )
        
        ttk.Label(right_frame, text="Password:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.entry_password_var = tk.StringVar()
        password_frame = ttk.Frame(right_frame)
        password_frame.grid(row=2, column=1, pady=2)
        ttk.Entry(
            password_frame, textvariable=self.entry_password_var, width=25, show="*"
        ).pack(side=tk.LEFT)
        ttk.Button(
            password_frame, text="Show", command=lambda: self._toggle_password_visibility()
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            password_frame, text="Copy", command=lambda: self._copy_to_clipboard(
                self.entry_password_var.get()
            )
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(right_frame, text="Notes:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.notes_text = tk.Text(right_frame, width=30, height=5)
        self.notes_text.grid(row=3, column=1, pady=2)
        
        # Buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Save", command=self._save_entry).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(button_frame, text="Delete", command=self._delete_entry).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(
            side=tk.LEFT, padx=2
        )
        
        # Configure grid weights
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)
    
    def _setup_generator_tab(self, parent: ttk.Frame) -> None:
        """Setup password generator tab."""
        frame = ttk.LabelFrame(parent, text="Generate Strong Password", padding="20")
        frame.pack(padx=20, pady=20)
        
        # Options
        ttk.Label(frame, text="Password Length:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.length_var = tk.IntVar(value=16)
        ttk.Spinbox(
            frame, from_=8, to=64, textvariable=self.length_var, width=10
        ).grid(row=0, column=1, pady=5)
        
        self.use_upper_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame, text="Include Uppercase (A-Z)", variable=self.use_upper_var
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.use_lower_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame, text="Include Lowercase (a-z)", variable=self.use_lower_var
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.use_digits_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame, text="Include Digits (0-9)", variable=self.use_digits_var
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        self.use_special_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame, text="Include Special Characters (!@#$%^&*)", variable=self.use_special_var
        ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Generated password display
        ttk.Label(frame, text="Generated Password:").grid(
            row=5, column=0, sticky=tk.W, pady=10
        )
        self.generated_var = tk.StringVar()
        ttk.Entry(
            frame, textvariable=self.generated_var, width=40, state='readonly'
        ).grid(row=5, column=1, pady=10)
        
        # Strength indicator
        ttk.Label(frame, text="Strength:").grid(row=6, column=0, sticky=tk.W)
        self.strength_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.strength_var).grid(
            row=6, column=1, sticky=tk.W
        )
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=7, column=0, columnspan=2, pady=20)
        
        ttk.Button(
            button_frame, text="Generate Password", command=self._generate_password
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame, text="Copy to Clipboard",
            command=lambda: self._copy_to_clipboard(self.generated_var.get())
        ).pack(side=tk.LEFT, padx=5)
    
    def _refresh_service_list(self) -> None:
        """Refresh the service listbox."""
        self.service_listbox.delete(0, tk.END)
        try:
            services = self.vault.list_services()
            for service in sorted(services):
                self.service_listbox.insert(tk.END, service)
        except Exception as e:
            logger.error(f"Failed to refresh services: {str(e)}")
    
    def _on_service_select(self, event) -> None:
        """Handle service selection from listbox."""
        selection = self.service_listbox.curselection()
        if not selection:
            return
        
        service = self.service_listbox.get(selection[0])
        entry = self.vault.get_entry(service)
        
        if entry:
            self.service_var.set(service)
            self.username_var.set(entry['username'])
            self.entry_password_var.set(entry['password'])
            self.notes_text.delete('1.0', tk.END)
            self.notes_text.insert('1.0', entry.get('notes', ''))
    
    def _save_entry(self) -> None:
        """Save credential entry."""
        service = self.service_var.get().strip()
        username = self.username_var.get().strip()
        password = self.entry_password_var.get()
        notes = self.notes_text.get('1.0', tk.END).strip()
        
        if not service or not username or not password:
            messagebox.showerror("Error", "Service, username, and password are required")
            return
        
        try:
            self.vault.add_entry(service, username, password, notes)
            self._refresh_service_list()
            self._clear_form()
            messagebox.showinfo("Success", f"Saved credentials for {service}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save entry: {str(e)}")
    
    def _delete_entry(self) -> None:
        """Delete selected credential entry."""
        service = self.service_var.get().strip()
        
        if not service:
            messagebox.showerror("Error", "Please select a service to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Delete credentials for {service}?"):
            if self.vault.delete_entry(service):
                self._refresh_service_list()
                self._clear_form()
                messagebox.showinfo("Success", f"Deleted {service}")
            else:
                messagebox.showerror("Error", "Service not found")
    
    def _clear_form(self) -> None:
        """Clear credential form."""
        self.service_var.set("")
        self.username_var.set("")
        self.entry_password_var.set("")
        self.notes_text.delete('1.0', tk.END)
    
    def _toggle_password_visibility(self) -> None:
        """Toggle password visibility in entry."""
        # Simple implementation - in production, would toggle Entry show/hide
        messagebox.showinfo("Password", self.entry_password_var.get())
    
    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard."""
        if text:
            pyperclip.copy(text)
            messagebox.showinfo("Copied", "Password copied to clipboard")
    
    def _generate_password(self) -> None:
        """Generate password and display strength."""
        try:
            password = self.password_gen.generate(
                length=self.length_var.get(),
                use_uppercase=self.use_upper_var.get(),
                use_lowercase=self.use_lower_var.get(),
                use_digits=self.use_digits_var.get(),
                use_special=self.use_special_var.get()
            )
            
            self.generated_var.set(password)
            
            # Evaluate strength
            strength = self.password_gen.evaluate_strength(password)
            self.strength_var.set(
                f"{strength['strength']} ({strength['score']}/{strength['max_score']})"
            )
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate password: {str(e)}")
    
    def run(self) -> None:
        """Run the GUI application."""
        self.root.mainloop()

def main():
    """Main entry point."""
    app = PasswordManagerGUI()
    app.run()

if __name__ == "__main__":
    main()
