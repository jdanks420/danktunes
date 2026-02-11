"""
State management module for danktunes.
"""
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

try:
    from logging_config import get_logger, StateError
    logger = get_logger('state')
except ImportError:
    import logging
    logger = logging.getLogger('state')


@dataclass
class NavigationState:
    """Navigation-related state."""
    cursor: int = 0
    scroll_offset: int = 0
    expanded_dirs: set = field(default_factory=set)
    
    def __post_init__(self):
        pass


@dataclass 
class PlaybackState:
    """Playback-related state."""
    current_path: Optional[str] = None
    current_position: float = 0.0
    current_artist: Optional[str] = None
    current_title: Optional[str] = None
    current_player: Optional[str] = None
    paused: bool = False
    volume: int = 100
    effect_speed: float = 1.0
    last_seek_time: float = 0.0


@dataclass
class UIState:
    """UI and overlay state."""
    show_help: bool = False
    show_playlist: bool = False
    show_search: bool = False
    search_query: str = ""
    search_cursor: int = 0
    search_mode: str = "recursive"  # "flat" or "recursive"


@dataclass
class PlaylistState:
    """Playlist-related state."""
    playlist: List[str] = field(default_factory=list)
    playlist_index: int = 0
    shuffle_mode: bool = False
    repeat_mode: str = "off"
    
    def __post_init__(self):
        pass


@dataclass
class CacheState:
    """Cache-related state."""
    track_durations: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        pass


class StateManager:
    """Centralized state management for danktunes."""
    
    def __init__(self):
        self.navigation = NavigationState()
        self.playback = PlaybackState()
        self.ui = UIState()
        self.playlist = PlaylistState()
        self.cache = CacheState()
    
    def validate_state(self) -> List[str]:
        """Validate current state and return list of issues."""
        issues = []
        
        # Validate navigation state
        if self.navigation.cursor < 0:
            issues.append("Navigation cursor is negative")
        
        # Validate playback state
        if self.playback.volume < 0 or self.playback.volume > 100:
            issues.append("Volume out of bounds")
        
        if self.playback.effect_speed < 0.5 or self.playback.effect_speed > 2.0:
            issues.append("Effect speed out of bounds")
        
        # Validate UI state - ensure only one overlay active
        active_overlays = [
            name for name, active in [
                ("help", self.ui.show_help),
                ("playlist", self.ui.show_playlist),
                ("search", self.ui.show_search)
            ] if active
        ]
        
        if len(active_overlays) > 1:
            issues.append(f"Multiple overlays active: {active_overlays}")
        
        if issues:
            logger.warning(f"State validation issues: {issues}")
        
        return issues
    
    def fix_overlay_conflicts(self) -> None:
        """Fix overlay state conflicts."""
        overlays = [
            ("help", self.ui.show_help),
            ("playlist", self.ui.show_playlist),
            ("search", self.ui.show_search)
        ]
        
        active_count = sum(1 for _, active in overlays if active)
        
        if active_count > 1:
            # Deactivate all except the first one (help > search > playlist priority)
            for name, active in overlays:
                if active:
                    if name != "help" and self.ui.show_help:
                        self.ui.show_playlist = False
                        self.ui.show_search = False
                    elif name != "search" and self.ui.show_search:
                        self.ui.show_help = False
                        self.ui.show_playlist = False
                    elif name != "playlist" and self.ui.show_playlist:
                        self.ui.show_help = False
                        self.ui.show_search = False
                    break  # Only keep first active overlay
    
    def get_search_mode_display(self) -> str:
        """Get display text for search mode."""
        return f" ({self.ui.search_mode})" if self.ui.search_mode != "flat" else ""
    
    def is_cursor_valid(self, max_items: int) -> bool:
        """Check if cursor position is valid."""
        return 0 <= self.navigation.cursor < max_items
    
    def safe_navigate(self, direction: str, max_items: int) -> None:
        """Safely navigate with bounds checking."""
        if direction == "up":
            self.navigation.cursor = max(0, self.navigation.cursor - 1)
        elif direction == "down":
            self.navigation.cursor = min(max_items - 1, self.navigation.cursor + 1)
        
        # Log navigation for debugging
        logger.debug(f"Navigated {direction} to position {self.navigation.cursor}")
    
    def clear_search_state(self) -> None:
        """Clear search-related state."""
        self.ui.search_query = ""
        self.ui.search_cursor = 0
        logger.debug("Search state cleared")
    
    def toggle_overlay(self, overlay_name: str) -> None:
        """Toggle a specific overlay state."""
        # Clear all overlays first
        self.ui.show_help = False
        self.ui.show_playlist = False
        self.ui.show_search = False
        
        # Activate requested overlay
        if overlay_name == "help":
            self.ui.show_help = True
        elif overlay_name == "playlist":
            self.ui.show_playlist = True
        elif overlay_name == "search":
            self.ui.show_search = True
        
        logger.debug(f"Activated overlay: {overlay_name}")


# Global state manager instance
state_manager = StateManager()


def validate_state() -> None:
    """Validate current state and fix common issues."""
    try:
        # Check for overlay conflicts
        overlays_active = sum([
            state_manager.ui.show_help,
            state_manager.ui.show_playlist,
            state_manager.ui.show_search
        ])
        if overlays_active > 1:
            # Deactivate all overlays first, then reactivate the first one
            if state_manager.ui.show_help:
                state_manager.ui.show_playlist = False
                state_manager.ui.show_search = False
            elif state_manager.ui.show_playlist:
                state_manager.ui.show_help = False
                state_manager.ui.show_search = False
            elif state_manager.ui.show_search:
                state_manager.ui.show_help = False
                state_manager.ui.show_playlist = False
        
        # Check navigation bounds
        if state_manager.navigation.cursor < 0:
            state_manager.navigation.cursor = 0
        
        # Check volume bounds
        if state_manager.playback.volume < 0 or state_manager.playback.volume > 100:
            state_manager.playback.volume = max(0, min(100, state_manager.playback.volume))
        
        # Check speed bounds
        if state_manager.playback.effect_speed < 0.5 or state_manager.playback.effect_speed > 2.0:
            state_manager.playback.effect_speed = max(0.5, min(2.0, state_manager.playback.effect_speed))
        
        from logging_config import get_logger
        logger = get_logger('state')
        logger.debug("State validation completed")
        
    except Exception as e:
        from logging_config import get_logger
        logger = get_logger('state')
        logger.error(f"Error in state validation: {e}")