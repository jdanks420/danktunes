import pytest
from pathlib import Path
import danktunes


class TestScanDirectory:
    """Tests for scan_directory() function."""

    def test_scan_empty_directory(self, temp_music_dir):
        """Test scanning an empty directory."""
        empty_dir = temp_music_dir / "empty"
        empty_dir.mkdir()
        
        items = danktunes.scan_directory(empty_dir)
        
        assert items == []

    def test_scan_directory_with_files(self, temp_music_dir):
        """Test scanning directory with audio files."""
        items = danktunes.scan_directory(temp_music_dir)
        
        file_names = [item.path.name for item in items]
        
        assert "test1.mp3" in file_names
        assert "test2.flac" in file_names
        assert "test3.ogg" in file_names

    def test_scan_filters_non_audio_files(self, temp_music_dir):
        """Test that non-audio files are filtered out."""
        items = danktunes.scan_directory(temp_music_dir)
        
        file_names = [item.path.name for item in items]
        
        assert "test4.txt" not in file_names

    def test_scan_recursive_with_expansion(self, temp_music_dir):
        """Test scanning with directory expansion."""
        state = danktunes.state
        state.expanded_dirs.add(str(temp_music_dir / "subdir"))
        
        items = danktunes.scan_directory(temp_music_dir)
        
        dirs = [item for item in items if item.is_dir]
        assert len(dirs) > 0
        
        state.expanded_dirs.clear()

    def test_scan_directory_with_subdirs(self, temp_music_dir):
        """Test that subdirectories are included."""
        items = danktunes.scan_directory(temp_music_dir)
        
        dirs = [item for item in items if item.is_dir]
        
        assert len(dirs) > 0
        assert any("subdir" in str(d.path) for d in dirs)

    def test_scan_nonexistent_directory(self):
        """Test scanning a nonexistent directory."""
        items = danktunes.scan_directory(Path("/nonexistent/path"))
        
        assert items == []

    def test_scan_permission_error(self):
        """Test handling of permission errors."""
        items = danktunes.scan_directory(Path("/root"))
        
        assert items == []


class TestFlattenTree:
    """Tests for flatten_tree() function."""

    def test_flatten_empty_list(self):
        """Test flattening an empty list."""
        result = danktunes.flatten_tree([])
        assert result == []

    def test_flatten_single_item(self):
        """Test flattening a single item."""
        item = danktunes.TreeItem("/test", level=0, is_dir=False)
        result = danktunes.flatten_tree([item])
        
        assert len(result) == 1
        assert result[0] is item

    def test_flatten_nested_expanded(self):
        """Test flattening nested expanded directories."""
        parent = danktunes.TreeItem("/parent", level=0, is_dir=True)
        parent.expanded = True
        child = danktunes.TreeItem("/parent/child.mp3", level=1, is_dir=False)
        parent.children = [child]
        
        result = danktunes.flatten_tree([parent])
        
        assert len(result) == 2

    def test_flatten_nested_collapsed(self):
        """Test flattening nested collapsed directories."""
        parent = danktunes.TreeItem("/parent", level=0, is_dir=True)
        parent.expanded = False
        child = danktunes.TreeItem("/parent/child.mp3", level=1, is_dir=False)
        parent.children = [child]
        
        result = danktunes.flatten_tree([parent])
        
        assert len(result) == 1


class TestTreeItem:
    """Tests for TreeItem class."""

    def test_tree_item_creation(self):
        """Test creating a TreeItem."""
        item = danktunes.TreeItem("/test/path.mp3", level=0, is_dir=False)
        
        assert item.path == Path("/test/path.mp3")
        assert item.level == 0
        assert item.is_dir is False
        assert item.expanded is False
        assert item.children == []

    def test_tree_item_directory(self):
        """Test creating a directory TreeItem."""
        item = danktunes.TreeItem("/test/dir", level=1, is_dir=True)
        
        assert item.is_dir is True
        assert item.expanded is False
