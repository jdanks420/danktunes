#!/bin/bash
# danktunes Launcher

cd "$(dirname "$0")"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if the main script exists
if [ ! -f "danktunes.py" ]; then
    echo "Error: danktunes.py not found in $(pwd)"
    exit 1
fi

# Check for required system dependencies
MISSING_DEPS=()

if ! command -v mpg123 &> /dev/null; then
    MISSING_DEPS+=("mpg123")
fi

if ! command -v ffprobe &> /dev/null; then
    MISSING_DEPS+=("ffprobe (from ffmpeg)")
fi

# Report missing dependencies
if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo "Error: Missing required dependencies:"
    printf '  %s\n' "${MISSING_DEPS[@]}"
    echo ""
    echo "Install them with:"
    if command -v apt-get &> /dev/null; then
        echo "  sudo apt-get install mpg123 ffmpeg"
    elif command -v dnf &> /dev/null; then
        echo "  sudo dnf install mpg123 ffmpeg"
    elif command -v pacman &> /dev/null; then
        echo "  sudo pacman -S mpg123 ffmpeg"
    elif command -v brew &> /dev/null; then
        echo "  brew install mpg123 ffmpeg"
    else
        echo "  Install mpg123 and ffmpeg using your package manager"
    fi
    exit 1
fi

# Set up config directory if needed
CONFIG_DIR="$HOME/.config/danktunes"
if [ ! -d "$CONFIG_DIR" ]; then
    mkdir -p "$CONFIG_DIR"
fi

# Set up playlist directory if needed
PLAYLIST_DIR="$HOME/.local/share/music_player/playlists"
if [ ! -d "$PLAYLIST_DIR" ]; then
    mkdir -p "$PLAYLIST_DIR"
fi

# Run the application
exec python3 danktunes.py "$@"