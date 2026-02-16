# Danktunes - Project Description

## Overview

Danktunes is a terminal-based music player written in Python that serves as a user-friendly frontend for mpg123. It provides a minimalist, keyboard-driven interface for browsing and playing audio files directly in the terminal.

**Version**: 2.0.0  
**License**: GPL  
**Python**: 3.8+  
**Main Entry Point**: `danktunes.py`

## Architecture

### Core Files

- **`danktunes.py`**: Main application (~4000+ lines). Contains all player logic, UI rendering, and input handling
- **`logging_config.py`**: Logging configuration module
- **`danktunes.toml`**: Default configuration file
- **`pyproject.toml`**: Python project configuration
- **`tests/`**: Test suite with 8 test modules

### Key Dependencies

| Dependency | Purpose |
|------------|---------|
| `mpg123` | Primary audio player for MP3, OGG, AAC, FLAC, M4A |
| `aplay` | WAV file playback (ALSA) |
| `ffprobe` | Audio metadata extraction |
| `ffmpeg` | Album art extraction |

## Features

### Playback
- **Multi-format support**: MP3, WAV, FLAC, OGG, M4A, AAC
- **Speed control**: 0.5x to 2.0x playback speed
- **Seeking**: ±5 seconds per seek action
- **Volume control**: 0-100% with ALSA integration

### File Browser
- **Directory tree navigation**: Expand/collapse folders
- **Flat and recursive search**: Filter library by filename
- **Duration scanning**: Parallel scanning with caching
- **Sort modes**: By name, date, or duration

### Playlist Management
- **Add/remove tracks**: Individual or bulk add
- **Shuffle mode**: Standard shuffle or smart shuffle (avoids recently played)
- **Repeat modes**: Off, all, one
- **M3U support**: Import/export standard M3U playlists

### Metadata & Display
- **Artist/Title extraction**: Via ffprobe
- **Album art**: Extracts embedded art or finds local cover images
- **Terminal image protocols**: Supports Kitty, iTerm2, Sixel, urxvt, Konsole, ueberzug
- **Customizable colors**: Via TOML configuration
- **Desktop notifications**: Track change notifications via notify-send

### State Persistence
- **Auto-save**: Volume, position, expanded directories, shuffle/repeat modes
- **Restores on launch**: Last played track and position

## Configuration

Configuration is stored at `~/.config/danktunes/danktunes.toml` (or `danktunes.toml` in project folder).

### Sections

```toml
[music]
directory = "~/Music"          # Music library location

[playlist]
directory = "~/.config/danktunes/playlists"  # Playlist storage

[colors]
header = "bold"               # Header text color
secondary = "gray"            # Secondary info (duration, speed)
selection = "reverse"         # Selected item highlight
text = "default"              # Default text color

[ui]
borders = true                # Show Ranger-style borders
header_glyph = "😎"           # Custom emoji icon

[notifications]
enabled = false              # Desktop notifications
glyph = "🎵"                 # Notification icon

[album_art]
enabled = true               # Album art display
width = 20                   # Image width in cells
```

## Key Classes and Data Structures

### `TreeItem`
Represents a file or directory in the music library tree with:
- `path`: Path to file/directory
- `level`: Depth in tree
- `is_dir`: Boolean flag
- `parent`: Parent TreeItem
- `children`: List of child items
- `expanded`: Expansion state

### `PlayerState` (dataclass)
Centralized state container holding:
- Paths and configuration
- Current playback state (file, position, speed, volume)
- Metadata (artist, title)
- Audio process handle
- UI state (cursor, scroll, overlays)
- Playlist and shuffle history
- Search state
- Cache (track durations, album art)

### `TerminalImageProtocol`
Detects and manages terminal image display:
- Auto-detects best protocol (Kitty, iTerm2, Sixel, etc.)
- Provides protocol-specific image rendering functions

## Input Handling

All navigation and playback is keyboard-driven:

| Category | Keys | Action |
|----------|------|--------|
| Navigation | ↑/↓, j/k | Move cursor |
| Navigation | Enter | Play file / Toggle folder |
| Playback | Space | Play/Pause |
| Playback | n/p | Next/Previous track |
| Playback | s | Stop |
| Playback | ←/→ | Seek ±5s |
| Playback | 1/2 | Decrease/Increase speed |
| Playback | 0 | Reset speed to 1.0x |
| Playlist | a/A | Add selected/all to playlist |
| Playlist | x/c | Remove/Clear playlist |
| Playlist | Shift+S | Toggle shuffle |
| Playlist | r | Cycle repeat mode |
| Playlist | v/L/W | View/Load/Save playlist |
| Search | / | Toggle search |
| Help | ? | Toggle help overlay |
| Quit | q | Exit |

## UI Rendering

The UI uses ANSI escape codes for:
- Color formatting (via `COLOR_MAP`)
- Terminal control sequences (clear, cursor positioning)
- Optional Ranger-style borders (box-drawing characters)

The `draw()` function handles:
- Screen clearing and cursor positioning
- File browser rendering with indentation
- Progress bar with elapsed/total time
- Overlay rendering (help, playlist, search, album art)

## Caching & Performance

- **Directory cache**: Caches directory scans with mtime validation (max 100 entries)
- **Track duration cache**: LRU cache with 5000 entry limit
- **Album art cache**: Finds local covers or extracts embedded art
- **Parallel scanning**: Uses ThreadPoolExecutor for duration scanning
- **Command cache**: Caches `shutil.which()` results for external commands

## State Validation

The `validate_state()` function ensures:
- No conflicting overlays (help, playlist, search)
- Cursor within bounds of flat_items
- Playlist index within playlist bounds
- Volume within 0-100 range

## Testing

Test suite in `tests/` covers:
- `test_terminal_images.py`: Image protocol detection
- `test_album_art.py`: Album art extraction and caching
- `test_features.py`: Core player features
- `test_persistence.py`: State save/load
- `test_playlist.py`: Playlist operations
- `test_m3u.py`: M3U import/export
- `test_state.py`: State validation
- `test_scan.py`: Directory scanning

## Logging

Uses a custom `logging_config.py` module. Logger name is `'main'` for the core application.

## Constants

Key constants in `danktunes.py`:
- `REDRAW_INTERVAL`: 0.12s (UI refresh)
- `SEEK_COOLDOWN`: 0.3s between seeks
- `MAX_TRACK_DURATIONS`: 5000 cached durations
- `SPEED_MIN/MAX`: 0.5x - 2.0x
- `SEEK_SECONDS`: 5s per seek
- `VISIBLE_PLAYLIST_ITEMS`: 15 items in playlist view

## Notes for Developers

1. **Terminal requirements**: Must run in a real TTY for keyboard input
2. **Signal handling**: Uses SIGTERM/SIGSTOP/SIGCONT for playback control
3. **Process groups**: Uses `os.setsid()` and `os.killpg()` for process control
4. **Path validation**: Validates paths stay within music directory for security
5. **Unicode support**: Full Unicode support with display width calculation for CJK characters
