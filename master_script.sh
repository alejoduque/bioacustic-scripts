#!/bin/bash

# Master AudioMoth Processing Script - IMPROVED VERSION
# Processes YYYYMMDD_HHMMSS.WAV files to create spectrograms, movies, and HTML table
# Features: Larger thumbnails, working video links, minimalistic CSS

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Check if any arguments were provided
if [ $# -eq 0 ]; then
    print_error "No input files provided!"
    echo "Usage: $0 /path/to/files/*.WAV"
    echo "Example: $0 /run/media/adj/1680-9036/*.WAV"
    echo ""
    echo "This script will process AudioMoth WAV files and create:"
    echo "  • Spectrogram thumbnails (256x144px)"
    echo "  • Spectrogram movies (MP4 format)"
    echo "  • Interactive HTML gallery with lightbox video viewer"
    exit 1
fi

# Check if required scripts exist
required_scripts=("make-spectrogram-thumbnail-fixed.sh" "make-spectrogram-movie-fixed.sh" "make-html-lightbox-table-fixed.sh")
missing_scripts=()

for script in "${required_scripts[@]}"; do
    if [[ ! -f "$script" ]]; then
        missing_scripts+=("$script")
    fi
done

if [[ ${#missing_scripts[@]} -gt 0 ]]; then
    print_error "Missing required scripts:"
    for script in "${missing_scripts[@]}"; do
        echo "  - $script"
    done
    echo ""
    echo "Please make sure all the processing scripts are in the current directory and executable:"
    echo "  chmod +x make-spectrogram-thumbnail-fixed.sh"
    echo "  chmod +x make-spectrogram-movie-fixed.sh" 
    echo "  chmod +x make-html-lightbox-table-fixed.sh"
    exit 1
fi

# Count input files
file_count=0
valid_files=()
for file in "$@"; do
    if [[ -f "$file" ]]; then
        # Check if it's a WAV file
        if [[ "$file" == *.WAV ]] || [[ "$file" == *.wav ]]; then
            ((file_count++))
            valid_files+=("$file")
        else
            print_warning "Skipping non-WAV file: $file"
        fi
    else
        print_warning "File not found: $file"
    fi
done

if [[ $file_count -eq 0 ]]; then
    print_error "No valid WAV files found!"
    exit 1
fi

print_header "AudioMoth Processing Pipeline - Enhanced Version"
echo "Processing $file_count WAV files..."
print_info "Improvements in this version:"
echo "  • Thumbnails are now 256x144px (double the original size)"
echo "  • Filenames displayed below each thumbnail"
echo "  • Fixed video lightbox functionality"
echo "  • Clean, minimalistic CSS design"
echo "  • Mobile-responsive layout"
echo ""

# Show sample of files being processed
echo "Sample files to process:"
for i in "${!valid_files[@]}"; do
    if [[ $i -lt 5 ]]; then
        echo "  $(basename "${valid_files[$i]}")"
    elif [[ $i -eq 5 ]]; then
        echo "  ... and $((file_count - 5)) more files"
        break
    fi
done
echo ""

# Step 1: Generate spectrogram thumbnails
print_header "Step 1: Generating Spectrogram Thumbnails"
print_info "Creating 256x144px thumbnails for web display..."
if ./make-spectrogram-thumbnail-fixed.sh "${valid_files[@]}"; then
    print_success "Spectrogram thumbnails generated successfully"
    # Count generated thumbnails
    thumbnail_count=$(ls *-thumbnail.png 2>/dev/null | wc -l)
    echo "  Generated $thumbnail_count thumbnail files"
else
    print_error "Failed to generate spectrogram thumbnails"
    exit 1
fi
echo ""

# Step 2: Generate spectrogram movies
print_header "Step 2: Generating Spectrogram Movies"
print_info "Creating MP4 videos for lightbox viewing..."
if ./make-spectrogram-movie-fixed.sh "${valid_files[@]}"; then
    print_success "Spectrogram movies generated successfully"
    # Count generated movies
    movie_count=$(ls *.mp4 2>/dev/null | wc -l)
    echo "  Generated $movie_count MP4 files"
else
    print_error "Failed to generate spectrogram movies"
    exit 1
fi
echo ""

# Step 3: Generate HTML lightbox table
print_header "Step 3: Generating HTML Lightbox Table"
print_info "Creating interactive web gallery..."
if ./make-html-lightbox-table-fixed.sh "${valid_files[@]}"; then
    print_success "HTML lightbox table generated successfully"
    echo "  Created index.html with enhanced gallery"
else
    print_error "Failed to generate HTML lightbox table"
    exit 1
fi
echo ""

# Check and report on CSS files
print_header "Checking CSS Files"
css_files=("spectrogram-table.css" "perfundo.min.css")
css_status=()

for css_file in "${css_files[@]}"; do
    if [[ -f "$css_file" ]]; then
        print_success "Found $css_file"
        css_status+=("✓")
    else
        print_warning "Missing $css_file"
        css_status+=("✗")
    fi
done

if [[ ! -f "spectrogram-table.css" ]] || [[ ! -f "perfundo.min.css" ]]; then
    echo ""
    print_warning "Some CSS files are missing. The gallery will work but styling may be basic."
    echo "To get the full enhanced experience, make sure these files are present:"
    echo "  • spectrogram-table.css (main gallery styling)"
    echo "  • perfundo.min.css (lightbox functionality)"
fi
echo ""

# Final summary
print_header "Processing Complete! 🎉"
echo "Generated files:"
echo "  📊 Spectrogram thumbnails: *-thumbnail.png (256x144px)"
echo "  🎬 Spectrogram movies: *.mp4 (video format)"
echo "  🌐 HTML gallery: index.html (interactive table)"
echo "  🎨 CSS files: spectrogram-table.css + perfundo.min.css"
echo ""
echo "✨ NEW FEATURES:"
echo "  • Double-sized thumbnails with filenames"
echo "  • Click thumbnails to open videos in lightbox"
echo "  • Minimalistic, responsive design"
echo "  • Mobile-friendly interface"
echo ""
print_success "Open index.html in a web browser to view your enhanced spectrogram gallery!"

# Show file statistics
echo ""
echo "📈 Statistics:"
echo "  WAV files processed: $file_count"
echo "  Thumbnails created: $(ls *-thumbnail.png 2>/dev/null | wc -l)"
echo "  Videos created: $(ls *.mp4 2>/dev/null | wc -l)"
echo "  Total output files: $(($(ls *-thumbnail.png *.mp4 index.html 2>/dev/null | wc -l)))"

# Performance tip
echo ""
print_info "💡 Tip: For large datasets, consider processing files in batches to manage memory usage."