#!/bin/bash

# Flexible Spectrogram Movie Generator
# Works with ANY WAV filename - no strict naming requirements
# Generates spectrograms for the COMPLETE duration of each file

# Variables for setting output options quickly
dynamic_range=72
highest_freq=10000
lowest_freq=0
gain_scale="log"
freq_scale="lin"
color_choice="cool"
slide_choice="scroll"

# Set variables used when generating text (customize as needed)
location_text="AudioMoth Recording"
gps_text="Location Unknown"

# Variable to store user's global overwrite choice
overwrite_choice=""

# Function to get file duration and basic info
get_file_info() {
    local file="$1"
    
    # Get duration in seconds using ffprobe
    local duration=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$file" 2>/dev/null)
    
    if [ $? -eq 0 ] && [ -n "$duration" ]; then
        # Convert to minutes and seconds for display
        local minutes=$(printf "%.0f" $(echo "$duration / 60" | bc -l 2>/dev/null || echo "0"))
        local seconds=$(printf "%.1f" $(echo "$duration % 60" | bc -l 2>/dev/null || echo "0"))
        echo "$duration|${minutes}m ${seconds}s"
    else
        echo "unknown|unknown"
    fi
}

# Function to generate a clean display name from filename
get_display_name() {
    local filename="$1"
    local basename=$(basename "$filename")
    local name_no_ext="${basename%.*}"
    
    # Try to extract date/time if it matches YYYYMMDD_HHMMSS pattern
    if [[ "$name_no_ext" =~ ^([0-9]{8})_([0-9]{6})$ ]]; then
        local date_part="${BASH_REMATCH[1]}"
        local time_part="${BASH_REMATCH[2]}"
        
        local year="${date_part:0:4}"
        local month="${date_part:4:2}" 
        local day="${date_part:6:2}"
        local hour="${time_part:0:2}"
        local minute="${time_part:2:2}"
        local second="${time_part:4:2}"
        
        # Try to format nicely
        local iso_datetime="${year}-${month}-${day} ${hour}:${minute}:${second}"
        local formatted_date=$(date -d "$iso_datetime" +"%d %B %Y at %H:%M:%S" 2>/dev/null)
        
        if [ $? -eq 0 ]; then
            echo "$formatted_date"
            return
        fi
    fi
    
    # If no date pattern or date parsing failed, just use the filename
    echo "$name_no_ext"
}

# Check if bc is available for duration calculations
if ! command -v bc &> /dev/null; then
    echo "Warning: 'bc' calculator not found. Duration calculations may be imprecise."
fi

echo "Flexible Spectrogram Movie Generator"
echo "===================================="

# Iterate through all arguments 
for file in "$@"
do
    # Get the full path for ffmpeg input
    full_path="$file"
    
    # Strip out the filename without extension
    without_path="${file##*/}"
    without_extension="${without_path%.*}"
    output_filename="${without_extension}.mp4"
    
    # Check if it's a WAV file (case insensitive)
    if [[ ! $without_path =~ \.(wav|WAV)$ ]]; then
        echo "Skipping $without_path - not a WAV file!"
        continue
    fi
    
    # Check if the input file exists and is readable
    if [ ! -f "$full_path" ] || [ ! -r "$full_path" ]; then
        echo "Skipping $without_path - file not found or not readable!"
        continue
    fi
    
    # Get file duration info
    file_info=$(get_file_info "$full_path")
    IFS='|' read -r duration duration_display <<< "$file_info"
    
    # Get display name for the video
    display_name=$(get_display_name "$file")
    
    echo ""
    echo "Processing: $without_path"
    echo "    Duration: $duration_display"
    echo "    Display name: $display_name"
    
    # Check if the output file already exists
    if [ -f "$output_filename" ]; then
        if [ "$overwrite_choice" == "Y" ]; then
            echo "    Output file exists. Overwriting (YES TO ALL)..."
        elif [ "$overwrite_choice" == "N" ]; then
            echo "    Output file exists. Skipping (NO TO ALL)..."
            continue
        else
            # Prompt the user for overwrite
            while true; do
                read -p "    Output file $output_filename exists. Overwrite? (y/n/Y/N) " ynYN
                case $ynYN in
                    [Yy]* ) 
                        if [[ "$ynYN" == "Y" ]]; then
                            overwrite_choice="Y"
                        fi
                        echo "    Overwriting..."
                        break
                        ;;
                    [Nn]* ) 
                        if [[ "$ynYN" == "N" ]]; then
                            overwrite_choice="N"
                        fi
                        echo "    Skipping..."
                        continue 2
                        ;;
                    * ) echo "    Please answer y, n, Y, or N.";;
                esac
            done
        fi
    fi

    # Generate spectrogram video for the COMPLETE file duration
    echo "    Creating spectrogram movie..."
    
    # Prepare text overlays
    full_header_text="$location_text"
    full_date_text="$display_name"
    
    # Create the spectrogram movie with better error handling
    if ffmpeg -i "$full_path" -filter_complex \
        "[0:a]showspectrum=s=996x592:legend=enable:start=$lowest_freq:stop=$highest_freq:fscale=$freq_scale:color=$color_choice:drange=$dynamic_range:scale=$gain_scale:slide=$slide_choice,
        drawtext=text='$full_header_text':x=25:y=25:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=2,
        drawtext=text='$full_date_text':x=W-tw-25:y=25:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=2,
        format=yuv420p[v]" \
        -map "[v]" -map 0:a \
        -c:v libx264 -preset medium -crf 23 \
        -c:a aac -b:a 128k \
        -movflags +faststart \
        -y "$output_filename" 2>&1; then
        
        echo "    ✓ Movie created successfully: $output_filename"
        
        # Verify the output file was actually created and has reasonable size
        if [ -f "$output_filename" ] && [ -s "$output_filename" ]; then
            file_size=$(du -h "$output_filename" | cut -f1)
            echo "    ✓ File size: $file_size"
        else
            echo "    ✗ Warning: Output file seems empty or corrupted"
        fi
    else
        echo "    ✗ Error creating movie for $without_path"
        echo "    Check if the WAV file is corrupted or in an unsupported format"
    fi
done

echo ""
echo "Spectrogram movie generation complete!"
echo "All movies process the complete duration of their source files."