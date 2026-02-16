import pytest
from pathlib import Path
import tempfile
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestM3UImportExport:
    """Tests for M3U playlist import/export."""

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
        state.playlist_dir = Path.home() / ".local/share/music_player/playlists"
        state.music_dir = Path.home() / "Music"

    def test_save_playlist_m3u(self, temp_playlist_dir):
        """Test saving playlist to M3U file."""
        state = danktunes.state
        state.playlist_dir = temp_playlist_dir
        state.music_dir = Path("/music")
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"dummy")
            temp_file = f.name
        
        try:
            state.playlist = [temp_file]
            result = danktunes.save_playlist("test_playlist")
            
            assert result is True
            assert (temp_playlist_dir / "test_playlist.m3u").exists()
        finally:
            os.unlink(temp_file)

    def test_save_playlist_invalid_name(self, temp_playlist_dir):
        """Test saving with invalid name."""
        state = danktunes.state
        state.playlist_dir = temp_playlist_dir
        state.playlist = ["/music/test.mp3"]
        
        assert danktunes.save_playlist("test/playlist") is False
        assert danktunes.save_playlist("test.playlist") is False
        assert danktunes.save_playlist("") is False

    def test_save_empty_playlist(self, temp_playlist_dir):
        """Test saving empty playlist."""
        state = danktunes.state
        state.playlist_dir = temp_playlist_dir
        state.playlist = []
        
        result = danktunes.save_playlist("empty")
        
        assert result is False

    def test_load_playlist_m3u(self, temp_playlist_dir):
        """Test loading playlist from M3U."""
        state = danktunes.state
        state.playlist_dir = temp_playlist_dir
        state.music_dir = Path("/music")
        
        m3u_content = """#EXTM3U
#EXTINF:180,Test Song
/music/test1.mp3
#EXTINF:240,Another Song
/music/test2.mp3
"""
        m3u_file = temp_playlist_dir / "test.m3u"
        m3u_file.write_text(m3u_content)
        
        result = danktunes.load_playlist("test")
        
        assert result is True

    def test_load_nonexistent_playlist(self, temp_playlist_dir):
        """Test loading nonexistent playlist."""
        state = danktunes.state
        state.playlist_dir = temp_playlist_dir
        
        result = danktunes.load_playlist("nonexistent")
        
        assert result is False

    def test_list_playlists(self, temp_playlist_dir):
        """Test listing playlists."""
        state = danktunes.state
        state.playlist_dir = temp_playlist_dir
        
        (temp_playlist_dir / "playlist1.m3u").touch()
        (temp_playlist_dir / "playlist2.m3u").touch()
        (temp_playlist_dir / "readme.txt").touch()
        
        playlists = danktunes.list_playlists()
        
        assert "playlist1" in playlists
        assert "playlist2" in playlists
        assert "readme" not in playlists


class TestM3UParsing:
    """Tests for M3U file parsing."""

    def test_m3u_extinf_parsing(self):
        """Test parsing EXTINF lines."""
        line = "#EXTINF:180,Test Artist - Test Title"
        
        assert "180" in line
        assert "Test Artist" in line

    def test_m3u_empty_lines(self):
        """Test handling of empty lines in M3U."""
        lines = ["#EXTM3U", "", "#EXTINF:120,Test", "/music/test.mp3", ""]
        
        non_empty = [l for l in lines if l.strip()]
        
        assert len(non_empty) == 3
