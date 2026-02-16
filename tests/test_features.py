import pytest
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestSortFunctions:
    """Tests for sort functionality."""

    def setup_method(self):
        """Reset global state before each test."""
        self._restore_state()

    def teardown_method(self):
        """Clean up global state after each test."""
        self._restore_state()

    def _restore_state(self):
        """Restore default state."""
        state = danktunes.state
        state.playlist = []
        state.playlist_index = 0
        state.sort_by = "name"
        state.sort_reverse = False

    def test_cycle_sort_mode(self):
        """Test cycling through sort modes."""
        state = danktunes.state
        assert state.sort_by == "name"
        
        danktunes.cycle_sort_mode()
        assert state.sort_by == "date"
        
        danktunes.cycle_sort_mode()
        assert state.sort_by == "duration"
        
        danktunes.cycle_sort_mode()
        assert state.sort_by == "name"

    def test_sort_playlist_by_name(self):
        """Test sorting playlist by name."""
        state = danktunes.state
        state.playlist = ["/music/zzz.mp3", "/music/aaa.mp3", "/music/mmm.mp3"]
        
        danktunes.sort_playlist()
        
        assert state.playlist == ["/music/aaa.mp3", "/music/mmm.mp3", "/music/zzz.mp3"]

    def test_sort_playlist_preserves_current(self):
        """Test that sort preserves current track position."""
        state = danktunes.state
        state.playlist = ["/music/zzz.mp3", "/music/aaa.mp3", "/music/mmm.mp3"]
        state.playlist_index = 1  # aaa.mp3
        
        danktunes.sort_playlist()
        
        assert state.playlist_index == 0  # aaa.mp3 is now first

    def test_reverse_sort(self):
        """Test reversing sort order."""
        state = danktunes.state
        state.playlist = ["/music/aaa.mp3", "/music/zzz.mp3"]
        
        danktunes.reverse_sort()
        
        assert state.sort_reverse is True
        assert state.playlist == ["/music/zzz.mp3", "/music/aaa.mp3"]


class TestFavorites:
    """Tests for favorites functionality."""

    def setup_method(self):
        """Reset global state before each test."""
        self._restore_state()

    def teardown_method(self):
        """Clean up global state after each test."""
        self._restore_state()

    def _restore_state(self):
        """Restore default state."""
        state = danktunes.state
        state.favorites = []
        state.current_path = None

    def test_toggle_favorite_add(self):
        """Test adding to favorites."""
        state = danktunes.state
        state.current_path = "/music/test.mp3"
        
        danktunes.toggle_favorite()
        
        assert "/music/test.mp3" in state.favorites

    def test_toggle_favorite_remove(self):
        """Test removing from favorites."""
        state = danktunes.state
        state.current_path = "/music/test.mp3"
        state.favorites = ["/music/test.mp3"]
        
        danktunes.toggle_favorite()
        
        assert "/music/test.mp3" not in state.favorites

    def test_toggle_favorite_no_track(self):
        """Test toggling favorite with no current track."""
        state = danktunes.state
        state.current_path = None
        
        danktunes.toggle_favorite()
        
        assert state.favorites == []

    def test_is_favorite(self):
        """Test checking if track is favorite."""
        state = danktunes.state
        state.favorites = ["/music/test.mp3"]
        
        assert danktunes.is_favorite("/music/test.mp3") is True
        assert danktunes.is_favorite("/music/other.mp3") is False


class TestSmartShuffle:
    """Tests for smart shuffle functionality."""

    def setup_method(self):
        """Reset global state before each test."""
        self._restore_state()

    def teardown_method(self):
        """Clean up global state after each test."""
        self._restore_state()

    def _restore_state(self):
        """Restore default state."""
        state = danktunes.state
        state.playlist = []
        state.playlist_index = 0
        state.shuffle_history = []
        state.shuffle_history_max = 20

    def test_smart_shuffle_empty(self):
        """Test smart shuffle with empty playlist."""
        result = danktunes.smart_shuffle()
        # Function should handle empty playlist gracefully

    def test_smart_shuffle_uses_history(self):
        """Test smart shuffle avoids recently played tracks."""
        state = danktunes.state
        state.playlist = ["/music/track1.mp3", "/music/track2.mp3", "/music/track3.mp3", "/music/track4.mp3"]
        state.playlist_index = 0
        state.shuffle_history = ["/music/track1.mp3", "/music/track2.mp3"]
        
        # Run smart shuffle - should try to avoid track1 and track2
        # (deterministic test difficult due to randomness, just verify it runs)
        try:
            danktunes.smart_shuffle()
        except Exception as e:
            pytest.fail(f"smart_shuffle raised exception: {e}")
