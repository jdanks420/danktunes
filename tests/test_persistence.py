import pytest
from pathlib import Path
import tempfile
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestStatePersistence:
    """Tests for state persistence functions."""

    def setup_method(self):
        """Reset global state before each test."""
        self._restore_state()
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        danktunes.CONFIG_DIR = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up global state after each test."""
        self._restore_state()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _restore_state(self):
        """Restore default state."""
        state = danktunes.state
        state.volume = 100
        state.current_path = None
        state.current_position = 0
        state.expanded_dirs = set()
        state.shuffle_mode = False
        state.repeat_mode = "off"

    def test_save_state_creates_file(self):
        """Test that save_state creates a state file."""
        state = danktunes.state
        state.volume = 75
        
        result = danktunes.save_state()
        
        assert result is True
        assert self.state_file.exists()

    def test_load_state_restores_volume(self):
        """Test loading restores volume."""
        state = danktunes.state
        
        self.state_file.write_text('{"volume": 50}')
        
        result = danktunes.load_state()
        
        assert result is True
        assert state.volume == 50

    def test_load_state_restores_expanded_dirs(self):
        """Test loading restores expanded directories."""
        state = danktunes.state
        
        self.state_file.write_text('{"expanded_dirs": ["/music/test", "/music/test2"]}')
        
        result = danktunes.load_state()
        
        assert result is True
        assert "/music/test" in state.expanded_dirs
        assert "/music/test2" in state.expanded_dirs

    def test_load_state_volume_bounds(self):
        """Test loading clamps volume to valid range."""
        state = danktunes.state
        
        self.state_file.write_text('{"volume": 150}')
        
        danktunes.load_state()
        
        assert state.volume == 100

    def test_load_state_negative_volume(self):
        """Test loading clamps negative volume to 0."""
        state = danktunes.state
        
        self.state_file.write_text('{"volume": -10}')
        
        danktunes.load_state()
        
        assert state.volume == 0

    def test_load_state_no_file(self):
        """Test loading returns False when no state file."""
        result = danktunes.load_state()
        
        assert result is False

    def test_save_and_load_cycle(self):
        """Test that save/load preserves state."""
        state = danktunes.state
        state.volume = 42
        state.expanded_dirs = {"/music/album1", "/music/album2"}
        state.shuffle_mode = True
        state.repeat_mode = "one"
        
        danktunes.save_state()
        
        state.volume = 100
        state.expanded_dirs = set()
        state.shuffle_mode = False
        state.repeat_mode = "off"
        
        danktunes.load_state()
        
        assert state.volume == 42
        assert state.expanded_dirs == {"/music/album1", "/music/album2"}
        assert state.shuffle_mode is True
        assert state.repeat_mode == "one"
