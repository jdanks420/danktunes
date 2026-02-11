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

# =============================================================================
# Imports
# =============================================================================
import fcntl
import os
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

# Audio file extensions
AUDIO_EXTENSIONS: Set[str] = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}

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
        import shutil

        notify_send = shutil.which("notify-send")
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


def _char_display_width(ch: str) -> int:
    """Return display width of a single Unicode character (0, 1 or 2)."""
    if not ch:
        return 0
    # Treat non-spacing marks and format chars as zero width
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    # East Asian Wide/Fullwidth characters (and most emoji) are width 2
    ea = unicodedata.east_asian_width(ch)
    if ea in ("F", "W"):
        return 2
    return 1


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
        # Not enough room for ellipsis: hard-truncate
        target = max_width
        out = []
        cur = 0
        for ch in text:
            w = _char_display_width(ch)
            if cur + w > target:
                break
            out.append(ch)
            cur += w
        return "".join(out)

    target = max_width - e_width
    out = []
    cur = 0
    for ch in text:
        w = _char_display_width(ch)
        if cur + w > target:
            break
        out.append(ch)
        cur += w
    return "".join(out) + ellipsis


def get_duration(path: str) -> Optional[float]:
    """Get audio file duration using ffprobe.

    Args:
        path: Path to the audio file

    Returns:
        Duration in seconds, or None if unavailable
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return None
    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        OSError,
        ValueError,
    ):
        return None


def get_metadata(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Get artist and title metadata from audio file using ffprobe.

    Args:
        path: Path to the audio file

    Returns:
        Tuple of (artist, title), or (None, None) if unavailable
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
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
            timeout=1,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            artist = lines[0].strip() if len(lines) > 0 and lines[0].strip() else None
            title = lines[1].strip() if len(lines) > 1 and lines[1].strip() else None
            return (artist, title)
        return (None, None)
    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        OSError,
        ValueError,
    ):
        return (None, None)


def scan_all_durations(items: List[TreeItem]) -> int:
    """Scan all audio files in the tree and cache their durations.

    Args:
        items: List of tree items to scan

    Returns:
        Number of durations cached
    """
    count = 0
    for item in items:
        if item.is_dir and item.children:
            count += scan_all_durations(item.children)
        else:
            path_str = str(item.path)
            if path_str not in state.track_durations:
                duration = get_duration(path_str)
                if duration:
                    if len(state.track_durations) > MAX_TRACK_DURATIONS:
                        # Use OrderedDict's LRU behavior - remove oldest items
                        keys_to_remove = list(state.track_durations.keys())[
                            :len(state.track_durations) - MAX_TRACK_DURATIONS
                        ]
                        for key in keys_to_remove:
                            del state.track_durations[key]
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
    for item in items:
        result.append(item)
        if item.is_dir and item.expanded and item.children:
            flatten_tree(item.children, result)
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


def scan_directory(path: Path, level: int = 0) -> List[TreeItem]:
    """Scan a directory and return tree items.

    Args:
        path: Directory path to scan
        level: Current nesting level

    Returns:
        List of tree items
    """
    items = []
    try:
        entries = sorted(os.listdir(path))

        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        files = [
            e
            for e in entries
            if os.path.isfile(os.path.join(path, e))
            and Path(e).suffix.lower() in AUDIO_EXTENSIONS
        ]

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
            aplay = shutil.which("aplay")
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
            mpg123 = shutil.which("mpg123")
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

        if path_str in state.playlist:
            state.playlist_index = state.playlist.index(path_str)

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
        # Resume playback if paused
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


def remove_from_playlist(index: int) -> None:
    """Remove a track from the playlist.

    Args:
        index: Index of the track to remove
    """
    if 0 <= index < len(state.playlist):
        state.playlist.pop(index)
        if state.playlist_index >= len(state.playlist):
            state.playlist_index = 0


def clear_playlist() -> None:
    """Clear the entire playlist."""
    state.playlist = []
    state.playlist_index = 0


def toggle_shuffle_mode() -> None:
    """Toggle shuffle mode on/off."""
    state.shuffle_mode = not state.shuffle_mode
    import random

    if state.shuffle_mode and state.playlist:
        current = (
            state.playlist[state.playlist_index]
            if state.playlist_index < len(state.playlist)
            else None
        )
        random.shuffle(state.playlist)
        if current and current in state.playlist:
            state.playlist_index = state.playlist.index(current)
        else:
            state.playlist_index = 0


def toggle_repeat_mode() -> None:
    """Cycle through repeat modes: off -> all -> one -> off."""
    modes = ["off", "all", "one"]
    current_idx = modes.index(state.repeat_mode) if state.repeat_mode in modes else 0
    next_idx = (current_idx + 1) % len(modes)
    state.repeat_mode = modes[next_idx]


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


# Playlist file functions (save, load, list, import)
# =============================================================================


def save_playlist(name: str) -> bool:
    """Save the current playlist to an M3U file.

    Args:
        name: Name of the playlist (without extension)

    Returns:
        True if saved successfully, False otherwise
    """
    return save_playlist_m3u(name)


def save_playlist_m3u(name: str) -> bool:
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
    """Load a playlist from M3U file.

    Args:
        name: Name of the playlist (without extension)

    Returns:
        True if loaded successfully, False otherwise
    """
    return load_playlist_m3u(name)


def load_playlist_m3u(name: str) -> bool:
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
        if i < len(state.playlist):
            idx = i
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
        fixed = f"{HEADER_GLYPH}  "
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
    
    if key == "j":
        if state.show_playlist and state.playlist:
            state.playlist_index = min(len(state.playlist) - 1, state.playlist_index + 1)
            handled = True
        elif state.flat_items:
            state.cursor = min(len(state.flat_items) - 1, state.cursor + 1)
            handled = True
            
    elif key == "k":
        if state.show_playlist and state.playlist:
            state.playlist_index = max(0, state.playlist_index - 1)
            handled = True
        elif state.flat_items:
            state.cursor = max(0, state.cursor - 1)
            handled = True
            
    elif key == "\x1b[A":  # Up arrow
        if state.show_playlist and state.playlist:
            state.playlist_index = max(0, state.playlist_index - 1)
            handled = True
        elif state.flat_items:
            state.cursor = max(0, state.cursor - 1)
            handled = True
            
    elif key == "\x1b[B":  # Down arrow
        if state.show_playlist and state.playlist:
            state.playlist_index = min(len(state.playlist) - 1, state.playlist_index + 1)
            handled = True
        elif state.flat_items:
            state.cursor = min(len(state.flat_items) - 1, state.cursor + 1)
            handled = True
            
    return handled


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

    # Redraw throttling to reduce flicker
    last_draw = time.time()
    last_cursor = -1
    last_show_playlist = state.show_playlist
    last_show_help = state.show_help
    last_playlist_len = len(state.playlist)

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
            global resize_received
            state_changed = (
                state.cursor != last_cursor
                or state.show_playlist != last_show_playlist
                or state.show_help != last_show_help
                or state.show_search != last_show_search
                or state.search_query != last_search_query
                or len(state.playlist) != last_playlist_len
                or resize_received
            )
            resize_received = False
            # Only redraw on interval if not showing static overlays (help/playlist)
            needs_redraw = state_changed or (
                (now - last_draw >= REDRAW_INTERVAL) and not (state.show_help or state.show_playlist)
            )
            if needs_redraw:
                print("\033[2J\033[H", end="")
                if state.show_help:
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
                last_search_query = state.search_query
                last_playlist_len = len(state.playlist)

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
                        elif seq == "[B":
                            if state.playlist:
                                state.playlist_index = min(
                                    len(state.playlist) - 1, state.playlist_index + 1
                                )
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
    if "--no-tty-check" in sys.argv:
        if len(sys.argv) > 2:
            play(sys.argv[2])
        else:
            print("Usage: python3 music_player.py --no-tty-check [audio_file]")
    elif not sys.stdout.isatty() and len(sys.argv) > 1:
        play(sys.argv[1])
    else:
        main()
