#!/usr/bin/env python3
"""
Music Player - A terminal-based music player with playlist support.

This module provides a full-featured terminal music player with:
- File browser with directory tree navigation
- Audio playback using mpg123/aplay
- Playlist management with shuffle mode
- Speed control and seeking
- Keyboard shortcuts for all operations
"""

__version__ = "2.0.0"
__author__ = "DankTunes Team"
__description__ = "A terminal-based music player with playlist support, search, and audio playback."

# =============================================================================
# Imports
# =============================================================================
import fcntl
import os
import random
import re
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import OrderedDict

# Import logging configuration
try:
    from logging_config import setup_logging, get_logger
    logger = get_logger('main')
    # Initialize logging at startup
    setup_logging()
except ImportError:
    # Fallback to basic logging if config not available
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('main')


def validate_state():
    """Validate current state and fix common issues."""
    try:
        # Check for overlay conflicts
        overlays_active = sum([state.show_help, state.show_playlist, state.show_search])
        if overlays_active > 1:
            logger.warning(f"Multiple overlays active: {overlays_active}")
            # Fix overlay conflicts
            state.show_help = False
            state.show_playlist = False
            state.show_search = False
        
        # Check navigation bounds
        if state.flat_items and state.cursor >= len(state.flat_items):
            logger.warning(f"Cursor out of bounds: {state.cursor} >= {len(state.flat_items)}")
            state.cursor = max(0, len(state.flat_items) - 1)
        
        # Check playlist bounds
        if state.playlist and state.playlist_index >= len(state.playlist):
            logger.warning(f"Playlist index out of bounds: {state.playlist_index} >= {len(state.playlist)}")
            state.playlist_index = max(0, len(state.playlist) - 1)
        
        # Check playlist scroll offset bounds
        if state.playlist:
            visible = min(VISIBLE_PLAYLIST_ITEMS, len(state.playlist))
            max_offset = max(0, len(state.playlist) - visible)
            if state.playlist_scroll_offset > max_offset:
                logger.warning(f"Playlist scroll offset out of bounds: {state.playlist_scroll_offset}")
                state.playlist_scroll_offset = max_offset
        
        # Check volume bounds
        if state.volume < 0 or state.volume > 100:
            logger.warning(f"Volume out of bounds: {state.volume}")
            state.volume = max(0, min(100, state.volume))
        
        logger.debug("State validation completed")
        
    except Exception as e:
        logger.error(f"Error in state validation: {e}")

# =============================================================================
# Constants
# =============================================================================
REDRAW_INTERVAL: float = 0.12
SEEK_COOLDOWN: float = 0.3
MAX_TRACK_DURATIONS: int = 5000
CACHE_TRIM_SIZE: int = 1000
SPEED_MIN: float = 0.5
SPEED_MAX: float = 2.0
SPEED_STEP: float = 0.1
SEEK_SECONDS: int = 5
VISIBLE_PLAYLIST_ITEMS: int = 15

# Performance settings
DURATION_SCAN_WORKERS: int = 4
DURATION_SCAN_BATCH_SIZE: int = 100
ENABLE_PARALLEL_DURATION_SCAN: bool = True

# Audio file extensions
AUDIO_EXTENSIONS: Set[str] = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}

# External command cache
_command_cache: Dict[str, Optional[str]] = {}

def _find_command(cmd: str) -> Optional[str]:
    """Find an external command in PATH with caching.
    
    Args:
        cmd: Command name to find
        
    Returns:
        Path to command if found, None otherwise
    """
    if cmd in _command_cache:
        return _command_cache[cmd]
    result = shutil.which(cmd)
    _command_cache[cmd] = result
    return result

# =============================================================================
# Configuration
# =============================================================================
DEFAULT_CONFIG: str = """# Music Player Configuration
# Colors can be: black, red, green, yellow, blue, magenta, cyan, white,
# gray/bright_black, bright_red, bright_green, bright_yellow, bright_blue,
# bright_magenta, bright_cyan, bright_white, bold, dim, italic, underline,
# reverse, hidden, reset, default

[music]
# Path to your music library
directory = "~/Music"

[playlist]
# Directory to store playlist files
directory = "~/.local/share/music_player/playlists"

[colors]
# Color scheme for the UI
header = "bold"
secondary = "gray"
selection = "reverse"
text = "default"
"""

COLOR_MAP: Dict[str, str] = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
    "bright_black": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    "reverse": "\033[7m",
    "hidden": "\033[8m",
    "reset": "\033[0m",
    "default": "",
}


# =============================================================================
# Icons
# =============================================================================
class Icons:
    """Collection of Unicode icons used in the UI."""

    AUDIO: str = "\uf028"
    FOLDER: str = "\uf07c"
    FOLDER_CLOSED: str = "\uf07b"
    PLAY: str = "\uf04b"
    PAUSE: str = "\uf04c"
    STOP: str = "\uf04d"
    NEXT: str = "\uf051"
    PREV: str = "\uf048"
    SUNGLASSES: str = "\uf118"
    SHUFFLE: str = "\uf074"
    REPEAT: str = "\uf079"
    REPEAT_ONE: str = "\uf01d"
    MUSIC_NOTE: str = "\uf001"
    IMAGE: str = "\uf1c5"


# Terminal Image Protocols
# =============================================================================
class TerminalImageProtocol:
    """Support for various terminal image display protocols."""
    
    KITTY = "kitty"
    ITERM2 = "iterm2"
    SIXEL = "sixel"
    URXVT = "urxvt"
    KONSOLE = "konsole"
    UEBERZUG = "ueberzug"
    NONE = "none"
    
    _detected: Optional[str] = None
    
    @classmethod
    def detect(cls) -> str:
        """Detect the best available image protocol for this terminal."""
        if cls._detected:
            return cls._detected
        
        term = os.environ.get("TERM_PROGRAM", "")
        term_var = os.environ.get("TERM", "")
        colorterm = os.environ.get("COLORTERM", "")
        
        # Check for Ghostty (supports Kitty graphics protocol)
        if term.lower() == "ghostty":
            cls._detected = cls.KITTY
            return cls._detected
        
        # Check for WezTerm (supports Sixel and iTerm2)
        if term.lower() == "wezterm":
            if cls._check_sixel_support():
                cls._detected = cls.SIXEL
            elif cls._check_iterm2_inline():
                cls._detected = cls.ITERM2
            else:
                cls._detected = cls.SIXEL  # WezTerm has built-in Sixel
            return cls._detected
        
        # Check for Windows Terminal (supports iTerm2)
        if term.lower() == "windows-terminal" or "windows terminal" in term.lower():
            cls._detected = cls.ITERM2
            return cls._detected
        
        # Check for VSCode terminal (supports iTerm2)
        if "vscode" in term.lower():
            cls._detected = cls.ITERM2
            return cls._detected
        
        # Check for Kitty-specific environment variable
        if os.environ.get("KITTY_WINDOW_ID"):
            cls._detected = cls.KITTY
            return cls._detected
        
        if "iTerm.app" in term or "iTerm2" in term:
            cls._detected = cls.ITERM2
            return cls._detected
        
        if "kitty" in term_var.lower() or "kitty" in colorterm.lower():
            cls._detected = cls.KITTY
            return cls._detected
        
        if "sixel" in colorterm.lower() or "sixel" in term_var.lower():
            cls._detected = cls.SIXEL
            return cls._detected
        
        if "konsole" in term_var.lower():
            cls._detected = cls.KONSOLE
            return cls._detected
        
        if "rxvt" in term_var.lower() or "urxvt" in term_var.lower():
            cls._detected = cls.URXVT
            return cls._detected
        
        # Check for Alacritty - no native image support, try ueberzug
        if "alacritty" in term_var.lower():
            if cls._check_ueberzug_support():
                cls._detected = cls.UEBERZUG
                return cls._detected
        
        # GNOME Terminal and other mainstream terminals - try iTerm2 then Sixel
        if "gnome" in term_var.lower() or "vte" in term_var.lower():
            if cls._check_iterm2_inline():
                cls._detected = cls.ITERM2
                return cls._detected
            if cls._check_sixel_support():
                cls._detected = cls.SIXEL
                return cls._detected
        
        if cls._check_ueberzug_support():
            cls._detected = cls.UEBERZUG
            return cls._detected
        
        if "xterm" in term_var.lower():
            if cls._check_iterm2_inline():
                cls._detected = cls.ITERM2
                return cls._detected
            if cls._check_sixel_support():
                cls._detected = cls.SIXEL
                return cls._detected
        
        cls._detected = cls.NONE
        return cls._detected
    
    @classmethod
    def _check_iterm2_inline(cls) -> bool:
        """Check if iTerm2 inline image support is available."""
        return bool(os.environ.get("ITERM2_SOCKET_PATH"))
    
    @classmethod
    def _check_sixel_support(cls) -> bool:
        """Check if Sixel is supported."""
        return False
    
    @classmethod
    def _check_ueberzug_support(cls) -> bool:
        """Check if ueberzug is available."""
        result = subprocess.run(
            ["which", "ueberzug"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    @classmethod
    def get_protocol_name(cls) -> str:
        """Get human-readable protocol name."""
        name = cls.detect()
        return {
            cls.KITTY: "Kitty",
            cls.ITERM2: "iTerm2",
            cls.SIXEL: "Sixel",
            cls.URXVT: "urxvt",
            cls.KONSOLE: "Konsole",
            cls.UEBERZUG: "ueberzug",
            cls.NONE: "None (disabled)",
        }.get(name, "Unknown")


def print_image_iterm2(path: str, width: Optional[int] = None, height: Optional[int] = None) -> str:
    """Print image using iTerm2 inline image protocol.
    
    Args:
        path: Path to image file
        width: Optional width in cells
        height: Optional height in cells
        
    Returns:
        Escape sequence string
    """
    try:
        import base64
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        
        args = []
        if width:
            args.append(f"width={width}")
        if height:
            args.append(f"height={height}")
        
        param = ";".join(args) if args else ""
        
        return f"\033]1337;File=inline=1{';' + param if param else ''}:{data}\a"
    except Exception:
        return ""


def print_image_kitty(path: str, width: Optional[int] = None, height: Optional[int] = None,
                     x: int = 0, y: int = 0, clear: bool = False) -> str:
    """Print image using Kitty inline graphics protocol via kitty icat.
    
    Args:
        path: Path to image file
        width: Optional width in cells
        height: Optional height in cells
        x: X position (cells from left)
        y: Y position (cells from top)
        clear: Clear existing image first
        
    Returns:
        Command string to display image via kitty icat
    """
    try:
        cmd = ["kitty", "+kitten", "icat"]
        
        if clear:
            cmd.append("--clear")
        
        if width or height:
            place = f"{width or 40}x{height or 20}@{x or 0}x{y or 0}"
            cmd.extend(["--place", place])
        
        cmd.append(path)
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            return result.stdout
        return ""
    except Exception:
        return ""


def print_image_sixel(path: str) -> str:
    """Print image using Sixel graphics protocol (requires img2sixel).
    
    Args:
        path: Path to image file
        
    Returns:
        Escape sequence string
    """
    try:
        result = subprocess.run(
            ["img2sixel", "-w", "60", path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout
        return ""
    except Exception:
        return ""


def print_image_urxvt(path: str) -> str:
    """Print image using urxvt background extension.
    
    Args:
        path: Path to image file
        
    Returns:
        Escape sequence string
    """
    try:
        return f"\033]20;{path};100;oT\a"
    except Exception:
        return ""


def print_image_konsole(path: str) -> str:
    """Print image using Konsole background image feature.
    
    Args:
        path: Path to image file
        
    Returns:
        Escape sequence string
    """
    try:
        return f"\033]40;file://{path}\a"
    except Exception:
        return ""


def print_image_ueberzug(path: str, width: Optional[int] = None, height: Optional[int] = None,
                        x: int = 0, y: int = 0) -> str:
    """Print image using ueberzug.
    
    Args:
        path: Path to image file
        width: Optional width in cells
        height: Optional height in cells
        x: X position (cells from left)
        y: Y position (cells from top)
        
    Returns:
        Command string for ueberzug (not an escape sequence)
    """
    import json
    
    action = {
        "action": "add",
        "identifier": "danktunes-cover",
        "path": path,
        "x": x,
        "y": y,
        "scaler": "contain"
    }
    
    if width:
        action["width"] = width
    if height:
        action["height"] = height
    
    return json.dumps(action)


def clear_ueberzug() -> str:
    """Clear ueberzug image."""
    import json
    return json.dumps({"action": "remove", "identifier": "danktunes-cover"})


def print_image(path: str, width: Optional[int] = None, height: Optional[int] = None,
                x: int = 0, y: int = 0) -> str:
    """Print image using the best available protocol.
    
    Args:
        path: Path to image file
        width: Optional width in cells
        height: Optional height in cells
        x: X position (cells from left)
        y: Y position (cells from top)
        
    Returns:
        Escape sequence string, or empty string if not supported
    """
    protocol = TerminalImageProtocol.detect()
    
    if protocol == TerminalImageProtocol.ITERM2:
        return print_image_iterm2(path, width, height)
    elif protocol == TerminalImageProtocol.KITTY:
        return print_image_kitty(path, width, height, x, y)
    elif protocol == TerminalImageProtocol.SIXEL:
        return print_image_sixel(path)
    elif protocol == TerminalImageProtocol.URXVT:
        return print_image_urxvt(path)
    elif protocol == TerminalImageProtocol.KONSOLE:
        return print_image_konsole(path)
    elif protocol == TerminalImageProtocol.UEBERZUG:
        return print_image_ueberzug(path, width, height, x, y)
    
    return ""


def clear_images() -> str:
    """Clear all inline images.
    
    Returns:
        Escape sequence string
    """
    protocol = TerminalImageProtocol.detect()
    
    if protocol == TerminalImageProtocol.KITTY:
        return "\033_Ga\033\\"
    elif protocol == TerminalImageProtocol.ITERM2:
        return "\033]1337;CleanAllFiles\a"
    
    return ""


# =============================================================================
# Classes
# =============================================================================
class TreeItem:
    """Represents a file or directory in the music library tree.

    Attributes:
        path: Path to the file or directory
        level: Depth in the directory tree
        is_dir: Whether this item is a directory
        parent: Parent TreeItem (None for root items)
        children: List of child TreeItems (for directories)
        expanded: Whether the directory is expanded
    """
    
    __slots__ = ('path', 'level', 'is_dir', 'parent', 'children', 'expanded')

    def __init__(
        self,
        path: Union[Path, str],
        level: int = 0,
        is_dir: bool = False,
        parent: Optional["TreeItem"] = None,
    ) -> None:
        self.path: Path = path if isinstance(path, Path) else Path(path)
        self.level: int = level
        self.is_dir: bool = is_dir
        self.parent: Optional["TreeItem"] = parent
        self.children: List["TreeItem"] = []
        self.expanded: bool = False


@dataclass
class PlayerState:
    """Holds all player state in a single container.

    This class replaces scattered global variables with a single
    organized data structure for better maintainability.
    """

    # Paths and configuration
    music_dir: Path = field(default_factory=lambda: Path.home() / "Music")
    playlist_dir: Path = field(
        default_factory=lambda: Path.home() / ".local/share/music_player/playlists"
    )

    # Current playback
    current_file: Optional[str] = None
    current_path: Optional[str] = None
    current_position: float = 0.0
    effect_speed: float = 1.0
    volume: int = 100

    # Metadata
    current_artist: Optional[str] = None
    current_title: Optional[str] = None

    # Audio process
    process: Optional[subprocess.Popen] = None
    playback_start_time: Optional[float] = None
    current_player: Optional[str] = None

    # UI state
    cursor: int = 0
    scroll_offset: int = 0
    expanded_dirs: Set[str] = field(default_factory=set)
    flat_items: List[TreeItem] = field(default_factory=list)
    tree_items: List[TreeItem] = field(default_factory=list)

    # Playlist
    playlist: List[str] = field(default_factory=list)
    playlist_index: int = 0
    playlist_index_map: Dict[str, int] = field(default_factory=dict)
    playlist_scroll_offset: int = 0
    shuffle_mode: bool = False
    show_playlist: bool = False
    repeat_mode: str = "off"

    # Timing
    last_seek_time: float = 0.0
    paused: bool = False  # Whether playback is currently paused

    # Cache - Use OrderedDict for LRU behavior
    track_durations: Dict[str, float] = field(default_factory=lambda: OrderedDict())

    # Help
    show_help: bool = False

# Search
    show_search: bool = False
    search_query: str = ""
    search_results: List[str] = field(default_factory=list)
    search_cursor: int = 0
    recursive_search_results: List[Dict[str, Any]] = field(default_factory=list)
    search_mode: str = "flat"  # "flat" or "recursive"

    # Album Art Overlay
    show_album_art: bool = False

    # Sorting
    sort_by: str = "name"  # "name", "date", "duration"
    sort_reverse: bool = False

    # Favorites
    favorites: List[str] = field(default_factory=list)

    # Smart shuffle history
    shuffle_history: List[str] = field(default_factory=list)
    shuffle_history_max: int = 20


# =============================================================================
# Global State Instance
# =============================================================================
state = PlayerState()


# =============================================================================
# Configuration Functions
# =============================================================================
def _get_config_dir() -> Path:
    """Get the configuration directory following XDG spec.

    Returns:
        Path to the config directory (~/.config/danktunes by default)
    """
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "danktunes"
    return Path.home() / ".config" / "danktunes"


# Global config directory (used by main)
CONFIG_DIR = _get_config_dir()


def _init_config(config_dir: Path, config_file: Path) -> bool:
    """Initialize default config file if it doesn't exist.

    Args:
        config_dir: Directory for configuration files
        config_file: Path to the main config file

    Returns:
        True if config was created, False if it already existed
    """
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

    if not config_file.exists():
        with open(config_file, "w") as f:
            f.write(DEFAULT_CONFIG)
        return True
    return False


def _load_config() -> Tuple[Dict[str, Any], bool]:
    """Load configuration from TOML file.

    Returns:
        Tuple of (config dictionary, whether config was created)
    """
    config_dir = _get_config_dir()
    config_file = config_dir / "danktunes.toml"
    created = _init_config(config_dir, config_file)

    config = {
        "music": {"directory": "~/Music"},
        "playlist": {"directory": str(Path.home() / ".config/danktunes/playlists")},
        "colors": {
            "header": "bold",
            "secondary": "gray",
            "selection": "reverse",
            "text": "default",
        },
        "ui": {
            "borders": False,
            "header_glyph": "😎",
        },
        "notifications": {
            "enabled": False,
            "glyph": "🎵",
        },
    }

    if config_file.exists():
        try:
            # Try Python 3.11+ tomllib first
            try:
                import tomllib

                with open(config_file, "rb") as f:
                    user_config = tomllib.load(f)
            except ImportError:
                # Fall back to tomli if available
                try:
                    import tomli

                    with open(config_file, "rb") as f:
                        user_config = tomli.load(f)
                except ImportError:
                    print(
                        "Warning: No TOML parser available (tomllib or tomli), using defaults"
                    )
                    return config, created

            # Merge user config with defaults
            for section in config:
                if section in user_config and isinstance(user_config[section], dict):
                    config[section].update(user_config[section])
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")

    return config, created


# Load configuration
_config, _config_created = _load_config()

# Color scheme from config
C_HEADER = COLOR_MAP.get(_config["colors"]["header"], COLOR_MAP["bold"])
C_SECONDARY = COLOR_MAP.get(_config["colors"]["secondary"], COLOR_MAP["gray"])
C_SELECTION = COLOR_MAP.get(_config["colors"]["selection"], COLOR_MAP["reverse"])
C_TEXT = COLOR_MAP.get(_config["colors"]["text"], "")
C_RESET = COLOR_MAP["reset"]

# UI options
USE_BORDERS = _config.get("ui", {}).get("borders", False)
HEADER_GLYPH = _config.get("ui", {}).get("header_glyph", "😎")

# Album art options
ALBUM_ART_ENABLED = _config.get("album_art", {}).get("enabled", True)
ALBUM_ART_WIDTH = _config.get("album_art", {}).get("width", 20)
last_album_art_path = None  # Track last displayed album art for overlay
last_album_art_track = None  # Track last displayed track for overlay

# Notification options
NOTIFICATIONS_ENABLED = _config.get("notifications", {}).get("enabled", False)
NOTIFICATION_GLYPH = _config.get("notifications", {}).get("glyph", "🎵")

# Ranger-style border characters
BORDER_TL = "┌"  # Top-left
BORDER_TR = "┐"  # Top-right
BORDER_BL = "└"  # Bottom-left
BORDER_BR = "┘"  # Bottom-right
BORDER_H = "─"  # Horizontal
BORDER_V = "│"  # Vertical
BORDER_X = "┼"  # Cross (for column dividers)
BORDER_LT = "├"  # Left T (for section dividers)
BORDER_RT = "┤"  # Right T (for section dividers)


def _get_state_file() -> Path:
    """Get the path to the state file."""
    return CONFIG_DIR / "state.json"


def save_state() -> bool:
    """Save current player state to disk.

    Saves: volume, last played track, position, expanded directories.

    Returns:
        True if state was saved successfully, False otherwise
    """
    try:
        state_data = {
            "volume": state.volume,
            "last_track": state.current_path,
            "last_position": state.current_position,
            "expanded_dirs": list(state.expanded_dirs),
            "shuffle_mode": state.shuffle_mode,
            "repeat_mode": state.repeat_mode,
        }

        state_file = _get_state_file()
        state_file.parent.mkdir(parents=True, exist_ok=True)

        with open(state_file, "w") as f:
            import json
            json.dump(state_data, f)

        logger.debug(f"State saved to {state_file}")
        return True
    except Exception as e:
        logger.warning(f"Failed to save state: {e}")
        return False


def load_state() -> bool:
    """Load saved player state from disk.

    Loads: volume, last played track, position, expanded directories.

    Returns:
        True if state was loaded successfully, False otherwise
    """
    try:
        state_file = _get_state_file()
        if not state_file.exists():
            logger.debug("No saved state found")
            return False

        with open(state_file, "r") as f:
            import json
            state_data = json.load(f)

        if "volume" in state_data:
            state.volume = max(0, min(100, state_data["volume"]))

        if "expanded_dirs" in state_data:
            state.expanded_dirs = set(state_data["expanded_dirs"])

        if "shuffle_mode" in state_data:
            state.shuffle_mode = state_data["shuffle_mode"]

        if "repeat_mode" in state_data:
            state.repeat_mode = state_data["repeat_mode"]

        logger.debug(f"State loaded from {state_file}")
        return True
    except Exception as e:
        logger.warning(f"Failed to load state: {e}")
        return False


def _get_terminal_size() -> tuple:
    """Get actual terminal size using ioctl with fallback to shutil."""
    try:
        if sys.stdout.isatty():
            winsize = struct.pack("HHHH", 0, 0, 0, 0)
            result = fcntl.ioctl(sys.stdout.fileno(), 0x5413, winsize)
            rows, cols, xpix, ypix = struct.unpack("HHHH", result)
            if rows > 0 and cols > 0:
                return (rows, cols)
    except Exception:
        pass

    # Fallback to /dev/tty
    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
        try:
            winsize = struct.pack("HHHH", 0, 0, 0, 0)
            result = fcntl.ioctl(fd, 0x5413, winsize)
            rows, cols, xpix, ypix = struct.unpack("HHHH", result)
            if rows > 0 and cols > 0:
                return (rows, cols)
        finally:
            os.close(fd)
    except Exception:
        pass

    # Final fallback
    import shutil

    return shutil.get_terminal_size()


def _send_notification(title: str, message: str) -> None:
    """Send a desktop notification.

    Args:
        title: Notification title
        message: Notification body text
    """
    if not NOTIFICATIONS_ENABLED:
        return

    try:
        notify_send = _find_command("notify-send")
        if notify_send:
            subprocess.run(
                [
                    "notify-send",
                    "--app-name=danktunes",
                    f"{NOTIFICATION_GLYPH} {title}",
                    message,
                ],
                capture_output=True,
                check=False,
            )
    except Exception:
        pass


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for accurate length calculation."""
    # More robust ANSI CSI sequence removal (covers common control sequences)
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


@lru_cache(maxsize=4096)
def _char_display_width(ch: str) -> int:
    """Return display width of a single Unicode character (0, 1 or 2)."""
    if not ch:
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    ea = unicodedata.east_asian_width(ch)
    if ea in ("F", "W"):
        return 2
    return 1


@lru_cache(maxsize=4096)
def _display_width(text: str) -> int:
    """Return the visible terminal width of `text`, ignoring ANSI escapes."""
    s = _strip_ansi(text)
    return sum(_char_display_width(ch) for ch in s)


def _truncate_to_width(text: str, max_width: int, ellipsis: str = "...") -> str:
    """Truncate `text` (plain text) to fit in `max_width` display columns.

    Adds `ellipsis` when there's room; otherwise hard-truncates to fit.
    """
    if max_width <= 0:
        return ""
    if _display_width(text) <= max_width:
        return text

    e_width = _display_width(ellipsis)
    
    if e_width >= max_width:
        # Hard-truncate without ellipsis
        target = max_width
    else:
        # Leave room for ellipsis
        target = max_width - e_width
    
    out = []
    cur = 0
    for ch in text:
        w = _char_display_width(ch)
        if cur + w > target:
            break
        out.append(ch)
        cur += w
    
    if e_width >= max_width:
        return "".join(out)
    return "".join(out) + ellipsis


def get_duration(path: str) -> Optional[float]:
    """Get audio file duration using ffprobe.

    Args:
        path: Path to the audio file

    Returns:
        Duration in seconds, or None if unavailable
    """
    # Use combined function for efficiency
    duration, _, _ = get_duration_and_metadata(path)
    return duration


def get_metadata(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Get artist and title metadata from audio file using ffprobe.

    Args:
        path: Path to the audio file

    Returns:
        Tuple of (artist, title), or (None, None) if unavailable
    """
    _, artist, title = get_duration_and_metadata(path)
    return (artist, title)


def _get_duration_mpg123(path: str) -> Optional[float]:
    """Get duration using mpg123 -t (fast test mode).
    
    Args:
        path: Path to the audio file
        
    Returns:
        Duration in seconds, or None if unavailable
    """
    mpg123 = _find_command("mpg123")
    if not mpg123:
        return None
    
    try:
        result = subprocess.run(
            [mpg123, "-t", "--skip-printing-frames", str(path)],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 or result.returncode == 1:
            for line in result.stderr.split("\n"):
                if " Frames" in line or "frames" in line.lower():
                    import re
                    match = re.search(r'(\d+)\s*[Ff]rames?', line)
                    if match:
                        frames = int(match.group(1))
                        return frames * 1152 / 44100
            for line in result.stderr.split("\n"):
                if "Total time:" in line:
                    import re
                    match = re.search(r'(\d+):(\d+)', line)
                    if match:
                        mins = int(match.group(1))
                        secs = int(match.group(2))
                        return mins * 60 + secs
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _get_metadata_ffprobe(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Get artist/title metadata using ffprobe (separate call for metadata only).
    
    Args:
        path: Path to the audio file
        
    Returns:
        Tuple of (artist, title)
    """
    ffprobe = _find_command("ffprobe")
    if not ffprobe:
        return (None, None)
    
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format_tags=artist,title",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            artist = lines[0] if len(lines) > 0 else None
            title = lines[1] if len(lines) > 1 else None
            return (artist, title)
        return (None, None)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return (None, None)


@lru_cache(maxsize=4096)
def get_duration_and_metadata(path: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """Get duration using mpg123 and metadata using ffprobe.

    Args:
        path: Path to the audio file

    Returns:
        Tuple of (duration, artist, title)
    """
    duration = _get_duration_mpg123(path)
    artist, title = _get_metadata_ffprobe(path)
    return (duration, artist, title)


_album_art_cache: Dict[str, Optional[str]] = {}
_cover_names = frozenset([
    "cover.jpg", "cover.png", "cover.jpeg", "cover.webp",
    "folder.jpg", "folder.png", "folder.jpeg", "folder.webp",
    "album.jpg", "album.png", "album.jpeg", "album.webp",
    "front.jpg", "front.png", "front.jpeg", "front.webp",
])
_dir_cover_cache: Dict[str, Optional[str]] = {}


def get_album_art(path: str) -> Optional[str]:
    """Get album art for an audio file.
    
    First checks for local cover images in the same directory,
    then tries to extract embedded art using ffmpeg.
    
    Args:
        path: Path to the audio file
        
    Returns:
        Path to album art image, or None if not found
    """
    if path in _album_art_cache:
        return _album_art_cache[path]
    
    audio_path = Path(path)
    if not audio_path.exists():
        try:
            audio_path = Path(path).resolve()
        except Exception:
            _album_art_cache[path] = None
            return None
    
    directory = str(audio_path.parent)
    
    if directory in _dir_cover_cache:
        local_cover = _dir_cover_cache[directory]
    else:
        local_cover = _find_local_album_art(audio_path, directory)
        _dir_cover_cache[directory] = local_cover
    
    if local_cover:
        _album_art_cache[path] = local_cover
        return local_cover
    
    result = _extract_embedded_album_art(path)
    _album_art_cache[path] = result
    return result


def _find_local_album_art(audio_path: Path, directory: str) -> Optional[str]:
    """Look for local cover images in the track's directory."""
    try:
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return None
        
        for name in os.listdir(dir_path):
            if name.lower() in _cover_names:
                cover_path = dir_path / name
                if cover_path.is_file():
                    return str(cover_path)
    except OSError:
        pass
    return None


def _extract_embedded_album_art(path: str) -> Optional[str]:
    """Extract embedded album art using ffmpeg."""
    import tempfile
    
    try:
        audio_path = Path(path)
        if not audio_path.exists():
            audio_path = Path(path).resolve()
        
        directory = audio_path.parent
        
        with tempfile.NamedTemporaryFile(
            suffix=".jpg", 
            dir=directory, 
            delete=False
        ) as tmp:
            tmp_path = tmp.name
        
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(audio_path),
                "-an",
                "-vcodec", "copy",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        
        if result.returncode == 0 and Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
            return tmp_path
        else:
            if Path(tmp_path).exists():
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass
            return None
            
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return None


def clear_album_art_cache() -> None:
    """Clear the album art cache."""
    global _album_art_cache
    _album_art_cache = {}


def _collect_audio_files(items: List[TreeItem]) -> List[str]:
    """Collect all audio file paths from tree items.
    
    Args:
        items: List of tree items
        
    Returns:
        List of audio file paths
    """
    paths = []
    for item in items:
        if item.is_dir and item.children:
            paths.extend(_collect_audio_files(item.children))
        else:
            paths.append(str(item.path))
    return paths


def _scan_duration_batch(paths: List[str], cached_paths: Optional[Set[str]] = None) -> Dict[str, float]:
    """Scan durations for a batch of paths.
    
    Args:
        paths: List of audio file paths
        cached_paths: Set of already cached paths (for exclusion)
        
    Returns:
        Dictionary mapping path to duration
    """
    results = {}
    for path_str in paths:
        if cached_paths and path_str in cached_paths:
            continue
        duration = get_duration(path_str)
        if duration:
            results[path_str] = duration
    return results


def scan_all_durations(items: List[TreeItem]) -> int:
    """Scan all audio files in the tree and cache their durations.

    Args:
        items: List of tree items to scan

    Returns:
        Number of durations cached
    """
    import concurrent.futures
    
    audio_paths = _collect_audio_files(items)
    if not audio_paths:
        return 0
    
    cached_paths = set(state.track_durations.keys())
    uncached = [p for p in audio_paths if p not in cached_paths]
    if not uncached:
        return 0
    
    count = 0
    
    if ENABLE_PARALLEL_DURATION_SCAN and len(uncached) > DURATION_SCAN_BATCH_SIZE:
        batches = [
            uncached[i:i + DURATION_SCAN_BATCH_SIZE] 
            for i in range(0, len(uncached), DURATION_SCAN_BATCH_SIZE)
        ]
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=DURATION_SCAN_WORKERS) as executor:
            futures = [executor.submit(_scan_duration_batch, batch, cached_paths) for batch in batches]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    results = future.result()
                    for path_str, duration in results.items():
                        if len(state.track_durations) >= MAX_TRACK_DURATIONS:
                            for _ in range(CACHE_TRIM_SIZE):
                                if state.track_durations:
                                    del state.track_durations[next(iter(state.track_durations))]
                        
                        state.track_durations[path_str] = duration
                        count += 1
                except Exception:
                    pass
    else:
        for path_str in uncached:
            duration = get_duration(path_str)
            if duration:
                if len(state.track_durations) >= MAX_TRACK_DURATIONS:
                    for _ in range(CACHE_TRIM_SIZE):
                        if state.track_durations:
                            del state.track_durations[next(iter(state.track_durations))]
                state.track_durations[path_str] = duration
                count += 1
    
    return count


def flatten_tree(
    items: List[TreeItem], result: Optional[List[TreeItem]] = None
) -> List[TreeItem]:
    """Flatten tree structure into a list.

    Args:
        items: List of tree items
        result: Accumulator list (for recursion)

    Returns:
        Flattened list of all items
    """
    if result is None:
        result = []
    
    # Use iterative approach with stack for better performance
    stack = list(reversed(items))
    
    while stack:
        item = stack.pop()
        result.append(item)
        if item.is_dir and item.expanded and item.children:
            # Add children in reverse order so they're processed in correct order
            stack.extend(reversed(item.children))
    
    return result


def _format_duration(seconds: float) -> str:
    """Format duration in MM:SS format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string
    """
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


# Directory scan cache: path -> (mtime, items) - using OrderedDict for O(1) LRU eviction
_dir_cache: OrderedDict[str, Tuple[float, List["TreeItem"]]] = OrderedDict()
DIR_CACHE_MAX_SIZE: int = 100


def _get_cached_directory(path: Path, level: int) -> Optional[List["TreeItem"]]:
    """Get cached directory scan results if valid.
    
    Args:
        path: Directory path
        level: Nesting level
        
    Returns:
        Cached items or None if cache is invalid/missing
    """
    path_str = str(path)
    if path_str not in _dir_cache:
        return None
    
    try:
        mtime = os.path.getmtime(path_str)
        cached_mtime, items = _dir_cache[path_str]
        if mtime != cached_mtime:
            del _dir_cache[path_str]
            return None
        _dir_cache.move_to_end(path_str)
        return items
    except OSError:
        return None


def _cache_directory(path: Path, level: int, items: List["TreeItem"]) -> None:
    """Cache directory scan results.
    
    Args:
        path: Directory path  
        level: Nesting level
        items: Scanned items
    """
    path_str = str(path)
    
    if path_str in _dir_cache:
        _dir_cache.move_to_end(path_str)
    
    while len(_dir_cache) >= DIR_CACHE_MAX_SIZE:
        del _dir_cache[next(iter(_dir_cache))]
    
    try:
        mtime = os.path.getmtime(str(path))
        _dir_cache[path_str] = (mtime, items)
    except OSError:
        pass


def scan_directory(path: Path, level: int = 0) -> List[TreeItem]:
    """Scan a directory and return tree items.

    Args:
        path: Directory path to scan
        level: Current nesting level

    Returns:
        List of tree items
    """
    cached = _get_cached_directory(path, level)
    if cached is not None:
        return cached
    
    items = []
    dirs = []
    files = []
    
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        dirs.append(entry.name)
                    elif entry.is_file(follow_symlinks=False):
                        suffix = Path(entry.name).suffix.lower()
                        if suffix in AUDIO_EXTENSIONS:
                            files.append(entry.name)
                except (OSError, PermissionError):
                    continue
        
        dirs.sort()
        files.sort()
        
        for entry in dirs:
            full_path = os.path.join(path, entry)
            item = TreeItem(full_path, level, True)
            if str(full_path) in state.expanded_dirs:
                item.children = scan_directory(Path(full_path), level + 1)
                item.expanded = True
            items.append(item)

        for entry in files:
            full_path = os.path.join(path, entry)
            items.append(TreeItem(full_path, level, False))
    except (OSError, PermissionError):
        pass
    
    _cache_directory(path, level, items)
    
    return items


def play(path: Union[str, Path], start_pos: int = 0, notify: bool = True) -> bool:
    """Play an audio file with optional starting position.

    Args:
        path: Path to the audio file
        start_pos: Starting position in seconds (default: 0)
        notify: Whether to send desktop notification (default: True)

    Returns:
        True if playback started successfully, False otherwise
    """
    if not path or not isinstance(path, (str, Path)):
        state.current_file = "Error: Invalid path"
        return False

    try:
        resolved_path = Path(path).resolve()
        music_dir_resolved = state.music_dir.resolve()
        if not str(resolved_path).startswith(str(music_dir_resolved)):
            state.current_file = "Error: Path outside music directory"
            return False
    except Exception:
        state.current_file = "Error: Invalid path"
        return False

    if (
        state.process
        and state.process.poll() is None
        and state.current_path == str(resolved_path)
        and start_pos == 0
    ):
        return True

    stop_audio()

    try:
        if not os.path.exists(resolved_path):
            state.current_file = "Error: File not found"
            return False

        ext = resolved_path.suffix.lower()

        if ext == ".wav":
            aplay = _find_command("aplay")
            if aplay:
                cmd = [aplay, str(resolved_path)]
                state.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                )
                state.current_player = "aplay"
            else:
                state.current_file = "Error: aplay not found"
                return False
        else:
            mpg123 = _find_command("mpg123")
            if not mpg123:
                state.current_file = "Error: mpg123 not found"
                return False

            cmd = [mpg123, "-q", "--no-control", "-a", "alsa", "--fuzzy"]

            if state.volume != 100:
                mpg_vol = int(state.volume * 2.55)
                cmd.extend(["--vol", str(mpg_vol)])

            if start_pos > 0:
                frames_per_second = 44100 / 1152
                frame_skip = int(start_pos * frames_per_second)
                cmd.extend(["--skip", str(max(1, frame_skip))])

            if state.effect_speed != 1.0:
                pitch_val = state.effect_speed - 1.0
                pitch_val = max(-0.9, min(3.0, pitch_val))
                cmd.extend(["--pitch", str(round(pitch_val, 2))])

            cmd.append(str(resolved_path))

            state.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )
            state.current_player = "mpg123"

        state.current_file = resolved_path.name
        state.current_path = str(resolved_path)
        state.current_position = start_pos
        state.playback_start_time = time.time()

        path_str = str(resolved_path)
        if path_str not in state.track_durations:
            duration = get_duration(path_str)
            if duration:
                state.track_durations[path_str] = duration

        if path_str in state.playlist_index_map:
            state.playlist_index = state.playlist_index_map[path_str]

        # Extract metadata
        artist, title = get_metadata(path_str)
        state.current_artist = artist
        state.current_title = title

        # Send notification only if notify is True
        if notify:
            if artist and title:
                _send_notification("Now Playing", f"{artist} - {title}")
            elif title:
                _send_notification("Now Playing", title)
            else:
                _send_notification("Now Playing", resolved_path.name)

        return True

    except Exception as e:
        state.current_file = f"Error: {str(e)[:50]}"
        return False


def stop_audio() -> None:
    """Stop any currently playing audio and clear playback state."""
    try:
        if state.process and state.process.poll() is None:
            try:
                # Try graceful termination first
                os.killpg(os.getpgid(state.process.pid), signal.SIGTERM)
                state.process.wait(timeout=1.0)
                logger.info(f"Gracefully stopped audio process: {state.process.pid}")
            except (ProcessLookupError, PermissionError) as e:
                logger.warning(f"Process lookup/permission error during stop: {e}")
                pass  # Process may have already terminated
            except subprocess.TimeoutExpired:
                try:
                    # Force kill if graceful termination failed
                    os.killpg(os.getpgid(state.process.pid), signal.SIGKILL)
                    state.process.wait(timeout=0.5)
                    logger.warning(f"Force killed audio process: {state.process.pid}")
                except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Force kill failed: {e}")
                    pass  # Process may be zombie or already terminated
        else:
            logger.debug("No active process to stop")
    except Exception as e:
        logger.error(f"Unexpected error during audio stop: {e}")
        pass  # Ignore any other exceptions during cleanup
    finally:
        # Always clear state, even if cleanup failed
        state.process = None
        state.current_file = None
        state.current_path = None
        state.playback_start_time = None
        state.current_position = 0
        state.current_artist = None
        state.current_title = None
        state.current_player = None
        state.paused = False
        logger.info("Audio playback state cleared")


def toggle_pause() -> None:
    """Toggle pause state by pausing/resuming audio."""
    if state.process and state.process.poll() is None:
        if state.current_player == "mpg123":
            # Send pause/resume command to mpg123
            try:
                if state.paused:
                    # Resume playback
                    os.killpg(os.getpgid(state.process.pid), signal.SIGCONT)
                    state.paused = False
                else:
                    # Pause playback
                    os.killpg(os.getpgid(state.process.pid), signal.SIGSTOP)
                    state.paused = True
            except Exception:
                pass
        elif state.current_player == "aplay":
            # aplay doesn't support pause, so we need to stop and resume
            try:
                if state.paused:
                    # Resume playback from saved position
                    if state.current_path and state.current_position > 0:
                        play(state.current_path, int(state.current_position))
                        state.paused = False
                else:
                    # Pause by stopping and saving position
                    if state.process and state.process.poll() is None:
                        # Save current position before stopping
                        elapsed = (
                            time.time()
                            - (state.playback_start_time or time.time())
                            + state.current_position
                        )
                        # Stop audio but preserve state
                        try:
                            os.killpg(os.getpgid(state.process.pid), signal.SIGTERM)
                            try:
                                state.process.wait(timeout=0.1)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        state.current_position = elapsed
                        state.paused = True
                        state.process = None
            except Exception:
                pass
    else:
        # Resume playback if paused (process was stopped)
        if hasattr(state, "paused") and state.paused:
            if state.current_path and state.current_position > 0:
                play(state.current_path, int(state.current_position))
                state.paused = False
        elif state.cursor < len(state.flat_items):
            item = state.flat_items[state.cursor]
            if not item.is_dir:
                play(str(item.path))




# =============================================================================
# Playlist Functions
# =============================================================================


def add_to_playlist(path: str) -> None:
    """Add a track to the playlist.

    Args:
        path: Path to the audio file
    """
    state.playlist.append(path)
    state.playlist_index_map[path] = len(state.playlist) - 1


def _rebuild_playlist_map() -> None:
    """Rebuild the playlist index map for O(1) lookups."""
    state.playlist_index_map = {
        path: idx for idx, path in enumerate(state.playlist)
    }


def remove_from_playlist(index: int) -> None:
    """Remove a track from the playlist.

    Args:
        index: Index of the track to remove
    """
    if 0 <= index < len(state.playlist):
        removed_path = state.playlist.pop(index)
        state.playlist_index_map.pop(removed_path, None)
        _rebuild_playlist_map()
        if state.playlist_index >= len(state.playlist):
            state.playlist_index = 0
            state.playlist_scroll_offset = 0


def clear_playlist() -> None:
    """Clear the entire playlist."""
    state.playlist = []
    state.playlist_index_map = {}
    state.playlist_index = 0
    state.playlist_scroll_offset = 0


def toggle_shuffle_mode() -> None:
    """Toggle shuffle mode on/off."""
    state.shuffle_mode = not state.shuffle_mode

    if state.shuffle_mode and state.playlist:
        current = (
            state.playlist[state.playlist_index]
            if state.playlist_index < len(state.playlist)
            else None
        )
        random.shuffle(state.playlist)
        if current and current in state.playlist_index_map:
            state.playlist_index = state.playlist_index_map[current]
        else:
            state.playlist_index = 0
            state.playlist_scroll_offset = 0
        _rebuild_playlist_map()


def toggle_repeat_mode() -> None:
    """Cycle through repeat modes: off -> all -> one -> off."""
    modes = ["off", "all", "one"]
    current_idx = modes.index(state.repeat_mode) if state.repeat_mode in modes else 0
    next_idx = (current_idx + 1) % len(modes)
    state.repeat_mode = modes[next_idx]


def cycle_sort_mode() -> None:
    """Cycle through sort modes: name -> date -> duration -> name."""
    modes = ["name", "date", "duration"]
    current_idx = modes.index(state.sort_by) if state.sort_by in modes else 0
    next_idx = (current_idx + 1) % len(modes)
    state.sort_by = modes[next_idx]


def sort_playlist() -> None:
    """Sort the current playlist by the current sort mode."""
    if not state.playlist:
        return

    current_track = state.playlist[state.playlist_index] if state.playlist_index < len(state.playlist) else None

    if state.sort_by == "name":
        state.playlist.sort(key=lambda x: os.path.basename(x).lower(), reverse=state.sort_reverse)
    elif state.sort_by == "duration":
        state.playlist.sort(
            key=lambda x: state.track_durations.get(x, 0),
            reverse=state.sort_reverse
        )
    elif state.sort_by == "date":
        state.playlist.sort(
            key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0,
            reverse=state.sort_reverse
        )

    if current_track and current_track in state.playlist_index_map:
        state.playlist_index = state.playlist_index_map[current_track]
    _rebuild_playlist_map()


def reverse_sort() -> None:
    """Toggle sort direction."""
    state.sort_reverse = not state.sort_reverse
    sort_playlist()


def toggle_favorite() -> None:
    """Add or remove current track from favorites."""
    if not state.current_path:
        return

    if state.current_path in state.favorites:
        state.favorites.remove(state.current_path)
    else:
        state.favorites.append(state.current_path)


def is_favorite(path: str) -> bool:
    """Check if a track is in favorites."""
    return path in state.favorites


def smart_shuffle() -> None:
    """Shuffle playlist avoiding recently played tracks."""
    if not state.playlist:
        return

    import random

    current = state.playlist[state.playlist_index] if state.playlist_index < len(state.playlist) else None
    recent = set(state.shuffle_history[-state.shuffle_history_max:])

    available = [t for t in state.playlist if t not in recent]
    if not available:
        available = list(state.playlist)

    random.shuffle(available)

    if current in available:
        available.remove(current)
        available.insert(0, current)

    state.playlist = available
    if current:
        state.playlist_index = 0


def adjust_volume(delta: int) -> None:
    """Adjust volume by delta percentage.

    Args:
        delta: Volume change (positive or negative)
    """
    new_vol = max(0, min(100, state.volume + delta))
    state.volume = new_vol

    if (
        state.process
        and state.process.poll() is None
        and state.current_player == "mpg123"
    ):
        try:
            os.killpg(os.getpgid(state.process.pid), signal.SIGTERM)
            try:
                state.process.wait(timeout=1)
            except Exception:
                pass
        except Exception:
            pass

        if state.current_path:
            play(state.current_path, int(state.current_position))


def go_to_next_track() -> bool:
    """Navigate to next track in playlist.

    Handles repeat modes:
    - "off": stops at end of playlist
    - "all": loops back to start
    - "one": replays current track

    Returns:
        True if moved to next, False if at end (and repeat is off)
    """
    if not state.playlist:
        return False

    if state.repeat_mode == "one":
        return True

    if state.playlist_index + 1 < len(state.playlist):
        state.playlist_index += 1
        return True
    elif state.repeat_mode == "all":
        state.playlist_index = 0
        state.playlist_scroll_offset = 0
        return True
    return False


def go_to_previous_track() -> bool:
    """Navigate to previous track in playlist.

    Handles repeat modes:
    - "off" and "all": goes to start of playlist if at beginning
    - "one": stays on current track

    Returns:
        True if moved to previous, False if at start (and repeat is off)
    """
    if not state.playlist:
        return False

    if state.repeat_mode == "one":
        return True

    if state.playlist_index > 0:
        state.playlist_index -= 1
        return True
    elif state.repeat_mode == "all":
        state.playlist_index = len(state.playlist) - 1
        return True
    return False


def get_current_track() -> Optional[str]:
    """Get the currently selected track from playlist.

    Returns:
        Path to current track, or None
    """
    if 0 <= state.playlist_index < len(state.playlist):
        return state.playlist[state.playlist_index]
    return None


def toggle_playlist_view() -> None:
    """Toggle playlist overlay visibility."""
    # Fix: Ensure overlay exclusivity - only one overlay active at a time
    if not state.show_playlist:
        state.show_playlist = True
        state.show_help = False
        state.show_search = False
    else:
        state.show_playlist = False


def toggle_album_art_view() -> None:
    """Toggle album art overlay visibility."""
    if not state.show_album_art:
        state.show_album_art = True
    else:
        state.show_album_art = False


# Playlist file functions (save, load, list, import)
# =============================================================================


def save_playlist(name: str) -> bool:
    """Save current playlist to M3U file.

    Args:
        name: Name of the playlist (without extension)

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        if not name or "/" in name or "\\" in name or "." in name:
            return False

        if not state.playlist:
            return False

        path = state.playlist_dir / f"{name}.m3u"
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in state.playlist:
                try:
                    file_path = Path(item).resolve()
                    music_dir_resolved = state.music_dir.resolve()
                    if (
                        str(file_path).startswith(str(music_dir_resolved))
                        and file_path.exists()
                    ):
                        duration = state.track_durations.get(str(file_path), -1)
                        filename = file_path.name
                        f.write(
                            f"#EXTINF:{int(duration) if duration > 0 else -1},{filename}\n"
                        )
                        try:
                            rel_path = file_path.relative_to(music_dir_resolved)
                            f.write(f"{rel_path}\n")
                        except ValueError:
                            f.write(f"{file_path}\n")
                except (OSError, ValueError):
                    continue
        return True
    except (OSError, ValueError):
        return False


def load_playlist(name: str) -> bool:
    """Load playlist from M3U file.

    Args:
        name: Name of the playlist (without extension)

    Returns:
        True if loaded successfully, False otherwise
    """
    try:
        if not name or "/" in name or "\\" in name:
            return False

        path = state.playlist_dir / f"{name}.m3u"
        if not path.exists():
            return False

        with open(path, "r", encoding="utf-8") as f:
            state.playlist = []
            music_dir_resolved = state.music_dir.resolve()

            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                try:
                    file_path = Path(line)
                    if not file_path.is_absolute():
                        file_path = music_dir_resolved / file_path
                    file_path = file_path.resolve()

                    if file_path.exists():
                        state.playlist.append(str(file_path))
                except (OSError, ValueError):
                    continue

            state.playlist_index = 0
            state.playlist_scroll_offset = 0
            return True
    except (OSError, ValueError):
        pass
    return False


def list_playlists() -> List[str]:
    """List all saved playlists.

    Returns:
        List of playlist names
    """
    try:
        return [p.stem for p in state.playlist_dir.glob("*.m3u")]
    except (OSError, ValueError):
        return []


def import_m3u(filepath: str) -> bool:
    """Import an external M3U file into the playlist folder.

    Args:
        filepath: Path to the M3U file to import

    Returns:
        True if imported successfully, False otherwise
    """
    try:
        source_path = Path(filepath).resolve()
        if not source_path.exists():
            return False

        dest_path = state.playlist_dir / source_path.name
        with open(source_path, "r", encoding="utf-8") as src:
            content = src.read()

        with open(dest_path, "w", encoding="utf-8") as dst:
            dst.write(content)

        return True
    except (OSError, ValueError):
        return False


def add_selected_to_playlist() -> None:
    """Add the currently selected item to the playlist."""
    if state.cursor < len(state.flat_items):
        item = state.flat_items[state.cursor]
        if not item.is_dir:
            add_to_playlist(str(item.path))


def add_all_visible_to_playlist() -> None:
    """Add all visible files in the tree to the playlist."""
    for item in state.flat_items:
        if not item.is_dir:
            add_to_playlist(str(item.path))


def play_from_playlist() -> None:
    """Play the currently selected item from the playlist."""
    if 0 <= state.playlist_index < len(state.playlist):
        play(state.playlist[state.playlist_index])


def toggle_dir(item: TreeItem) -> None:
    """Toggle directory expansion state.

    Args:
        item: The directory tree item to toggle
    """
    path_str = str(item.path)
    if path_str in state.expanded_dirs:
        state.expanded_dirs.remove(path_str)
        item.children = []
        item.expanded = False
    else:
        state.expanded_dirs.add(path_str)
        item.children = scan_directory(Path(path_str), item.level + 1)
        item.expanded = True


def seek(direction: str) -> None:
    """Seek forward or backward by SEEK_SECONDS.

    Args:
        direction: 'forward' or 'backward'
    """
    if not state.process or state.process.poll() is not None or not state.current_path:
        return

    now = time.time()
    if now - state.last_seek_time < SEEK_COOLDOWN:
        return
    state.last_seek_time = now

    elapsed = (
        time.time() - state.playback_start_time if state.playback_start_time else 0
    )
    current_pos = state.current_position + elapsed

    if direction == "forward":
        new_pos = current_pos + SEEK_SECONDS
    else:
        new_pos = max(0, current_pos - SEEK_SECONDS)

    state.current_position = new_pos
    state.playback_start_time = time.time()
    play(state.current_path, int(new_pos), notify=False)


def _restart_playback() -> None:
    """Restart playback from current position (used when changing speed)."""
    if state.process and state.process.poll() is None and state.current_path:
        elapsed = (
            time.time() - state.playback_start_time if state.playback_start_time else 0
        )
        current_pos = state.current_position + elapsed
        play(state.current_path, int(current_pos), notify=False)
    elif (
        state.cursor < len(state.flat_items)
        and not state.flat_items[state.cursor].is_dir
    ):
        play(str(state.flat_items[state.cursor].path), notify=False)


def adjust_speed(delta: float) -> None:
    """Adjust playback speed by delta.

    Args:
        delta: Speed change (positive or negative)
    """
    new_speed = max(SPEED_MIN, min(SPEED_MAX, round(state.effect_speed + delta, 1)))
    state.effect_speed = new_speed
    _restart_playback()


def reset_speed() -> None:
    """Reset playback speed to 1.0."""
    state.effect_speed = 1.0
    _restart_playback()


# =============================================================================
# UI Functions
# =============================================================================
def _get_header_text() -> str:
    """Get the base header text without formatting.
    
    Returns:
        The header text string (artist - title, title, file, or danktunes)
    """
    if state.process and state.process.poll() is None:
        if state.current_artist and state.current_title:
            return f"{state.current_artist} - {state.current_title}"
        elif state.current_title:
            return state.current_title
        elif state.current_file:
            return state.current_file
        else:
            return "Unknown"
    else:
        return "danktunes"


def _draw_header() -> str:
    """Build the header text showing current playback status.

    Returns:
        The formatted header text string (without borders)
    """
    shuffle_icon = f" {Icons.SHUFFLE}" if state.shuffle_mode else ""
    header_text = _get_header_text()
    
    if state.process and state.process.poll() is None:
        speed_str = f" [{state.effect_speed}x]" if state.effect_speed != 1.0 else ""
        return f"{HEADER_GLYPH}  {C_HEADER}{header_text}{C_RESET}{C_SECONDARY}{speed_str}{C_RESET}{shuffle_icon}"
    else:
        # Do not include a trailing newline here. The caller already
        # handles line breaks and padding, which prevents an extra blank
        # line from appearing under the header when the UI renders.
        return f"{HEADER_GLYPH}  {C_HEADER}{header_text}{C_RESET}{shuffle_icon}"


def draw_playlist_overlay() -> None:
    """Draw the playlist overlay view."""
    if not state.show_playlist or not state.playlist:
        return

    h, w = _get_terminal_size()
    h = max(2, h - 4)
    w = max(10, w - 4)

    # Clear screen
    print("\033[2J\033[H", end="")

    # Draw header
    print(_draw_header())

    visible = min(VISIBLE_PLAYLIST_ITEMS, h - 4)
    max_name_len = w - 8

    # Playlist counter
    if state.playlist:
        print(f"  PL:{state.playlist_index + 1}/{len(state.playlist)}")

    for i in range(visible):
        idx = state.playlist_scroll_offset + i
        if idx < len(state.playlist):
            item_path = state.playlist[idx]
            name = os.path.basename(item_path)

            if len(name) > max_name_len:
                name = name[: max_name_len - 3] + "..."

            prefix = ""

            if idx == state.playlist_index:
                # Inverted selection like file browser
                print(f"  {prefix}{Icons.AUDIO}  {C_SELECTION}{name}{C_RESET}")
            else:
                print(f"  {prefix}{Icons.AUDIO}  {name}")
        else:
            print(f"  {' ' * max_name_len}")

    print()


def draw_help_overlay() -> None:
    """Draw help screen overlay with keyboard shortcuts."""
    if not state.show_help:
        return

    h, w = _get_terminal_size()
    h = max(2, h - 2)
    w = max(10, w - 4)

    # Clear screen
    print("\033[2J\033[H", end="")

    # Header
    print(f"\n  {HEADER_GLYPH}  {C_HEADER}Keyboard Shortcuts{C_RESET}\n")

    # Help content organized by category
    help_sections: List[Tuple[str, List[Tuple[str, str]]]] = [
        (
            "Navigation",
            [
                ("↑/↓ or j/k", "Navigate files"),
                ("Enter", "Play file / Toggle folder"),
                ("Space", "Play/Pause"),
                ("/", "Search/filter library"),
            ],
        ),
        (
            "Playback",
            [
                ("n", "Next track"),
                ("p", "Previous track"),
                ("s", "Stop"),
                ("→/←", "Seek ±5s"),
                ("1/2", "Decrease/Increase speed"),
                ("0", "Reset speed to 1.0x"),
                ("+/-", "Volume up/down"),
            ],
        ),
        (
            "Playlist",
            [
                ("a", "Add selected to playlist"),
                ("A", "Add all visible files"),
                ("x", "Remove from playlist"),
                ("c", "Clear playlist"),
                (f"Shift+S {Icons.SHUFFLE}", "Toggle shuffle"),
                ("r", "Cycle repeat: off -> all -> one"),
                ("[ / ]", "Previous/Next in playlist"),
                ("v", "View playlist"),
                ("L", "Load playlist"),
                ("W", "Save playlist"),
            ],
        ),
        (
            "Other",
            [
                ("?", "Toggle help (this screen)"),
                ("q", "Quit"),
            ],
        ),
    ]

    # Calculate layout
    max_key_len = max(len(key) for section, items in help_sections for key, _ in items)

    for section_name, items in help_sections:
        print(f"  {C_SECONDARY}{section_name}{C_RESET}")
        for key, description in items:
            key_display = f"{key:>{max_key_len}}"
            print(f"    {C_HEADER}{key_display}{C_RESET}  {description}")
        print()

    print(f"  Press {C_HEADER}?{C_RESET} to close help")


def draw() -> List[TreeItem]:
    """Draw the main file browser view."""
    # Clear screen and position cursor at exact top-left
    sys.stdout.write("\033[2J\033[1;1H")
    sys.stdout.flush()

    state.flat_items = flatten_tree(state.tree_items)

    lines, cols = _get_terminal_size()
    inner = cols - 2  # Account for left and right borders

    # Calculate how many lines are available for items
    if USE_BORDERS:
        # Reserve lines for borders: top(1) + header(1) + items(max_visible) + progress separator(1) + progress(1) + bottom(1) = 6 lines total
        # Visible item area should be lines - 6 so the bottom border sits at the terminal bottom
        max_visible = max(3, lines - 6)
    else:
        # Reserve lines: header(1) + items(max_visible) + progress(1) + 1 buffer = 4 lines
        max_visible = max(3, lines - 4)

    # Update scroll offset
    if state.cursor < state.scroll_offset:
        state.scroll_offset = state.cursor
    elif state.cursor >= state.scroll_offset + max_visible:
        state.scroll_offset = state.cursor - max_visible + 1

    # Draw top border
    if USE_BORDERS:
        print(f"{BORDER_TL}{BORDER_H * (cols - 2)}{BORDER_TR}")

    # Draw header
    if USE_BORDERS:
        if state.show_search:
            # Search mode header with mode indicator
            mode_text = f" ({state.search_mode})" if state.search_mode == "recursive" else ""
            search_header = (
                f"{HEADER_GLYPH}  {C_HEADER}Search{mode_text}: /{state.search_query}{C_RESET}"
            )
            print(f"{BORDER_V}{search_header}", end="")
            fill = inner - _display_width(search_header)
            if fill > 0:
                print(" " * fill + BORDER_V)
            else:
                print(BORDER_V)
        else:
            _draw_ranger_header(inner)
    else:
        if state.show_search:
            mode_text = f" ({state.search_mode})" if state.search_mode == "recursive" else ""
            print(f"{HEADER_GLYPH}  {C_HEADER}Search{mode_text}: /{state.search_query}{C_RESET}")
        else:
            print(_draw_header())

    # Draw items (or search results)
    if state.show_search:
        # Draw search results
        if state.search_mode == "recursive":
            # Draw recursive search results
            visible_results = state.recursive_search_results[
                state.scroll_offset : state.scroll_offset + max_visible
            ]
            for i, result in enumerate(visible_results):
                idx = state.scroll_offset + i
                
                # Build display line with depth indicator
                indent = "  " * result['depth']
                icon = Icons.FOLDER if result['is_dir'] else Icons.AUDIO
                name = os.path.basename(result['path'])
                
                max_len = inner - 4 - len(indent)
                disp = (
                    _truncate_to_width(name, max_len)
                    if _display_width(name) > max_len
                    else name
                )

                if idx == state.search_cursor:
                    line = f"{indent}{icon}  {C_SELECTION}{disp}{C_RESET}"
                else:
                    line = f"{indent}{icon}  {disp}"

                if USE_BORDERS:
                    print(f"{BORDER_V}{line}", end="")
                    fill = inner - _display_width(line)
                    if fill > 0:
                        print(" " * fill + BORDER_V)
                    else:
                        print(BORDER_V)
                else:
                    print(line)
        else:
            # Draw flat search results (legacy)
            visible_results = state.search_results[
                state.scroll_offset : state.scroll_offset + max_visible
            ]
            for i, path_str in enumerate(visible_results):
                idx = state.scroll_offset + i
                name = os.path.basename(path_str)

                max_len = inner - 4
                disp = (
                    _truncate_to_width(name, max_len)
                    if _display_width(name) > max_len
                    else name
                )

                if idx == state.search_cursor:
                    line = f"  {Icons.AUDIO}  {C_SELECTION}{disp}{C_RESET}"
                else:
                    line = f"  {Icons.AUDIO}  {disp}"

                if USE_BORDERS:
                    fill = inner - _display_width(line)
                    print(f"{BORDER_V}{line}", end="")
                    print(" " * max(0, fill) + BORDER_V)
                else:
                    print(line)

        # Fill remaining space
        remaining_space = max_visible - len(visible_results)
        for _ in range(remaining_space):
            if USE_BORDERS:
                print(f"{BORDER_V}{' ' * (cols - 2)}{BORDER_V}")
            else:
                print()
    else:
        # Draw regular file browser
        visible = state.flat_items[
            state.scroll_offset : state.scroll_offset + max_visible
        ]
        for i, item in enumerate(visible):
            idx = state.scroll_offset + i
            prefix = "  " * item.level

            if item.is_dir:
                icon = Icons.FOLDER if item.expanded else Icons.FOLDER_CLOSED
                name = item.path.name
                if idx == state.cursor:
                    line = f"{prefix}{icon}  {C_SELECTION}{name}{C_RESET}"
                else:
                    line = f"{prefix}{icon}  {name}"
            else:
                icon = Icons.AUDIO
                name = item.path.name
                dur = state.track_durations.get(str(item.path))
                dur_str = (
                    f" {C_SECONDARY}{_format_duration(dur)}{C_RESET}"
                    if dur
                    else f" {C_SECONDARY}--:--{C_RESET}"
                )

                max_len = inner - _display_width(prefix) - 4 - _display_width(dur_str)
                disp = (
                    _truncate_to_width(name, max_len)
                    if _display_width(name) > max_len
                    else name
                )

                if idx == state.cursor:
                    line = f"{prefix}{icon}  {C_SELECTION}{disp}{dur_str}{C_RESET}"
                else:
                    line = f"{prefix}{icon}  {disp}{dur_str}"

            if USE_BORDERS:
                fill = inner - _display_width(line)
                print(f"{BORDER_V}{line}", end="")
                print(" " * max(0, fill) + BORDER_V)
            else:
                print(line)

        # Fill remaining space
        remaining_space = max_visible - len(visible)
        for _ in range(remaining_space):
            if USE_BORDERS:
                print(f"{BORDER_V}{' ' * (cols - 2)}{BORDER_V}")
            else:
                print()

    # Progress separator
    if USE_BORDERS:
        print(f"{BORDER_LT}{BORDER_H * (cols - 2)}{BORDER_RT}")

    _draw_ranger_progress(inner)

    return state.flat_items


def _draw_ranger_header(inner_width: int) -> None:
    """Draw header line inside Ranger-style borders."""
    shuffle_icon = f" {Icons.SHUFFLE}" if state.shuffle_mode else ""
    header_text = _get_header_text()

    if state.process and state.process.poll() is None:
        speed_str = f" [{state.effect_speed}x]" if state.effect_speed != 1.0 else ""
        
        album_art = ""
        if state.current_path:
            art_path = get_album_art(state.current_path)
            if art_path:
                album_art = f" {Icons.MUSIC_NOTE}"
        
        fixed = f"{HEADER_GLYPH}{album_art} "
        fixed_len = (
            _display_width(fixed)
            + _display_width(speed_str)
            + _display_width(shuffle_icon)
        )
        max_len = inner_width - fixed_len

        header_plain = _strip_ansi(header_text)
        if _display_width(header_plain) > max_len:
            header_text = _truncate_to_width(header_plain, max_len)

        header_line = f"{fixed}{C_HEADER}{header_text}{C_RESET}{C_SECONDARY}{speed_str}{C_RESET}{shuffle_icon}"
        visible_len = _display_width(header_line)

        print(f"{BORDER_V}{header_line}", end="")
        fill = inner_width - visible_len
        if fill > 0:
            print(" " * fill + BORDER_V)
        else:
            print(BORDER_V)
    else:
        # Build a truncated danktunes header that respects inner width
        header_prefix = f"{HEADER_GLYPH}  {C_HEADER}"
        header_suffix = f"{C_RESET}{shuffle_icon}"

        max_text_len = (
            inner_width - _display_width(header_prefix) - _display_width(header_suffix)
        )
        if max_text_len > 0 and _display_width(header_text) > max_text_len:
            header_text = _truncate_to_width(header_text, max_text_len)

        ready_line = f"{HEADER_GLYPH}  {C_HEADER}{header_text}{C_RESET}{shuffle_icon}"
        visible_len = _display_width(ready_line)

        print(f"{BORDER_V}{ready_line}", end="")
        fill = inner_width - visible_len
        if fill > 0:
            print(" " * fill + BORDER_V)
        else:
            print(BORDER_V)


def _draw_ranger_progress(inner_width: int) -> None:
    """Draw progress bar inside Ranger-style borders with dynamic sizing."""
    if state.process and state.process.poll() is None and state.playback_start_time:
        # Calculate elapsed time based on paused state
        if hasattr(state, "paused") and state.paused:
            elapsed = state.current_position
        else:
            elapsed = time.time() - state.playback_start_time + state.current_position
        duration = (
            state.track_durations.get(state.current_path)
            if state.current_path
            else None
        )

        if duration:
            # Calculate responsive layout based on window width
            time_text = f"{_format_duration(elapsed)} / {_format_duration(duration)}"
            min_bar_width = 20  # Minimum visible progress bar
            max_time_text_len = 20  # Maximum space for time display

            # Calculate available space for progress bar
            available_space = (
                inner_width - min(len(time_text), max_time_text_len) - 3
            )  # -3 for brackets and space
            bar_width = max(min_bar_width, available_space)

            pct = min(elapsed / max(duration, 0.001), 1.0)
            filled_chars = int(pct * (bar_width - 2))  # -2 for brackets
            bar = (
                "["
                + "=" * filled_chars
                + ">"
                + " " * (bar_width - filled_chars - 2)
                + "]"
            )

            # Combine time text and bar, truncate if necessary
            combined = f"{time_text[:max_time_text_len]} {bar}"
            print(f"{BORDER_V}{combined}", end="")
            fill = inner_width - _display_width(combined)
            if fill > 0:
                print(" " * fill + BORDER_V)
            else:
                print(BORDER_V)
        else:
            # No duration available - show responsive elapsed time bar
            elapsed_text = f"{_format_duration(elapsed)}"
            available_space = (
                inner_width - len(elapsed_text) - 4
            )  # -4 for brackets and space
            bar_width = max(10, available_space)

            if bar_width > 10:
                bar = "[>" + " " * (bar_width - 2) + "]"
                combined = f"{elapsed_text} {bar}"
            else:
                combined = elapsed_text[: inner_width - 1]

            print(f"{BORDER_V}{combined}", end="")
            fill = inner_width - _display_width(combined)
            if fill > 0:
                print(" " * fill + BORDER_V)
            else:
                print(BORDER_V)
    else:
        # Empty progress bar when nothing is playing
        empty_content = " "
        print(f"{BORDER_V}{empty_content}", end="")
        fill = inner_width - _display_width(empty_content)
        if fill > 0:
            print(" " * fill + BORDER_V)
        else:
            print(BORDER_V)


def draw_album_art_overlay(force_redraw: bool = False) -> None:
    """Draw album art overlay with track info and progress bar.
    
    Args:
        force_redraw: If True, force redisplay of the image
    """
    global last_album_art_path
    
    if not ALBUM_ART_ENABLED:
        print("\033[2J\033[H", end="", flush=True)
        print(f"\n  {C_SECONDARY}Album art is disabled in config{C_RESET}\n")
        return
    
    if not state.current_path:
        print("\033[2J\033[H", end="", flush=True)
        print(f"\n  {C_SECONDARY}No track playing{C_RESET}\n")
        return
    
    art_path = get_album_art(state.current_path)
    
    protocol = TerminalImageProtocol.detect()
    lines, cols = _get_terminal_size()
    img_height = max(10, lines - 10)
    img_width = max(20, cols - 4)
    
    # Clear screen
    print("\033[2J\033[H", end="", flush=True)
    
    # Show album art path
    print(f"  {HEADER_GLYPH}  Album Art\n")
    
    if art_path and Path(art_path).exists():
        print(f"  {C_SECONDARY}Album art: {Path(art_path).name}{C_RESET}\n")
    else:
        print(f"  {C_SECONDARY}No album art found{C_RESET}\n")
    
    # Show track info
    print(f"  {Icons.MUSIC_NOTE}  ", end="")
    
    if state.current_title:
        print(f"{state.current_title}")
        if state.current_artist:
            print(f" - {state.current_artist}")
    elif state.current_path:
        print(f"{Path(state.current_path).name}")
    else:
        print("No track playing")
    print()
    
    # Draw progress bar
    _draw_album_art_progress(cols - 4)
    
    # Try to display image using kitty icat in background
    if art_path and Path(art_path).exists() and protocol == TerminalImageProtocol.KITTY:
        try:
            subprocess.Popen(
                ["kitty", "+kitten", "icat", "--place", f"{img_width}x{img_height}@1x1", art_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass


def _draw_album_art_progress(inner_width: int) -> None:
    """Draw progress bar for album art overlay."""
    if state.process and state.process.poll() is None and state.playback_start_time:
        if hasattr(state, "paused") and state.paused:
            elapsed = state.current_position
        else:
            elapsed = time.time() - state.playback_start_time + state.current_position
        
        duration = state.track_durations.get(state.current_path, 0) if state.current_path else 0
        
        if duration > 0:
            time_text = f"{_format_duration(elapsed)} / {_format_duration(duration)}"
            bar_width = max(20, inner_width - len(time_text) - 3)
            
            pct = min(elapsed / max(duration, 0.001), 1.0)
            filled_chars = int(pct * (bar_width - 2))
            bar = (
                "["
                + "=" * filled_chars
                + ">"
                + " " * (bar_width - filled_chars - 2)
                + "]"
            )
            
            print(f"  {time_text} {bar}")
        else:
            print()
    else:
        print(f"  {C_SECONDARY}No track playing{C_RESET}")
    
    print()


# =============================================================================
# Input Handling Functions
# =============================================================================
def _handle_navigation(key: str) -> bool:
    """Handle navigation key presses (arrows, j/k).

    Args:
        key: The key pressed

    Returns:
        True if handled, False otherwise
    """
    handled = False
    
    # Determine direction from key
    is_down = key in ("j", "\x1b[B")  # j or down arrow
    is_up = key in ("k", "\x1b[A")    # k or up arrow
    
    if is_down or is_up:
        direction = 1 if is_down else -1
        
        if state.show_playlist and state.playlist:
            _navigate_playlist(direction)
            handled = True
        elif state.flat_items:
            state.cursor = _navigate_bounded(state.cursor, direction, len(state.flat_items))
            handled = True
            
    return handled


def _navigate_playlist(direction: int) -> None:
    """Navigate in playlist with scroll handling.
    
    Args:
        direction: 1 for down, -1 for up
    """
    new_index = state.playlist_index + direction
    if 0 <= new_index < len(state.playlist):
        state.playlist_index = new_index
        _adjust_playlist_scroll()


def _adjust_playlist_scroll() -> None:
    """Adjust playlist scroll offset to keep current item visible."""
    visible = min(VISIBLE_PLAYLIST_ITEMS, len(state.playlist))
    if state.playlist_index < state.playlist_scroll_offset:
        state.playlist_scroll_offset = state.playlist_index
    elif state.playlist_index >= state.playlist_scroll_offset + visible:
        state.playlist_scroll_offset = state.playlist_index - visible + 1


def _navigate_bounded(current: int, direction: int, max_items: int) -> int:
    """Navigate with bounds checking.
    
    Args:
        current: Current position
        direction: 1 for down, -1 for up  
        max_items: Maximum number of items
        
    Returns:
        New position bounded to valid range
    """
    return max(0, min(max_items - 1, current + direction))


def _handle_playback(key: str) -> bool:
    """Handle playback key presses (space, s).

    Args:
        key: The key pressed

    Returns:
        True if handled, False otherwise
    """
    if key == " ":
        toggle_pause()
        return True
    elif key == "s":
        stop_audio()
        return True
    return False


def _handle_save_playlist() -> bool:
    """Handle saving a playlist with user input.

    Returns:
        True if playlist was saved, False otherwise
    """
    if not state.playlist:
        return False

    # Save current terminal state
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    try:
        # Show save prompt
        print("\033[2J\033[H", end="")
        print(f"\n  {HEADER_GLYPH}  Save Playlist\n")
        print(f"  Playlist contains {len(state.playlist)} tracks\n")
        print("  Enter playlist name (or press Enter to cancel): ")

        # Restore normal terminal mode for input
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

        try:
            name = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            name = ""

        # Restore cbreak mode
        tty.setcbreak(fd)

        if name:
            if save_playlist(name):
                print(f"\n  Playlist '{name}' saved!")
                time.sleep(1)
            else:
                print("\n  Failed to save playlist.")
                time.sleep(1)

        return True
    except Exception:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        return False


def _handle_playlist_commands(key: str) -> bool:
    """Handle playlist-related key presses.

    Args:
        key: The key pressed

    Returns:
        True if handled, False otherwise
    """
    if key == "a":
        add_selected_to_playlist()
        return True
    elif key == "A":
        add_all_visible_to_playlist()
        return True
    elif key == "x":
        if state.show_playlist and 0 <= state.playlist_index < len(state.playlist):
            remove_from_playlist(state.playlist_index)
        return True
    elif key == "c":
        clear_playlist()
        return True
    elif key == "S":
        toggle_shuffle_mode()
        return True
    elif key == "r":
        toggle_repeat_mode()
        return True
    elif key == "]":
        if go_to_next_track():
            track = get_current_track()
            if track:
                play(track)
        return True
    elif key == "[":
        go_to_previous_track()
        track = get_current_track()
        if track:
            play(track)
        return True
    elif key == "v":
        toggle_playlist_view()
        state.show_help = False
        return True
    elif key == "L":
        names = list_playlists()
        if names:
            load_playlist(names[0])
        return True
    elif key == "W":
        # Save playlist with a name - need to handle input
        return _handle_save_playlist()
    return False


def _handle_speed_control(key: str) -> bool:
    """Handle speed control key presses (0, 1, 2).

    Args:
        key: The key pressed

    Returns:
        True if handled, False otherwise
    """
    if key == "1":
        adjust_speed(-SPEED_STEP)
        return True
    elif key == "2":
        adjust_speed(SPEED_STEP)
        return True
    elif key == "0":
        reset_speed()
        return True
    return False


def _handle_volume_control(key: str) -> bool:
    """Handle volume control key presses (+, -).

    Args:
        key: The key pressed

    Returns:
        True if handled, False otherwise
    """
    if key == "+" or key == "=":
        adjust_volume(5)  # Use 5% increments instead of 10%
        return True
    elif key == "-" or key == "_":
        adjust_volume(-5)  # Use 5% increments instead of 10%
        return True
    return False


def _perform_recursive_search(query: str) -> List[Dict[str, Any]]:
    """Perform recursive search through the entire music directory.
    
    Args:
        query: Search query string
        
    Returns:
        List of dictionaries with 'path', 'tree_item', and 'match_info'
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    def search_tree_recursive(items: List[TreeItem], depth: int = 0) -> None:
        """Recursively search through tree items."""
        for item in items:
            if item.is_dir:
                # Search in directory name
                dir_name = item.path.name.lower()
                if query_lower in dir_name:
                    results.append({
                        'path': str(item.path),
                        'tree_item': item,
                        'match_info': f"Directory: {item.path.name}",
                        'depth': depth,
                        'is_dir': True
                    })
                
                # Recursively search children
                if item.children:
                    search_tree_recursive(item.children, depth + 1)
            else:
                # Search in audio file
                path_str = str(item.path)
                filename = item.path.name.lower()
                
                # Check for matches in filename and full path
                match_type = None
                if query_lower in filename:
                    match_type = "filename"
                elif query_lower in path_str.lower():
                    match_type = "path"
                
                if match_type:
                    results.append({
                        'path': path_str,
                        'tree_item': item,
                        'match_info': f"{match_type.title()}: {item.path.name}",
                        'depth': depth,
                        'is_dir': False
                    })

    # Start recursive search from tree_items (root level)
    search_tree_recursive(state.tree_items)
    
    # Sort results: directories first, then by depth, then by filename
    results.sort(key=lambda x: (not x['is_dir'], x['depth'], x['path'].lower()))
    
    return results


def _perform_search(query: str) -> List[str]:
    """Perform search through the library and return matching paths.
    
    This is the legacy search function for backward compatibility.
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    # Search through flat_items
    for item in state.flat_items:
        if not item.is_dir:
            path_str = str(item.path)
            # Search in filename, path, and metadata
            name = item.path.name.lower()
            if query_lower in name or query_lower in path_str:
                results.append(path_str)

    return results


def _handle_search(key: str) -> bool:
    """Handle search mode input.

    Args:
        key: The key pressed

    Returns:
        True if handled, False otherwise
    """
    if not state.show_search:
        return False

    if key == "\033":  # Escape
        state.show_search = False
        state.search_query = ""
        state.search_results = []
        state.recursive_search_results = []
        state.search_cursor = 0
        return True
        
    elif key == "\t":  # Tab - toggle search mode
        if state.search_mode == "flat":
            state.search_mode = "recursive"
            state.recursive_search_results = _perform_recursive_search(state.search_query)
        else:
            state.search_mode = "flat"
            state.search_results = _perform_search(state.search_query)
            state.recursive_search_results = []
        state.search_cursor = 0
        return True
        
    elif key == "\r" or key == "\n":  # Enter - play or jump to selected
        if state.search_mode == "recursive":
            # Jump to file in browser
            if state.recursive_search_results and state.search_cursor < len(state.recursive_search_results):
                selected = state.recursive_search_results[state.search_cursor]
                _jump_to_file_in_browser(selected['path'], selected['tree_item'])
                state.show_search = False
        else:
            # Play selected (flat search)
            if state.search_results and state.search_cursor < len(state.search_results):
                track_path = state.search_results[state.search_cursor]
                play(track_path)
                state.show_search = False
        return True
        
    elif key == "\033[B" or key == "j":  # Down
        if state.search_mode == "recursive":
            if state.recursive_search_results:
                state.search_cursor = min(
                    len(state.recursive_search_results) - 1, state.search_cursor + 1
                )
        else:
            if state.search_results:
                state.search_cursor = min(
                    len(state.search_results) - 1, state.search_cursor + 1
                )
        return True
        
    elif key == "\033[A" or key == "k":  # Up
        if state.search_mode == "recursive":
            if state.recursive_search_results:
                state.search_cursor = max(0, state.search_cursor - 1)
        else:
            if state.search_results:
                state.search_cursor = max(0, state.search_cursor - 1)
        return True
        
    elif key == "\177" or key == "\x7f":  # Backspace
        if state.search_query:
            state.search_query = state.search_query[:-1]
            if state.search_mode == "recursive":
                state.recursive_search_results = _perform_recursive_search(state.search_query)
                state.search_cursor = min(
                    max(0, len(state.recursive_search_results) - 1), state.search_cursor
                )
            else:
                state.search_results = _perform_search(state.search_query)
                state.search_cursor = min(
                    max(0, len(state.search_results) - 1), state.search_cursor
                )
        return True
        
    elif len(key) == 1 and key.isprintable():
        state.search_query += key
        if state.search_mode == "recursive":
            state.recursive_search_results = _perform_recursive_search(state.search_query)
            state.search_cursor = min(
                max(0, len(state.recursive_search_results) - 1), state.search_cursor
            )
        else:
            state.search_results = _perform_search(state.search_query)
            state.search_cursor = min(
                max(0, len(state.search_results) - 1), state.search_cursor
            )
        return True
    return False


def _jump_to_file_in_browser(file_path: str, target_tree_item: TreeItem) -> None:
    """Jump to specific file in the file browser.
    
    Args:
        file_path: Path to the target file
        target_tree_item: TreeItem to locate in browser
    """
    # First, ensure the parent directories are expanded
    current = target_tree_item.parent
    while current:
        current.expanded = True
        current = current.parent
    
    # Rebuild flat_items to include the target
    state.flat_items = _build_flat_items(state.tree_items)
    
    # Find the target in flat_items and set cursor
    for i, item in enumerate(state.flat_items):
        if str(item.path) == file_path:
            state.cursor = i
            # Ensure the target is visible by adjusting scroll offset
            visible_items = _get_visible_items_count()
            if i >= state.scroll_offset + visible_items:
                state.scroll_offset = i - visible_items + 2
            elif i < state.scroll_offset:
                state.scroll_offset = max(0, i - 2)
            break


def _get_visible_items_count() -> int:
    """Get number of items visible in current terminal height."""
    try:
        # Get terminal height
        import shutil
        terminal_height = shutil.get_terminal_size().lines
        # Reserve space for header, status bar, etc.
        return max(5, terminal_height - 10)
    except Exception:
        return 15  # Default fallback


def _build_flat_items(tree_items: List[TreeItem]) -> List[TreeItem]:
    """Build flat_items list from tree_items, respecting expansion state."""
    flat_list = []
    
    def add_items_recursive(items: List[TreeItem]) -> None:
        for item in items:
            flat_list.append(item)
            if item.is_dir and item.expanded:
                add_items_recursive(item.children)
    
    add_items_recursive(tree_items)
    return flat_list


resize_received = False


def _handle_resize(signum: Optional[int] = None, frame: Any = None) -> None:
    """Handle terminal resize events."""
    global resize_received
    resize_received = True


def _exit_now(signum: Optional[int] = None, frame: Any = None) -> None:
    """Clean up and exit the player immediately."""
    stop_audio()
    save_state()
    try:
        if state.process and state.process.poll() is None:
            os.killpg(os.getpgid(state.process.pid), signal.SIGTERM)
            try:
                state.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(state.process.pid), signal.SIGKILL)
                state.process.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
        pass

    # Restore cursor visibility before exiting
    print("\033[?25h", end="")
    print("\033[2J\033[H", end="")
    print("\n  Bye!")
    sys.exit(0)


# Setup signal handlers
try:
    signal.signal(signal.SIGINT, _exit_now)
    signal.signal(signal.SIGTERM, _exit_now)
    signal.signal(signal.SIGHUP, _exit_now)
except Exception:
    pass


# =============================================================================
# Main Function
# =============================================================================
def main() -> None:
    """Main entry point for the music player.

    Initializes the UI, scans the music library, and enters the main
    input loop.
    """
    global state

    if not sys.stdin.isatty():
        print("Error: Must run in interactive terminal")
        print("Usage: python3 music_player.py")
        return

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    # Hide cursor for clean UI display
    print("\033[?25l", end="")

    # Register signal handler for terminal resize
    signal.signal(signal.SIGWINCH, _handle_resize)

    # Load saved state (volume, expanded dirs, etc.)
    load_state()

    # Redraw throttling to reduce flicker
    last_draw = time.time()
    last_cursor = -1
    last_show_playlist = state.show_playlist
    last_show_help = state.show_help
    last_show_album_art = state.show_album_art
    last_playlist_len = len(state.playlist)
    last_playlist_index = state.playlist_index
    last_playlist_scroll = state.playlist_scroll_offset

    if _config_created:
        print(f"\n  Config file created at: {CONFIG_DIR / 'danktunes.toml'}")
    print("\n  Scanning music library for durations...")
    state.tree_items = scan_directory(state.music_dir)
    scan_all_durations(state.tree_items)

    # Initialize search state tracking
    last_show_search = False
    last_search_query = ""

    try:
        while True:
            # Fix: Validate state periodically to catch issues early
            if time.time() - last_draw > 1.0:  # Validate every second
                try:
                    # State validation is now in main file
                    validate_state()
                    logger.debug("State validation completed")
                except Exception as e:
                    logger.error(f"Error in state validation: {e}")
            
            # Check if process ended and auto-advance playlist
            if state.process and state.process.poll() is not None and state.playlist:
                state.process = None
                if go_to_next_track():
                    track = get_current_track()
                    if track:
                        play(track)

            # Redraw if needed
            now = time.time()
            global resize_received, last_album_art_track
            
            # Check if currently playing (for progress bar updates)
            is_playing = state.process and state.process.poll() is None and not getattr(state, 'paused', False)
            
            # For album art overlay, only redraw when track actually changes
            album_art_track_changed = state.current_path != last_album_art_track
            
            state_changed = (
                state.cursor != last_cursor
                or state.show_playlist != last_show_playlist
                or state.show_help != last_show_help
                or state.show_search != last_show_search
                or state.search_query != last_search_query
                or len(state.playlist) != last_playlist_len
                or state.playlist_index != last_playlist_index
                or state.playlist_scroll_offset != last_playlist_scroll
                or state.show_album_art != last_show_album_art
                or (state.show_album_art and album_art_track_changed)
                or resize_received
            )
            resize_received = False
            # Only redraw on interval if playing (for progress bar) and not in static overlays
            # For Alacritty/other terminals, this reduces flickering by only redrawing when needed
            needs_redraw = state_changed or (
                is_playing
                and (now - last_draw >= REDRAW_INTERVAL)
                and not (state.show_help or state.show_playlist or state.show_album_art)
            )
            if needs_redraw:
                print("\033[2J\033[H", end="")
                if state.show_album_art:
                    draw_album_art_overlay()
                    last_album_art_track = state.current_path
                elif state.show_help:
                    draw_help_overlay()
                elif state.show_playlist:
                    draw_playlist_overlay()
                else:
                    draw()
                last_draw = now
                last_cursor = state.cursor
                last_show_playlist = state.show_playlist
                last_show_help = state.show_help
                last_show_search = state.show_search
                last_show_album_art = state.show_album_art
                last_search_query = state.search_query
                last_playlist_len = len(state.playlist)
                last_playlist_index = state.playlist_index
                last_playlist_scroll = state.playlist_scroll_offset

            # Input handling
            while True:
                try:
                    if not select.select([sys.stdin], [], [], 0.05)[0]:
                        break
                except KeyboardInterrupt:
                    break
                try:
                    ch = sys.stdin.read(1)
                except (EOFError, KeyboardInterrupt, OSError):
                    break

                # Handle escape sequences (arrows)
                if ch == "\033":
                    try:
                        seq = sys.stdin.read(2)
                    except (EOFError, KeyboardInterrupt, OSError):
                        break

                    if state.show_playlist:
                        if seq == "[A":
                            if state.playlist:
                                state.playlist_index = max(0, state.playlist_index - 1)
                                if state.playlist_index < state.playlist_scroll_offset:
                                    state.playlist_scroll_offset = state.playlist_index
                        elif seq == "[B":
                            if state.playlist:
                                state.playlist_index = min(
                                    len(state.playlist) - 1, state.playlist_index + 1
                                )
                                visible = min(VISIBLE_PLAYLIST_ITEMS, len(state.playlist))
                                if state.playlist_index >= state.playlist_scroll_offset + visible:
                                    state.playlist_scroll_offset = state.playlist_index - visible + 1
                    else:
                        if seq == "[A":
                            if state.flat_items:
                                state.cursor = max(0, state.cursor - 1)
                        elif seq == "[B":
                            if state.flat_items:
                                state.cursor = min(
                                    len(state.flat_items) - 1, state.cursor + 1
                                )
                        elif seq == "[C":
                            seek("forward")
                        elif seq == "[D":
                            seek("backward")

                # Handle regular keys
                elif ch == "\r" or ch == "\n":
                    if state.show_search:
                        if state.search_results and state.search_cursor < len(
                            state.search_results
                        ):
                            track_path = state.search_results[state.search_cursor]
                            play(track_path)
                            state.show_search = False
                    elif state.show_playlist:
                        play_from_playlist()
                    else:
                        if state.cursor < len(state.flat_items):
                            item = state.flat_items[state.cursor]
                            if item.is_dir:
                                toggle_dir(item)
                            else:
                                play(str(item.path))

                elif ch == "?":
                    # Fix: Ensure overlay exclusivity - only one overlay active at a time
                    if not state.show_help:
                        state.show_help = True
                        state.show_playlist = False
                        state.show_search = False
                    else:
                        state.show_help = False

                elif ch == "/":
                    # Fix: Ensure overlay exclusivity - only one overlay active at a time
                    state.show_search = True
                    state.show_help = False
                    state.show_playlist = False
                    state.search_query = ""
                    state.search_results = []
                    state.recursive_search_results = []
                    state.search_cursor = 0
                    state.search_mode = "recursive"  # Default to recursive search

                elif ch == "q":
                    _exit_now()

                elif state.show_help:
                    state.show_help = False

                elif state.show_search:
                    if not _handle_search(ch):
                        # Pass through to other handlers if not handled
                        if _handle_navigation(ch):
                            pass
                        elif _handle_playback(ch):
                            pass
                        elif ch == "v":
                            state.show_search = False
                            toggle_playlist_view()

                elif state.show_playlist:
                    # Handle playlist-specific keys
                    if ch == " ":
                        if state.process and state.process.poll() is None:
                            toggle_pause()
                        else:
                            play_from_playlist()
                    elif ch == "x":
                        if 0 <= state.playlist_index < len(state.playlist):
                            remove_from_playlist(state.playlist_index)
                    elif ch == "v":
                        toggle_playlist_view()
                    elif _handle_navigation(ch):
                        # Handle navigation keys in playlist mode (j, k, arrows)
                        pass

                else:
                    # Handle all other keys through specialized handlers
                    if _handle_navigation(ch):
                        pass
                    elif _handle_playback(ch):
                        pass
                    elif _handle_playlist_commands(ch):
                        pass
                    elif _handle_speed_control(ch):
                        pass
                    elif _handle_volume_control(ch):
                        pass
                    elif ch == "o":
                        state.show_album_art = not state.show_album_art
                        state.show_help = False
                        state.show_playlist = False
                        state.show_search = False

    finally:
        stop_audio()
        # Restore cursor visibility and terminal settings
        print("\033[?25h", end="")
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print("\033[2J\033[H", end="")
        print("\n  Bye!")


# =============================================================================
# Non-Interactive Mode
# =============================================================================
if __name__ == "__main__":
    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"danktunes {__version__}")
        print(f"{__description__}")
        print(f"Author: {__author__}")
    elif "--help" in sys.argv or "-h" in sys.argv:
        print(f"danktunes {__version__}")
        print("")
        print("Usage:")
        print("  python3 danktunes.py           # Run in interactive mode")
        print("  python3 danktunes.py <file>   # Play file directly")
        print("  python3 danktunes.py --version # Show version info")
        print("  python3 danktunes.py --help   # Show this help")
    elif "--no-tty-check" in sys.argv:
        if len(sys.argv) > 2:
            play(sys.argv[2])
        else:
            print("Usage: python3 music_player.py --no-tty-check [audio_file]")
    elif not sys.stdout.isatty() and len(sys.argv) > 1:
        play(sys.argv[1])
    else:
        main()
