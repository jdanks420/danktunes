# danktunes

[![GPL License](https://img.shields.io/badge/license-GPL-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

A vibe coded minimalist terminal-based music player that serves as a user-friendly frontend for mpg123. Features playlist support, metadata display, and M3U playlist compatibility.


<img width="778" height="696" alt="image" src="https://github.com/user-attachments/assets/ee71ca4e-da1f-4db7-aba5-fd9ad160af42" />

<img width="761" height="726" alt="image" src="https://github.com/user-attachments/assets/190a40bf-24dc-4b15-bee1-96fd91fc400a" />

Fits nicely into multiplexers with minimal ui.
<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/5ee853a9-caa6-41cc-9c06-1a8ead3f7329" />
album art overlay
<img width="1155" height="891" alt="image" src="https://github.com/user-attachments/assets/7bcb662c-3edd-427f-b277-6acf9353b7ba" />




## Features

- **File browser** with directory tree navigation
- **Audio playback** using mpg123/aplay
- **Playlist management** with shuffle and repeat modes
- **Speed control** and seeking
- **Metadata display** (Artist - Title)
- **M3U playlist support** (import/export)
- **TOML configuration** for colors and directories
- **Help screen** with all keyboard shortcuts
- **Search** through your music library
- **Album art** display in terminal (iTerm2, Kitty, Ueberzug)
- **Overlays** for help, playlist, search, and album art views
- **Favorites** - mark and manage favorite tracks
- **Sort modes** - sort playlist by name, date, or duration
- **Smart shuffle** - avoids recently played tracks
- **Desktop notifications** on track change

## Installation

**Arch Linux:**
```bash
sudo pacman -S mpg123 alsa-utils ffmpeg
```

**Fedora:**
```bash
sudo dnf install mpg123 alsa-utils ffmpeg
```

**Debian**
```bash
sudo apt install mpg123 alsa-utils ffmpeg
```

**Clone and run:**
```bash
git clone https://github.com/jdanks420/danktunes.git
cd danktunes
python3 danktunes.py
```
### Creating a Shell Alias

Add `python3 /home/username/danktunes/danktunes.py` as an alias in your shell configuration to easily launch danktunes from anywhere.

## Configuration

The player uses a TOML configuration file for customization. The config file is stored at:
- `~/.config/danktunes/danktunes.toml` (standard location)
- `danktunes.toml` (in project folder for portable/development use)

### `[music]` Section

Controls where your music library is located:

- **directory**: Path to your music library (default: `~/Music`)

### `[playlist]` Section

Controls where playlists are stored:

- **directory**: Path to store M3U playlist files (default: `~/.local/share/music_player/playlists`)

### `[colors]` Section

Customize the UI color scheme:

- **header**: Color for the header text and icons (default: `bold`)
- **secondary**: Color for secondary information like speed and duration (default: `gray`)
- **selection**: Color for the currently selected item (default: `reverse`)
- **text**: Color for regular text (default: `default`)

**Available Colors:**
- **Basic**: black, red, green, yellow, blue, magenta, cyan, white
- **Bright**: bright_black (gray), bright_red, bright_green, bright_yellow, bright_blue, bright_magenta, bright_cyan, bright_white
- **Styles**: bold, dim, italic, underline, reverse, hidden

### `[ui]` Section

Control UI appearance and behavior:

- **borders**: Show decorative borders in the interface (default: `false`)
- **header_glyph**: Custom emoji/icon to display in the header (default: `😎`)
  - Can be any Unicode character, emoji, or text symbol
  - Example alternatives: `🎵`, `♪`, `🎧`, `▶`, `◈`

### `[notifications]` Section

Desktop notification settings:

- **enabled**: Send desktop notifications when tracks change (default: `false`)
- **glyph**: Icon to show in notifications (default: `🎵`)

### `[album_art]` Section

Album art display settings:

- **enabled**: Show album art in the player (default: `true`)
- **width**: Width of album art display in characters (default: `20`)

### Example Configuration

```toml
[music]
directory = "~/Music"

[playlist]
directory = "~/.config/danktunes/playlists"

[colors]
header = "cyan"
secondary = "yellow"
selection = "reverse"
text = "default"

[ui]
borders = false
header_glyph = "🎧"

[notifications]
enabled = true
glyph = "🎵"

[album_art]
enabled = true
width = 20
```

## Controls

Press `?` anytime to view all keyboard shortcuts in the help overlay.

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
| +/- | Volume up/down |
| r | Cycle repeat: off → all → one |
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
| **Overlays** | |
| ? | Toggle help screen |
| / | Search library |
| o | Toggle album art view |
| Tab | Toggle search mode (flat/recursive) |
| **Other** | |
| q | Quit |

## Overlays

danktunes features several overlay views that provide focused information:

### Help Overlay (?)

Shows all available keyboard shortcuts organized by category.

### Playlist Overlay (v)

Displays the current playlist with track numbers and titles. Use arrow keys or j/k to navigate, Enter to play, Space to toggle play/pause, x to remove tracks.

### Search Overlay (/)

Search through your music library by filename or path. Press Tab to toggle between:
- **Flat search**: Searches current view only
- **Recursive search**: Searches entire music directory tree

Use Backspace to delete characters, Enter to play selected result, Escape to close.

### Album Art Overlay (o)

Displays album art (if available) along with track info and a progress bar. Supports iTerm2, Kitty, and Ueberzug protocols.

Only one overlay can be active at a time - opening a new one closes the previous.

## Playlist View

Press `v` to toggle playlist view:

| Key | Action |
|-----|--------|
| ↑/↓ or j/k | Scroll through playlist |
| Enter | Play selected track |
| x | Remove selected track |
| Space | Play/Pause |
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
