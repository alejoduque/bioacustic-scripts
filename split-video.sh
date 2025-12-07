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
DEFAULT_FFMPEG_ARGS="-c:v libx264 -crf 23 -c:a copy -vf scale=1080:-1"

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo 'Illegal number of parameters. Needs 2-3 parameters:'
    echo 'Usage:'
    echo './split-video.sh FILE SIZELIMIT [FFMPEG_ARGS]'
    echo 
    echo 'Parameters:'
    echo '    - FILE:        Name of the video file to split'
    echo '    - SIZELIMIT:   Maximum file size of each part (e.g., 60M, 500M, 1G)'
    echo '    - FFMPEG_ARGS: Additional arguments to pass to each ffmpeg-call'
    echo "                   (default: \"$DEFAULT_FFMPEG_ARGS\")"
    echo
    echo 'Examples:'
    echo '    ./split-video.sh video.mp4 60M'
    echo '    ./split-video.sh video.mp4 500M "-c:v libx265 -crf 28"'
    exit 1
fi

FILE="$1"
SIZELIMIT_INPUT="$2"
FFMPEG_ARGS="${3:-$DEFAULT_FFMPEG_ARGS}"

# Convert size limit to bytes
SIZELIMIT=$(convert_to_bytes "$SIZELIMIT_INPUT")

echo "Size limit: $SIZELIMIT_INPUT ($SIZELIMIT bytes)"

# Duration of the source video
DURATION=$(ffprobe -i "$FILE" -show_entries format=duration -v quiet -of default=noprint_wrappers=1:nokey=1 | cut -d. -f1)

# Duration that has been encoded so far
CUR_DURATION=0

# Filename of the source video (without extension)
BASENAME="${FILE%.*}"

# Extension for the video parts
EXTENSION="mp4"

# Number of the current video part
i=1

# Filename of the next video part
NEXTFILENAME="$BASENAME-$i.$EXTENSION"

echo "Duration of source video: $DURATION seconds"
echo "Starting split process... (Press Ctrl+C to cancel)"
echo

# Until the duration of all partial videos has reached the duration of the source video
while [[ $CUR_DURATION -lt $DURATION ]]; do
    echo "=== Encoding part $i ==="
    echo "Command: ffmpeg -ss $CUR_DURATION -i \"$FILE\" -fs $SIZELIMIT $FFMPEG_ARGS \"$NEXTFILENAME\""
    
    # Encode next part
    ffmpeg -ss "$CUR_DURATION" -i "$FILE" -fs "$SIZELIMIT" $FFMPEG_ARGS "$NEXTFILENAME"
    
    # Check if file was created successfully
    if [ ! -f "$NEXTFILENAME" ]; then
        echo "Error: Failed to create $NEXTFILENAME"
        exit 1
    fi
    
    # Duration of the new part
    NEW_DURATION=$(ffprobe -i "$NEXTFILENAME" -show_entries format=duration -v quiet -of default=noprint_wrappers=1:nokey=1 | cut -d. -f1)
    
    # Check if we got a valid duration
    if [ -z "$NEW_DURATION" ] || [ "$NEW_DURATION" -eq 0 ]; then
        echo "Warning: Part $i has zero or invalid duration. This likely means we've reached the end."
        break
    fi
    
    # Total duration encoded so far
    CUR_DURATION=$((CUR_DURATION + NEW_DURATION))
    
    echo "Duration of $NEXTFILENAME: $NEW_DURATION seconds"
    echo "Total encoded so far: $CUR_DURATION / $DURATION seconds"
    echo
    
    # Check if we've encoded everything
    if [[ $CUR_DURATION -ge $DURATION ]]; then
        echo "✓ All parts encoded successfully!"
        break
    fi
    
    i=$((i + 1))
    NEXTFILENAME="$BASENAME-$i.$EXTENSION"
done

echo
echo "=== Split completed ==="
echo "Total parts created: $i"
echo "Total duration processed: $CUR_DURATION seconds"
