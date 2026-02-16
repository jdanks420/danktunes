import pytest
from pathlib import Path
import tempfile
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import danktunes


class TestTerminalImageProtocol:
    """Tests for terminal image protocol detection."""

    def test_detect_returns_string(self):
        """Test that detect returns a valid protocol string."""
        protocol = danktunes.TerminalImageProtocol.detect()
        valid = [
            danktunes.TerminalImageProtocol.KITTY,
            danktunes.TerminalImageProtocol.ITERM2,
            danktunes.TerminalImageProtocol.SIXEL,
            danktunes.TerminalImageProtocol.URXVT,
            danktunes.TerminalImageProtocol.KONSOLE,
            danktunes.TerminalImageProtocol.UEBERZUG,
            danktunes.TerminalImageProtocol.NONE,
        ]
        assert protocol in valid

    def test_get_protocol_name_returns_string(self):
        """Test that get_protocol_name returns a human-readable name."""
        name = danktunes.TerminalImageProtocol.get_protocol_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_print_image_returns_string(self):
        """Test that print_image returns a string."""
        result = danktunes.print_image("/nonexistent/path.jpg")
        assert isinstance(result, str)

    def test_clear_images_returns_string(self):
        """Test that clear_images returns a string."""
        result = danktunes.clear_images()
        assert isinstance(result, str)


class TestAlbumArtFunctions:
    """Tests for album art functions."""

    def test_print_image_iterm2_returns_escape_sequence(self):
        """Test that iTerm2 escape sequence starts with correct prefix."""
        result = danktunes.print_image_iterm2("/fake/path.jpg")
        assert "\033]1337;File=inline=1" in result or result == ""

    def test_print_image_kitty_returns_escape_sequence(self):
        """Test that Kitty escape sequence starts with correct prefix."""
        result = danktunes.print_image_kitty("/fake/path.jpg")
        assert "\033_G" in result or result == ""

    def test_print_image_ueberzug_returns_json(self):
        """Test that ueberzug returns JSON command."""
        result = danktunes.print_image_ueberzug("/fake/path.jpg", width=40, height=20, x=1, y=1)
        assert "action" in result
        assert "add" in result
        assert "danktunes-cover" in result

    def test_clear_ueberzug_returns_json(self):
        """Test that clear_ueberzug returns JSON command."""
        result = danktunes.clear_ueberzug()
        assert "action" in result
        assert "remove" in result

    def test_print_image_handles_invalid_path(self):
        """Test that print_image handles invalid paths gracefully."""
        result = danktunes.print_image("/completely/nonexistent/image.jpg")
        assert isinstance(result, str)

    def test_config_options_exist(self):
        """Test that album art config options exist."""
        assert hasattr(danktunes, 'ALBUM_ART_ENABLED')
        assert hasattr(danktunes, 'ALBUM_ART_WIDTH')
        assert isinstance(danktunes.ALBUM_ART_ENABLED, bool)
        assert isinstance(danktunes.ALBUM_ART_WIDTH, int)
