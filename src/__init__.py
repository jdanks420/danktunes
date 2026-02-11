"""
Danktunes - Terminal-based music player.
"""

__version__ = "2.0.0"
__author__ = "DankTunes Team"
__description__ = "A terminal-based music player with playlist support, search functionality, and audio playback."

# Import all modules
from . import audio
from . import state
from . import config
from . import logging_config

# Re-export key classes and functions
__all__ = [
    # Audio
    'AudioPlayer',
    'MPG123Player', 
    'APlayPlayer',
    'get_audio_player',
    'detect_available_player',
    
    # State
    'StateManager',
    'NavigationState',
    'PlaybackState',
    'UIState', 
    'PlaylistState',
    'CacheState',
    'state_manager',
    
    # Config
    'load_config',
    'save_config',
    'AppConfig',
    'ConfigManager',
]