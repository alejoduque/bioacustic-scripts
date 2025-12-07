#!/bin/bash
# Short script to split videos by filesize using ffmpeg by LukeLR

# Trap Ctrl+C and cleanup
trap 'echo -e "\n\nInterrupted by user. Exiting..."; exit 130' INT TERM

# Function to convert size notation to bytes
convert_to_bytes() {
    local size="$1"
    local number="${size%[MmGgKk]*}"
    local unit="${size#$number}"
    
    case "${unit^^}" in
        M)
            echo $((number * 1024 * 1024))
            ;;
        G)
            echo $((number * 1024 * 1024 * 1024))
            ;;
        K)
            echo $((number * 1024))
            ;;
        *)
            echo "$number"
            ;;
    esac
}

# Default parameters
DEFAULT_SCALE="scale=1080:-1"

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo 'Illegal number of parameters. Needs 2-3 parameters:'
    echo 'Usage:'
    echo './split-video.sh FILE SIZELIMIT [SCALE]'
    echo 
    echo 'Parameters:'
    echo '    - FILE:        Name of the video file to split'
    echo '    - SIZELIMIT:   Maximum file size of each part (e.g., 60M, 500M, 1G)'
    echo '    - SCALE:       Video scale filter (default: "scale=1080:-1")'
    echo
    echo 'Examples:'
    echo '    ./split-video.sh video.mp4 60M'
    echo '    ./split-video.sh video.mp4 500M "scale=720:-1"'
    exit 1
fi

FILE="$1"
SIZELIMIT_INPUT="$2"
SCALE="${3:-$DEFAULT_SCALE}"

# Convert size limit to bytes
SIZELIMIT=$(convert_to_bytes "$SIZELIMIT_INPUT")

echo "Size limit: $SIZELIMIT_INPUT ($SIZELIMIT bytes)"

# Get video information
DURATION=$(ffprobe -i "$FILE" -show_entries format=duration -v quiet -of default=noprint_wrappers=1:nokey=1)
AUDIO_BITRATE=$(ffprobe -i "$FILE" -select_streams a:0 -show_entries stream=bit_rate -v quiet -of default=noprint_wrappers=1:nokey=1)

# Set default audio bitrate if not detected
if [ -z "$AUDIO_BITRATE" ] || [ "$AUDIO_BITRATE" = "N/A" ]; then
    AUDIO_BITRATE=128000  # 128 kbps default
fi

echo "Source duration: $DURATION seconds"
echo "Audio bitrate: $((AUDIO_BITRATE / 1000)) kbps"

# Calculate chunk duration based on target filesize
# Formula: duration = (filesize_bytes * 8) / (video_bitrate + audio_bitrate)
# We'll use 80% of target size to account for overhead
TARGET_BITRATE=$(echo "($SIZELIMIT * 8 * 0.8) / $DURATION - $AUDIO_BITRATE" | bc)
CHUNK_DURATION=$(echo "$SIZELIMIT * 8 / ($TARGET_BITRATE + $AUDIO_BITRATE)" | bc)

echo "Calculated video bitrate: $((TARGET_BITRATE / 1000)) kbps"
echo "Chunk duration: $CHUNK_DURATION seconds"

# Filename of the source video (without extension)
BASENAME="${FILE%.*}"
EXTENSION="mp4"

# Current position in video
CUR_TIME=0
PART=1

echo "Starting split process... (Press Ctrl+C to cancel)"
echo

while (( $(echo "$CUR_TIME < $DURATION" | bc -l) )); do
    NEXTFILENAME="$BASENAME-$PART.$EXTENSION"
    
    echo "=== Encoding part $PART ==="
    echo "Time range: $CUR_TIME to $(echo "$CUR_TIME + $CHUNK_DURATION" | bc) seconds"
    
    # Encode with calculated bitrate
    ffmpeg -ss "$CUR_TIME" -i "$FILE" -t "$CHUNK_DURATION" \
        -c:v libx264 -b:v "$TARGET_BITRATE" -maxrate "$TARGET_BITRATE" -bufsize $((TARGET_BITRATE * 2)) \
        -c:a copy -vf "$SCALE" \
        -y "$NEXTFILENAME" 2>&1 | grep -E "time=|size="
    
    if [ ! -f "$NEXTFILENAME" ]; then
        echo "Error: Failed to create $NEXTFILENAME"
        exit 1
    fi
    
    # Get actual filesize
    FILESIZE=$(stat -f%z "$NEXTFILENAME" 2>/dev/null || stat -c%s "$NEXTFILENAME" 2>/dev/null)
    FILESIZE_MB=$(echo "scale=2; $FILESIZE / 1024 / 1024" | bc)
    
    echo "✓ Created: $NEXTFILENAME (${FILESIZE_MB}MB)"
    echo
    
    CUR_TIME=$(echo "$CUR_TIME + $CHUNK_DURATION" | bc)
    PART=$((PART + 1))
done

echo "=== Split completed ==="
echo "Total parts created: $((PART - 1))"
