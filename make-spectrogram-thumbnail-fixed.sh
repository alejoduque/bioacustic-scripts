#!/bin/bash

# Copyright (c) 2020, lowkey digital studio
# Author: Nathan Wolek
# Usage of this file and its contents is governed by the MIT License
# Modified to work with YYYYMMDD_HHMMSS.WAV filename format
# Enhanced with overwrite protection

# BEGUN - 23 June 2020
# GOAL - generate spectrogram thumbnail image of entire .WAV file
# expected input .wav files (upper or lower case extension) produced by the AudioMoth
# expected output 2 .png files (fullsize & thumbnail) visualizing entire .WAV file

# variables for setting output options quickly
# dynamic range in dBFS, values can be between 10 to 200
dynamic_range=72
# highest frequency in Hertz
highest_freq=10000
# lowest frequency in Hertz
lowest_freq=0
# gain scale, typically switch between linear "lin" or logarithmic "log"
gain_scale="log"
# frequency scale, switch between linear "lin" or logarithmic "log"
freq_scale="lin"
# color scheme, personal favorite options are cool, fruit, fiery, green
color_choice="fruit"

# overwrite control variables
overwrite_all=false
skip_all=false

# function to prompt for overwrite decision
prompt_overwrite() {
    local filename="$1"
    
    if $overwrite_all; then
        return 0  # proceed with overwrite
    fi
    
    if $skip_all; then
        return 1  # skip this file
    fi
    
    echo "File '$filename' already exists."
    echo "Options:"
    echo "  y - Yes, overwrite this file"
    echo "  n - No, skip this file"
    echo "  Y - Yes to ALL (overwrite all existing files)"
    echo "  N - No to ALL (skip all existing files)"
    
    while true; do
        read -p "Choice [y/n/Y/N]: " choice
        case $choice in
            y)
                return 0  # overwrite this file
                ;;
            n)
                return 1  # skip this file
                ;;
            Y)
                overwrite_all=true
                return 0  # overwrite this file and all future ones
                ;;
            N)
                skip_all=true
                return 1  # skip this file and all future ones
                ;;
            *)
                echo "Please enter y, n, Y, or N"
                ;;
        esac
    done
}

# function to check if file should be processed
should_process_file() {
    local fullsize_file="$1"
    local thumbnail_file="$2"
    
    # Check if either file exists
    if [[ -f "$fullsize_file" ]] || [[ -f "$thumbnail_file" ]]; then
        local existing_files=""
        [[ -f "$fullsize_file" ]] && existing_files="$fullsize_file"
        [[ -f "$thumbnail_file" ]] && existing_files="$existing_files $thumbnail_file"
        
        if ! prompt_overwrite "$existing_files"; then
            return 1  # don't process
        fi
    fi
    
    return 0  # process the file
}

# iterate through all arguments
for file in "$@"
do
	# strip out the filename without path
	without_path="${file##*/}"
	
	# use conditionals to make wav extension case insensitive
	if [[ $without_path == *.wav ]] || [[ $without_path == *.WAV ]]; then
		
		# strip the extension
		without_extension="${without_path%.*}"
		
		# define output filenames
		fullsize_file="$without_extension-fullsize.png"
		thumbnail_file="$without_extension-thumbnail.png"
		
		echo "Processing: $without_path"
		echo "Output base name: $without_extension"
		
		# check if files should be processed (handles overwrite logic)
		if ! should_process_file "$fullsize_file" "$thumbnail_file"; then
			echo "Skipped $without_path - files exist and user chose not to overwrite"
			echo ""
			continue
		fi
		
		# generate the initial .png spectrogram output from ffmpeg
		# dimension here are for spectrogram only, extra padding will result in 1280 x 720 image
		echo "Making fullsize spectrogram for $without_path..."
		ffmpeg -i "$file" -lavfi showspectrumpic=s=1280x720:legend=disable:start=$lowest_freq:stop=$highest_freq:fscale=$freq_scale:color=$color_choice:drange=$dynamic_range:scale=$gain_scale -v quiet "$fullsize_file"
	
		if [[ $? -eq 0 ]]; then
			echo "✓ Fullsize spectrogram created: $fullsize_file"
		else
			echo "✗ Error creating fullsize spectrogram for $without_path"
			continue
		fi

		# resize to thumbnail dimensions 128 x 72
		echo "Making thumbnail spectrogram for $without_path..."
		ffmpeg -i "$fullsize_file" -vf scale=128:72 -v quiet "$thumbnail_file"
		
		if [[ $? -eq 0 ]]; then
			echo "✓ Thumbnail created: $thumbnail_file"
		else
			echo "✗ Error creating thumbnail for $without_path"
		fi
		
		# to delete the fullsize version, uncomment the next two lines
		# echo "deleting fullsize spectrogram for $without_path..."
		# rm "$fullsize_file"
	
	else
		echo "Skipped $without_path - not a wav file!"
	fi
	
	echo ""
done

echo "Spectrogram generation complete!"