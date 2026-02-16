import pytest
from pathlib import Path
import tempfile
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestAlbumArt:
    """Tests for album art detection."""

    def setup_method(self):
        """Reset album art cache before each test."""
        danktunes._album_art_cache = {}
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up after each test."""
        danktunes._album_art_cache = {}
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_local_cover_jpg(self):
        """Test finding cover.jpg in same directory."""
        cover_path = Path(self.temp_dir) / "cover.jpg"
        cover_path.write_text("dummy image")
        audio_path = Path(self.temp_dir) / "music.mp3"
        audio_path.write_text("dummy audio")
        
        result = danktunes._find_local_album_art(audio_path, str(self.temp_dir))
        
        assert result == str(cover_path)

    def test_find_local_cover_png(self):
        """Test finding cover.png in same directory."""
        cover_path = Path(self.temp_dir) / "cover.png"
        cover_path.write_text("dummy image")
        audio_path = Path(self.temp_dir) / "music.mp3"
        audio_path.write_text("dummy audio")
        
        result = danktunes._find_local_album_art(audio_path, str(self.temp_dir))
        
        assert result == str(cover_path)

    def test_find_folder_jpg(self):
        """Test finding folder.jpg in same directory."""
        cover_path = Path(self.temp_dir) / "folder.jpg"
        cover_path.write_text("dummy image")
        audio_path = Path(self.temp_dir) / "music.mp3"
        audio_path.write_text("dummy audio")
        
        result = danktunes._find_local_album_art(audio_path, str(self.temp_dir))
        
        assert result == str(cover_path)

    def test_no_cover_found(self):
        """Test when no cover image exists."""
        audio_path = Path(self.temp_dir) / "music.mp3"
        audio_path.write_text("dummy audio")
        
        result = danktunes._find_local_album_art(audio_path, str(self.temp_dir))
        
        assert result is None

    def test_album_art_cache(self):
        """Test album art caching."""
        audio_path = Path(self.temp_dir) / "music.mp3"
        audio_path.write_text("dummy audio")
        
        result1 = danktunes.get_album_art(str(audio_path))
        
        assert str(audio_path) in danktunes._album_art_cache

    def test_clear_album_art_cache(self):
        """Test clearing the cache."""
        audio_path = Path(self.temp_dir) / "music.mp3"
        audio_path.write_text("dummy audio")
        
        danktunes.get_album_art(str(audio_path))
        assert len(danktunes._album_art_cache) > 0
        
        danktunes.clear_album_art_cache()
        assert len(danktunes._album_art_cache) == 0
