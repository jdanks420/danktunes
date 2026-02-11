# danktunes

[![GPL License](https://img.shields.io/badge/license-GPL-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A minimalist terminal-based music player with playlist support, metadata display, and M3U playlist compatibility.

## Features

- **File browser** with directory tree navigation
- **Audio playback** using mpg123/aplay
- **Playlist management** with shuffle mode
- **Speed control** and seeking
- **Metadata display** (Artist - Title)
- **M3U playlist support** (import/export)
- **TOML configuration** for colors and directories
- **Help screen** with all keyboard shortcuts

## Installation

```bash
# Install system dependencies (Debian/Ubuntu)
sudo apt install mpg123 alsa-utils ffmpeg

# Optional: tomli for Python < 3.11
pip install tomli

# Run the player
python3 danktunes.py
```

### Creating a Shell Alias

To easily launch danktunes from anywhere, add an alias to your shell configuration:

**For Bash (add to ~/.bashrc):**
```bash
echo 'alias danktunes="python3 /path/to/danktunes/danktunes.py"' >> ~/.bashrc
source ~/.bashrc
```

**For Zsh (add to ~/.zshrc):**
```bash
echo 'alias danktunes="python3 /path/to/danktunes/danktunes.py"' >> ~/.zshrc
source ~/.zshrc
```

**For Fish (add to ~/.config/fish/config.fish):**
```bash
echo 'alias danktunes "python3 /path/to/danktunes/danktunes.py"' >> ~/.config/fish/config.fish
source ~/.config/fish/config.fish
```

Replace `/path/to/danktunes/` with the actual path where you cloned the repository.

## Configuration

The player uses a TOML configuration file for customization.

### Config File Location

The player follows the XDG Base Directory Specification:

- `~/.config/danktunes/danktunes.toml` (standard location)
- `danktunes.toml` (in project folder for portable/development use)

### Default Configuration

```toml
[music]
directory = "~/Music"

[playlist]
directory = "~/.config/danktunes/playlists"

[colors]
header = "bold"
secondary = "gray"
selection = "reverse"
text = "default"
```

### Available Colors

- **Basic**: black, red, green, yellow, blue, magenta, cyan, white
- **Bright**: bright_black (gray), bright_red, bright_green, bright_yellow, bright_blue, bright_magenta, bright_cyan, bright_white
- **Styles**: bold, dim, italic, underline, reverse, hidden

## Controls

| Key | Action |
|-----|--------|
| **Navigation** | |
| ↑/↓ or j/k | Navigate files |
| Enter | Play file / Toggle folder |
| **Playback** | |
| Space | Play/Pause |
| n | Next track |
| p | Previous track |
| s | Stop |
| →/← | Seek ±5s |
| 1/2 | Decrease/Increase speed |
| 0 | Reset speed to 1.0x |
| **Playlist** | |
| a | Add selected to playlist |
| A | Add all visible files |
| x | Remove from playlist |
| c | Clear playlist |
| Shift+S | Toggle shuffle |
| [ / ] | Previous/Next in playlist |
| v | View playlist |
| L | Load playlist |
| W | Save playlist |
| **Other** | |
| ? | Show help |
| q | Quit |

## Playlist View

Press `v` to toggle playlist view:

| Key | Action |
|-----|--------|
| ↑/↓ or j/k | Scroll through playlist |
| Enter | Play selected track |
| x | Remove selected track |
| v | Close playlist view |

## M3U Playlists

The player supports standard M3U playlist format:

```m3u
#EXTM3U
#EXTINF:180,Artist - Song Title.mp3
Artist/Song Title.mp3
```

### Commands

- **W** (in playlist view): Save current playlist (prompts for name)
- **L**: Load first available playlist
- **import_m3u()**: Import external M3U files (programmatic)

Playlists are stored in `config/playlists/` as `.m3u` files.

## Supported Formats

| Format | Player |
|--------|--------|
| MP3 | mpg123 |
| OGG | mpg123 |
| AAC | mpg123 |
| FLAC | mpg123 |
| M4A | mpg123 |
| WAV | aplay |

## Keyboard Shortcuts

Press `?` anytime to view all keyboard shortcuts in the help overlay.

## Project Structure

```
danktunes/
├── danktunes.py      # Main application
├── danktunes.toml    # Configuration file
├── playlists/        # M3U playlist storage
├── README.md        # Documentation
├── TODO.md          # Feature roadmap
├── manpage.txt      # Man page
└── requirements.txt # Dependencies
```
