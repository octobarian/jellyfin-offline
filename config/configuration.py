"""
Configuration management for RV Media Player.
Handles secure storage and retrieval of application settings.
"""

import os
import json
import stat
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from dotenv import load_dotenv


@dataclass
class Configuration:
    """Configuration data class for RV Media Player."""
    jellyfin_server_url: str = ""
    jellyfin_username: str = ""
    jellyfin_api_key: str = ""
    local_media_paths: List[str] = None
    download_directory: str = ""
    vlc_path: Optional[str] = None
    auto_launch: bool = True
    fullscreen_browser: bool = True
    # Performance optimization settings
    validation_cache_ttl: int = 300  # 5 minutes cache TTL for file validation
    max_validation_workers: int = 10  # Maximum concurrent validation threads
    
    def __post_init__(self):
        """Initialize default values after dataclass creation."""
        if self.local_media_paths is None:
            self.local_media_paths = [
                "media/movies",
                "media/tv-shows",
                "media/downloads"
            ]
        if not self.download_directory:
            self.download_directory = "media/downloads"
    
    @classmethod
    def load_from_file(cls, config_path: str = None) -> 'Configuration':
        """Load configuration from file using ConfigurationManager."""
        config_dir = "config"
        if config_path:
            config_dir = os.path.dirname(config_path) or "config"
        
        manager = ConfigurationManager(config_dir)
        return manager.load_configuration()
    
    def save_to_file(self, config_path: str = None) -> bool:
        """Save configuration to file using ConfigurationManager."""
        config_dir = "config"
        if config_path:
            config_dir = os.path.dirname(config_path) or "config"
        
        manager = ConfigurationManager(config_dir)
        return manager.save_configuration(self)


class ConfigurationManager:
    """Manages secure configuration storage and retrieval."""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "app_config.json"
        self.key_file = self.config_dir / ".encryption_key"
        self.env_file = self.config_dir / ".env"
        
        # Ensure config directory exists with secure permissions
        self._ensure_config_directory()
        
        # Load environment variables
        load_dotenv(self.env_file)
    
    def _ensure_config_directory(self) -> None:
        """Create config directory with secure permissions if it doesn't exist."""
        if not self.config_dir.exists():
            self.config_dir.mkdir(mode=0o700, parents=True)
        else:
            # Ensure existing directory has secure permissions
            os.chmod(self.config_dir, 0o700)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get existing encryption key or create a new one."""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Set secure permissions on key file
            os.chmod(self.key_file, 0o600)
        
        return key
    
    def _encrypt_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive configuration data."""
        key = self._get_or_create_encryption_key()
        cipher = Fernet(key)

        encrypted_data = data.copy()
        sensitive_fields = ['jellyfin_api_key', 'jellyfin_username'] # <-- COMMENT THIS OUT
        # sensitive_fields = ['jellyfin_username'] # <-- ONLY ENCRYPT USERNAME FOR NOW

        for field in sensitive_fields:
            if field in encrypted_data and encrypted_data[field]:
                # Check if it's already encrypted to avoid double encryption
                if not encrypted_data[field].startswith("gAAAAA"): # Simple check for Fernet prefix
                    encrypted_value = cipher.encrypt(encrypted_data[field].encode())
                    encrypted_data[field] = encrypted_value.decode()
                # else:
                    # print(f"DEBUG: Field {field} appears to be already encrypted, skipping re-encryption.") # Add for debug

        return encrypted_data
    
    def _decrypt_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive configuration data."""
        if not self.key_file.exists():
            print("WARNING: Encryption key file not found, cannot decrypt sensitive data.") # Add warning
            return data # Return data as is, assuming it's unencrypted or corrupted

        key = self._get_or_create_encryption_key()
        cipher = Fernet(key)

        decrypted_data = data.copy()
        sensitive_fields = ['jellyfin_api_key', 'jellyfin_username'] # <-- COMMENT THIS OUT
        # sensitive_fields = ['jellyfin_username'] # <-- ONLY DECRYPT USERNAME FOR NOW

        for field in sensitive_fields:
            if field in decrypted_data and decrypted_data[field] and decrypted_data[field].startswith("gAAAAA"):
                try:
                    decrypted_value = cipher.decrypt(decrypted_data[field].encode())
                    decrypted_data[field] = decrypted_value.decode()
                except Exception as e: # <-- CHANGE TO LOG THE EXCEPTION
                    print(f"ERROR: Decryption failed for field '{field}': {e}. Value remains encrypted.")
                    # Leave it encrypted if decryption fails, so it's not accidentally stored in plain text if corrupt
            # else:
                # print(f"DEBUG: Field {field} not encrypted or empty, skipping decryption.") # Add for debug

        return decrypted_data
    
    def load_configuration(self) -> Configuration:
        """Load configuration from file or create default configuration."""
        if not self.config_file.exists():
            return Configuration()
        
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
            
            # Decrypt sensitive data
            decrypted_data = self._decrypt_sensitive_data(data)
            
            # Convert to Configuration object
            return Configuration(**decrypted_data)
        
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"Error loading configuration: {e}")
            return Configuration()
    
    def save_configuration(self, config: Configuration) -> bool:
        """Save configuration to file with encryption for sensitive data."""
        try:
            # Convert to dictionary
            config_dict = asdict(config)
            
            # Encrypt sensitive data
            encrypted_data = self._encrypt_sensitive_data(config_dict)
            
            # Write to file with secure permissions
            with open(self.config_file, 'w') as f:
                json.dump(encrypted_data, f, indent=2)
            
            # Set secure permissions on config file
            os.chmod(self.config_file, 0o600)
            
            return True
        
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
    
    def validate_configuration(self, config: Configuration) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Validate Jellyfin settings if provided
        if config.jellyfin_server_url:
            if not config.jellyfin_server_url.startswith(('http://', 'https://')):
                errors.append("Jellyfin server URL must start with http:// or https://")
        
        # Validate local media paths
        for path in config.local_media_paths:
            if not Path(path).exists():
                errors.append(f"Local media path does not exist: {path}")
        
        # Validate download directory
        if config.download_directory:
            download_path = Path(config.download_directory)
            if not download_path.exists():
                try:
                    download_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"Cannot create download directory: {e}")
        
        return errors
    
    def is_configured(self, config: Configuration) -> bool:
        """Check if the application is properly configured."""
        return bool(
            config.jellyfin_server_url and 
            config.jellyfin_username and 
            config.jellyfin_api_key and
            config.local_media_paths
        )
    
    def create_default_env_file(self) -> None:
        """Create a default .env file with example values."""
        if not self.env_file.exists():
            env_content = """# RV Media Player Environment Variables
# Copy this file and update with your actual values

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=False

# Application Settings
LOG_LEVEL=INFO
"""
            with open(self.env_file, 'w') as f:
                f.write(env_content)
            
            # Set secure permissions
            os.chmod(self.env_file, 0o600)