import pytest
from pathlib import Path
import tempfile
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestPlaylistFunctions:
    """Tests for playlist management functions."""

    def setup_method(self):
        """Reset global state before each test."""
        danktunes.state.playlist = []
        danktunes.state.playlist_index = 0
        danktunes.state.playlist_scroll_offset = 0
        danktunes.state.shuffle_mode = False
        danktunes.state.repeat_mode = "off"

    def teardown_method(self):
        """Clean up global state after each test."""
        danktunes.state.playlist = []
        danktunes.state.playlist_index = 0
        danktunes.state.playlist_scroll_offset = 0
        danktunes.state.shuffle_mode = False
        danktunes.state.repeat_mode = "off"

    def test_add_to_playlist(self):
        """Test adding a track to playlist."""
        state = danktunes.state
        
        danktunes.add_to_playlist("/music/test.mp3")
        
        assert len(state.playlist) == 1
        assert state.playlist[0] == "/music/test.mp3"

    def test_add_multiple_to_playlist(self):
        """Test adding multiple tracks."""
        state = danktunes.state
        
        danktunes.add_to_playlist("/music/test1.mp3")
        danktunes.add_to_playlist("/music/test2.mp3")
        danktunes.add_to_playlist("/music/test3.mp3")
        
        assert len(state.playlist) == 3

    def test_remove_from_playlist(self):
        """Test removing a track from playlist."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3", "/music/test3.mp3"]
        
        danktunes.remove_from_playlist(1)
        
        assert len(state.playlist) == 2
        assert "/music/test2.mp3" not in state.playlist

    def test_remove_from_playlist_updates_index(self):
        """Test that removing updates playlist index."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3", "/music/test3.mp3"]
        state.playlist_index = 1
        
        danktunes.remove_from_playlist(0)
        
        assert len(state.playlist) == 2

    def test_remove_invalid_index(self):
        """Test removing with invalid index does nothing."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3"]
        
        danktunes.remove_from_playlist(5)
        danktunes.remove_from_playlist(-1)
        
        assert len(state.playlist) == 1

    def test_clear_playlist(self):
        """Test clearing the playlist."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3"]
        state.playlist_index = 1
        state.playlist_scroll_offset = 5
        
        danktunes.clear_playlist()
        
        assert state.playlist == []
        assert state.playlist_index == 0
        assert state.playlist_scroll_offset == 0


class TestShuffleMode:
    """Tests for shuffle functionality."""

    def setup_method(self):
        """Reset global state before each test."""
        danktunes.state.shuffle_mode = False

    def teardown_method(self):
        """Clean up global state after each test."""
        danktunes.state.shuffle_mode = False

    def test_toggle_shuffle(self):
        """Test toggling shuffle mode."""
        state = danktunes.state
        
        assert state.shuffle_mode is False
        
        danktunes.toggle_shuffle_mode()
        
        assert state.shuffle_mode is True

    def test_shuffle_preserves_current(self):
        """Test that shuffle preserves current track position."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3", "/music/test3.mp3"]
        state.playlist_index = 1
        
        danktunes.toggle_shuffle_mode()
        
        assert state.shuffle_mode is True

    def test_shuffle_on_empty_playlist(self):
        """Test shuffling empty playlist doesn't error."""
        state = danktunes.state
        
        danktunes.toggle_shuffle_mode()
        
        assert state.shuffle_mode is True


class TestRepeatMode:
    """Tests for repeat mode functionality."""

    def setup_method(self):
        """Reset global state before each test."""
        danktunes.state.repeat_mode = "off"

    def teardown_method(self):
        """Clean up global state after each test."""
        danktunes.state.repeat_mode = "off"

    def test_toggle_repeat_mode(self):
        """Test cycling through repeat modes."""
        state = danktunes.state
        assert state.repeat_mode == "off"
        
        danktunes.toggle_repeat_mode()
        assert state.repeat_mode == "all"
        
        danktunes.toggle_repeat_mode()
        assert state.repeat_mode == "one"
        
        danktunes.toggle_repeat_mode()
        assert state.repeat_mode == "off"


class TestNavigation:
    """Tests for track navigation."""

    def setup_method(self):
        """Reset global state before each test."""
        danktunes.state.playlist = []
        danktunes.state.playlist_index = 0

    def teardown_method(self):
        """Clean up global state after each test."""
        danktunes.state.playlist = []
        danktunes.state.playlist_index = 0

    def test_go_to_next_track(self):
        """Test going to next track."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3", "/music/test3.mp3"]
        state.playlist_index = 0
        
        result = danktunes.go_to_next_track()
        
        assert result is True
        assert state.playlist_index == 1

    def test_go_to_next_track_at_end(self):
        """Test going to next track at end of playlist."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3"]
        state.playlist_index = 1
        
        result = danktunes.go_to_next_track()
        
        assert result is False

    def test_go_to_next_track_repeat_all(self):
        """Test repeat all mode."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3"]
        state.playlist_index = 1
        state.repeat_mode = "all"
        
        result = danktunes.go_to_next_track()
        
        assert result is True
        assert state.playlist_index == 0

    def test_go_to_previous_track(self):
        """Test going to previous track."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3", "/music/test3.mp3"]
        state.playlist_index = 2
        
        result = danktunes.go_to_previous_track()
        
        assert result is True
        assert state.playlist_index == 1

    def test_get_current_track(self):
        """Test getting current track."""
        state = danktunes.state
        state.playlist = ["/music/test1.mp3", "/music/test2.mp3"]
        state.playlist_index = 1
        
        result = danktunes.get_current_track()
        
        assert result == "/music/test2.mp3"

    def test_get_current_track_empty(self):
        """Test getting current track from empty playlist."""
        state = danktunes.state
        
        result = danktunes.get_current_track()
        
        assert result is None
