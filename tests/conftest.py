import os
import sys
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import danktunes


@pytest.fixture
def temp_music_dir():
    """Create a temporary music directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        music_dir = Path(tmpdir) / "music"
        music_dir.mkdir()
        
        (music_dir / "subdir").mkdir()
        
        (music_dir / "test1.mp3").touch()
        (music_dir / "test2.flac").touch()
        (music_dir / "test3.ogg").touch()
        (music_dir / "test4.txt").touch()
        
        (music_dir / "subdir" / "nested.mp3").touch()
        
        yield music_dir


@pytest.fixture
def temp_playlist_dir():
    """Create a temporary playlist directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        playlist_dir = Path(tmpdir) / "playlists"
        playlist_dir.mkdir()
        yield playlist_dir


@pytest.fixture
def clean_state():
    """Provide a clean state for testing."""
    state = danktunes.PlayerState()
    yield state
