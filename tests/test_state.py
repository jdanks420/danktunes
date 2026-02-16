import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestStateValidation:
    """Tests for state validation."""

    def setup_method(self):
        """Reset global state before each test."""
        self._restore_state()

    def teardown_method(self):
        """Clean up global state after each test."""
        self._restore_state()

    def _restore_state(self):
        """Restore default state."""
        state = danktunes.state
        state.show_help = False
        state.show_playlist = False
        state.show_search = False
        state.cursor = 0
        state.flat_items = []
        state.playlist = []
        state.playlist_index = 0
        state.playlist_scroll_offset = 0
        state.volume = 100

    def test_validate_state_overlay_conflict(self):
        """Test handling of multiple overlay conflicts."""
        state = danktunes.state
        state.show_help = True
        state.show_playlist = True
        state.show_search = True
        
        danktunes.validate_state()
        
        assert state.show_help is False
        assert state.show_playlist is False
        assert state.show_search is False

    def test_validate_state_cursor_bounds(self):
        """Test cursor bounds validation."""
        state = danktunes.state
        state.flat_items = [danktunes.TreeItem("/test", 0, False) for _ in range(5)]
        state.cursor = 10
        
        danktunes.validate_state()
        
        assert state.cursor == 4

    def test_validate_state_playlist_index_bounds(self):
        """Test playlist index bounds validation."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3"]
        state.playlist_index = 5
        
        danktunes.validate_state()
        
        assert state.playlist_index == 1

    def test_validate_state_playlist_scroll_offset(self):
        """Test playlist scroll offset validation."""
        state = danktunes.state
        state.playlist = [f"/music/test{i}.mp3" for i in range(20)]
        state.playlist_scroll_offset = 100
        
        danktunes.validate_state()
        
        assert state.playlist_scroll_offset <= 5

    def test_validate_state_volume_bounds(self):
        """Test volume bounds validation."""
        state = danktunes.state
        state.volume = 150
        
        danktunes.validate_state()
        
        assert state.volume == 100

    def test_validate_state_negative_volume(self):
        """Test negative volume handling."""
        state = danktunes.state
        state.volume = -10
        
        danktunes.validate_state()
        
        assert state.volume == 0


class TestPlayerState:
    """Tests for PlayerState dataclass."""

    def test_player_state_defaults(self):
        """Test PlayerState default values."""
        state = danktunes.PlayerState()
        
        assert state.music_dir == Path.home() / "Music"
        assert state.cursor == 0
        assert state.scroll_offset == 0
        assert state.volume == 100
        assert state.effect_speed == 1.0
        assert state.shuffle_mode is False
        assert state.repeat_mode == "off"
        assert state.paused is False

    def test_player_state_track_durations(self):
        """Test track_durations initialization."""
        state = danktunes.PlayerState()
        
        assert state.track_durations == {}


class TestTogglePlaylistView:
    """Tests for playlist view toggle."""

    def setup_method(self):
        """Reset global state before each test."""
        self._restore_state()

    def teardown_method(self):
        """Clean up global state after each test."""
        self._restore_state()

    def _restore_state(self):
        """Restore default state."""
        state = danktunes.state
        state.show_help = False
        state.show_playlist = False
        state.show_search = False

    def test_toggle_playlist_exclusive(self):
        """Test that playlist toggle is exclusive with other overlays."""
        state = danktunes.state
        state.show_help = True
        
        danktunes.toggle_playlist_view()
        
        assert state.show_playlist is True
        assert state.show_help is False
        assert state.show_search is False

    def test_toggle_playlist_off(self):
        """Test turning off playlist view."""
        state = danktunes.state
        state.show_playlist = True
        
        danktunes.toggle_playlist_view()
        
        assert state.show_playlist is False
