"""
Audio processing module for danktunes.
"""
import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager

from danktunes.logging_config import get_logger, AudioPlayerError

logger = get_logger('audio')


class AudioPlayer:
    """Base class for audio players."""
    
    def __init__(self, executable: str):
        self.executable = executable
        self.process = None
        self.current_file = None
    
    def play(self, file_path: str, start_pos: int = 0) -> bool:
        """Play audio file."""
        raise NotImplementedError("Subclasses must implement play()")
    
    def stop(self) -> None:
        """Stop audio playback."""
        raise NotImplementedError("Subclasses must implement stop()")
    
    def pause(self) -> None:
        """Pause audio playback."""
        raise NotImplementedError("Subclasses must implement pause()")
    
    def resume(self) -> None:
        """Resume audio playback."""
        raise NotImplementedError("Subclasses must implement pause()")
    
    def seek(self, seconds: int) -> None:
        """Seek to position."""
        raise NotImplementedError("Subclasses must implement seek()")


class MPG123Player(AudioPlayer):
    """MPG123 audio player implementation."""
    
    def __init__(self):
        super().__init__("mpg123")
    
    def play(self, file_path: str, start_pos: int = 0) -> bool:
        """Play audio file with mpg123."""
        try:
            cmd = [self.executable]
            if start_pos > 0:
                cmd.extend(["-k", str(start_pos)])
            cmd.append(file_path)
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )
            
            self.current_file = file_path
            logger.info(f"Started playback: {file_path}")
            return True
            
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.error(f"Failed to start {self.executable}: {e}")
            raise AudioPlayerError(f"Failed to start audio player: {e}")
    
    def stop(self) -> None:
        """Stop mpg123 playback."""
        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                logger.info(f"Stopping audio process: {self.process.pid}")
                self.process.wait(timeout=1.0)
            except (ProcessLookupError, PermissionError) as e:
                logger.warning(f"Process termination error: {e}")
                pass
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    logger.warning(f"Force killed audio process: {self.process.pid}")
                    self.process.wait(timeout=0.5)
                except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Force kill failed: {e}")
                    pass
            finally:
                self.process = None
                self.current_file = None
                logger.info("Audio playback stopped")
    
    def set_volume(self, volume: int) -> bool:
        """Set volume level (0-100)."""
        if not self.process or self.process.poll() is not None:
            return False
        
        try:
            # mpg123 volume control
            subprocess.run([
                self.executable,
                "-r",
                "volume", f"{volume}%"
            ], check=True)
            logger.info(f"Volume set to {volume}%")
            return True
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to set volume: {e}")
            return False


class APlayPlayer(AudioPlayer):
    """APLAY audio player implementation."""
    
    def __init__(self):
        super().__init__("aplay")


@contextmanager
def get_audio_player(player_type: str = "mpg123"):
    """Get an audio player instance."""
    if player_type == "mpg123":
        yield MPG123Player()
    elif player_type == "aplay":
        yield APlayPlayer()
    else:
        raise AudioPlayerError(f"Unsupported audio player: {player_type}")


def detect_available_player() -> str:
    """Detect available audio players."""
    players = ["mpg123", "aplay", "ffplay"]
    
    for player in players:
        try:
            subprocess.run([player, "--version"], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL, 
                         check=True, timeout=1)
            return player
        except (subprocess.SubprocessError, FileNotFoundError):
            continue
    
    logger.warning("No supported audio player found")
    return "mpg123"  # Default fallback