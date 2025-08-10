#!/bin/bash

# Function to show progress bar
show_progress() {
    local current=$1
    local total=$2
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((current * width / total))
    local remaining=$((width - completed))
    
    printf "\r["
    printf "%*s" $completed | tr ' ' '█'
    printf "%*s" $remaining | tr ' ' '░'
    printf "] %d%% (%d/%d)" $percentage $current $total
}

# Function to show step progress
show_step() {
    local step=$1
    local total_steps=$2
    local description=$3
    echo ""
    echo "Step $step/$total_steps: $description"
    show_progress $step $total_steps
    echo ""
}

# Check if any arguments provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 video_file [video_file2 ...]"
    exit 1
fi

for f in "$@"
do
    # Check if file exists
    if [ ! -f "$f" ]; then
        echo "Error: File '$f' not found"
        continue
    fi

    echo "Processing: $f"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Change this value to increase maximum size
    GIF_MAX_SIZE=480

    dir="$(dirname "$f")"
    name="$(basename "$f")"

    cd "$dir" || exit 1

    show_step 1 5 "Analyzing video properties"
    
    # Create temp directory
    mkdir -p .temp

    # Get video properties using multiple methods
    video_width=""
    video_height=""
    
    # Try ffprobe first (most reliable)
    if command -v ffprobe >/dev/null 2>&1; then
        video_width=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=width -of csv=s=x:p=0 "$f" 2>/dev/null)
        video_height=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=height -of csv=s=x:p=0 "$f" 2>/dev/null)
        echo "✓ Using ffprobe for dimensions"
    fi
    
    # If ffprobe failed, try mplayer
    if [ -z "$video_width" ] || [ -z "$video_height" ]; then
        echo "Trying mplayer for dimensions..."
        video_properties=$(/opt/homebrew/bin/mplayer -really-quiet -ao null -vo null -identify -frames 0 "$f" 2>/dev/null)
        
        video_width=$(echo "$video_properties" | grep "ID_VIDEO_WIDTH" | head -1 | cut -d'=' -f2)
        video_height=$(echo "$video_properties" | grep "ID_VIDEO_HEIGHT" | head -1 | cut -d'=' -f2)
        echo "✓ Using mplayer for dimensions"
    fi
    
    # If still no dimensions, try ffmpeg
    if [ -z "$video_width" ] || [ -z "$video_height" ]; then
        echo "Trying ffmpeg for dimensions..."
        if command -v ffmpeg >/dev/null 2>&1; then
            video_info=$(ffmpeg -i "$f" 2>&1 | grep "Video:")
            video_width=$(echo "$video_info" | sed -n 's/.* \([0-9]*\)x\([0-9]*\).*/\1/p')
            video_height=$(echo "$video_info" | sed -n 's/.* \([0-9]*\)x\([0-9]*\).*/\2/p')
            echo "✓ Using ffmpeg for dimensions"
        fi
    fi

    # Validate we got dimensions
    if [ -z "$video_width" ] || [ -z "$video_height" ] || [ "$video_width" -eq 0 ] || [ "$video_height" -eq 0 ]; then
        echo "Error: Could not determine video dimensions for $f"
        continue
    fi

    echo "Original dimensions: ${video_width}x${video_height}"

    show_step 2 5 "Calculating optimal dimensions"
    
    aspect_ratio=$(echo "$video_width $video_height" | awk '{printf "%.5f", $1/$2}')

    # Calculate final dimensions
    # Don't change dimensions if both are below GIF_MAX_SIZE
    if [ "$video_width" -lt "$GIF_MAX_SIZE" ] && [ "$video_height" -lt "$GIF_MAX_SIZE" ]; then
        final_width=$video_width
        final_height=$video_height
        echo "✓ Video already optimal size, no scaling needed"
    else
        # Shrink larger dimension to GIF_MAX_SIZE
        if [ "$video_height" -lt "$video_width" ]; then
            final_width=$GIF_MAX_SIZE
            final_height=$(echo "$final_width $aspect_ratio" | awk '{printf "%d", $1/$2}')
        else
            final_height=$GIF_MAX_SIZE
            final_width=$(echo "$final_height $aspect_ratio" | awk '{printf "%d", $1*$2}')
        fi
        echo "✓ Scaling to fit maximum size of ${GIF_MAX_SIZE}px"
    fi

    # Ensure dimensions are even numbers (required by some codecs)
    final_width=$(( (final_width + 1) / 2 * 2 ))
    final_height=$(( (final_height + 1) / 2 * 2 ))

    echo "Final dimensions: ${final_width}x${final_height}"

    show_step 3 5 "Extracting video frames"
    
    # Extract frames using mplayer
    echo "Extracting frames... (this may take a while)"
    /opt/homebrew/bin/mplayer -ao null -vo png:z=1:outdir=.temp -vf scale=$final_width:$final_height "$f" >/dev/null 2>&1

    # Check if any frames were extracted
    if [ ! "$(ls -A .temp/*.png 2>/dev/null)" ]; then
        echo "❌ Error: No frames extracted from $f"
        rm -rf .temp
        continue
    fi

    frame_count=$(ls .temp/*.png | wc -l)
    echo "✓ Extracted $frame_count frames"

    show_step 4 5 "Creating GIF from frames"
    
    # Create GIF using ImageMagick
    echo "Processing frames into GIF... (this may take a while)"
    if /opt/homebrew/bin/magick .temp/*.png +repage -fuzz 1.6% -delay 1.7 -loop 0 -layers OptimizePlus -layers OptimizeTransparency .temp.gif 2>/dev/null; then
        echo "✓ Created temporary GIF"
        
        show_step 5 5 "Optimizing final GIF"
        
        # Optimize with gifsicle
        echo "Optimizing GIF with gifsicle..."
        if /opt/homebrew/bin/gifsicle -O3 --colors 256 .temp.gif > "${name%.*}.gif"; then
            echo "✅ Successfully created: ${name%.*}.gif"
            
            # Show file size
            gif_size=$(ls -lh "${name%.*}.gif" | awk '{print $5}')
            echo "📁 Final GIF size: $gif_size"
            
            # Show completion bar
            echo ""
            show_progress 5 5
            echo ""
        else
            echo "❌ Error: Failed to optimize GIF with gifsicle"
        fi
    else
        echo "❌ Error: Failed to create GIF with ImageMagick"
    fi
    
    # Cleanup
    rm -rf .temp
    rm -f .temp.gif

    echo ""
    echo "🎉 Finished processing: $f"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

done

echo "✨ All files processed successfully! ✨"