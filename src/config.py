"""
Configuration management for danktunes.
"""
import json
import logging
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from logging_config import get_logger, ConfigurationError

logger = get_logger('config')


@dataclass
class AppConfig:
    """Application configuration settings."""
    
    # Music library
    music_directory: str = "~/Music"
    
    # Playlist settings
    playlist_directory: str = "~/.local/share/danktunes/playlists"
    auto_save_playlist: bool = True
    
    # Audio settings
    audio_player: str = "auto"  # auto, mpg123, aplay, ffplay
    volume_step: int = 5
    seek_seconds: int = 5
    
    # UI settings
    use_colors: bool = True
    use_borders: bool = True
    redraw_interval: float = 0.12
    
    # Search settings
    recursive_search_default: bool = True
    search_case_sensitive: bool = False
    
    # Performance settings
    max_cache_size: int = 5000
    async_duration_scanning: bool = True
    scan_workers: int = 4
    
    # Logging settings
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    # Advanced settings
    enable_debug: bool = False
    crash_reports: bool = True


class ConfigManager:
    """Manages configuration loading, saving, and validation."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config: AppConfig = AppConfig()
        self._load_config()
    
    def _get_default_config_path(self) -> Path:
        """Get default configuration file path."""
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "danktunes" / "config.json"
        return Path.home() / ".config" / "danktunes" / "config.json"
    
    def _load_config(self) -> None:
        """Load configuration from file."""
        if not self.config_path.exists():
            logger.info(f"Config file not found at {self.config_path}, using defaults")
            self._create_default_config()
            return
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                self._apply_config_data(data)
                logger.info(f"Loaded configuration from {self.config_path}")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config: {e}")
            logger.info("Using default configuration")
    
    def _create_default_config(self) -> None:
        """Create a default configuration file."""
        try:
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create default config
            default_data = asdict(self.config)
            
            with open(self.config_path, 'w') as f:
                json.dump(default_data, f, indent=2)
            
            logger.info(f"Created default config at {self.config_path}")
        except IOError as e:
            logger.warning(f"Failed to create default config: {e}")
    
    def _apply_config_data(self, data: Dict[str, Any]) -> None:
        """Apply configuration data to AppConfig object."""
        for key, value in data.items():
            if hasattr(self.config, key):
                try:
                    setattr(self.config, key, value)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Invalid config value for {key}: {value} ({e})")
    
    def save_config(self) -> bool:
        """Save current configuration to file."""
        try:
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            config_data = asdict(self.config)
            
            with open(self.config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info(f"Configuration saved to {self.config_path}")
            return True
            
        except IOError as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return getattr(self.config, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        if hasattr(self.config, key):
            setattr(self.config, key, value)
            logger.debug(f"Config updated: {key} = {value}")
    
    def validate_config(self) -> bool:
        """Validate current configuration."""
        issues = []
        
        # Validate music directory
        music_dir = Path(self.config.music_directory).expanduser()
        if not music_dir.exists():
            issues.append(f"Music directory does not exist: {music_dir}")
        
        # Validate audio player
        if self.config.audio_player not in ["auto", "mpg123", "aplay", "ffplay"]:
            issues.append(f"Invalid audio player: {self.config.audio_player}")
        
        # Validate numeric ranges
        if not (0 <= self.config.volume_step <= 20):
            issues.append(f"Volume step must be 1-20, got {self.config.volume_step}")
        
        if not (1 <= self.config.seek_seconds <= 30):
            issues.append(f"Seek seconds must be 1-30, got {self.config.seek_seconds}")
        
        if not (100 <= self.config.max_cache_size <= 100000):
            issues.append(f"Cache size must be 100-100000, got {self.config.max_cache_size}")
        
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.config.log_level not in valid_levels:
            issues.append(f"Invalid log level: {self.config.log_level}")
        
        if issues:
            logger.warning(f"Configuration validation issues: {issues}")
            return False
        
        return True
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults."""
        self.config = AppConfig()
        logger.info("Configuration reset to defaults")
    
    def get_music_directory_path(self) -> Path:
        """Get the actual path to music directory."""
        return Path(self.config.music_directory).expanduser()
    
    def get_playlist_directory_path(self) -> Path:
        """Get the actual path to playlist directory."""
        return Path(self.config.playlist_directory).expanduser()


# Global configuration manager
_config_manager = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def load_config(config_path: Optional[Path] = None) -> ConfigManager:
    """Load configuration and return manager."""
    return ConfigManager(config_path)


def save_config() -> bool:
    """Save current configuration."""
    manager = get_config_manager()
    return manager.save_config()


def get_config_value(key: str, default: Any = None) -> Any:
    """Get configuration value."""
    manager = get_config_manager()
    return manager.get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """Set configuration value."""
    manager = get_config_manager()
    manager.set(key, value)


def validate_current_config() -> bool:
    """Validate the current configuration."""
    manager = get_config_manager()
    return manager.validate_config()