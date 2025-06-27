#!/bin/bash

# Enhanced HTML gallery generator with metadata extraction
# Extracts file metadata and creates interactive gallery with GPS entry

echo "Scanning for thumbnail files and extracting metadata..."

# Find all thumbnail files in current directory
thumbnails=($(ls *-thumbnail.png 2>/dev/null | sort))

if [ ${#thumbnails[@]} -eq 0 ]; then
    echo "No thumbnail files found (*-thumbnail.png)"
    exit 1
fi

echo "Found ${#thumbnails[@]} thumbnail files"

# Function to extract metadata from WAV file
extract_metadata() {
    local wav_file="$1"
    local metadata_json=""
    
    if [ -f "$wav_file" ]; then
        # Extract metadata using ffprobe
        metadata_json=$(ffprobe -v quiet -print_format json -show_format "$wav_file" 2>/dev/null)
        
        # Extract specific fields
        local comment=$(echo "$metadata_json" | jq -r '.format.tags.comment // ""' 2>/dev/null)
        local artist=$(echo "$metadata_json" | jq -r '.format.tags.artist // ""' 2>/dev/null)
        local duration=$(echo "$metadata_json" | jq -r '.format.duration // ""' 2>/dev/null)
        local size=$(echo "$metadata_json" | jq -r '.format.size // ""' 2>/dev/null)
        local bitrate=$(echo "$metadata_json" | jq -r '.format.bit_rate // ""' 2>/dev/null)
        
        # Format duration if available
        if [ -n "$duration" ] && [ "$duration" != "null" ] && [ "$duration" != "" ]; then
            # Use awk for more reliable floating point arithmetic
            local minutes=$(echo "$duration" | awk '{print int($1/60)}')
            local seconds=$(echo "$duration" | awk '{printf "%.1f", $1%60}')
            duration="${minutes}m ${seconds}s"
        fi
        
        # Format file size if available
        if [ -n "$size" ] && [ "$size" != "null" ]; then
            size=$(numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "$size bytes")
        fi
        
        # Format bitrate if available
        if [ -n "$bitrate" ] && [ "$bitrate" != "null" ] && [ "$bitrate" != "" ]; then
            bitrate="$(echo "$bitrate" | awk '{printf "%.0fk", $1/1000}')"
        fi
        
        echo "$comment|$artist|$duration|$size|$bitrate"
    else
        echo "||||"
    fi
}

# Delete old index.html if it exists
[ -f "index.html" ] && rm index.html

# Start HTML document
cat > index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AudioMoth Spectrogram Gallery - Enhanced</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
            color: white;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .controls {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
        }
        
        .search-box {
            flex: 1;
            min-width: 250px;
            max-width: 400px;
            position: relative;
        }
        
        .search-box input {
            width: 100%;
            padding: 12px 40px 12px 15px;
            border: none;
            border-radius: 25px;
            background: rgba(255,255,255,0.9);
            font-size: 14px;
            outline: none;
        }
        
        .search-icon {
            position: absolute;
            right: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: #666;
        }
        
        .filter-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            padding: 8px 16px;
            border: none;
            border-radius: 20px;
            background: rgba(255,255,255,0.2);
            color: white;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 14px;
        }
        
        .filter-btn:hover,
        .filter-btn.active {
            background: rgba(255,255,255,0.3);
            transform: translateY(-2px);
        }
        
        .stats {
            text-align: center;
            color: white;
            margin-bottom: 20px;
            opacity: 0.8;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 25px;
        }
        
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.2);
        }
        
        .card-media {
            position: relative;
            cursor: pointer;
            overflow: hidden;
        }
        
        .thumbnail {
            width: 100%;
            height: 200px;
            object-fit: cover;
            transition: transform 0.3s ease;
        }
        
        .card:hover .thumbnail {
            transform: scale(1.05);
        }
        
        .play-overlay {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.7);
            color: white;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .card:hover .play-overlay {
            opacity: 1;
        }
        
        .card-content {
            padding: 20px;
        }
        
        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: #333;
            margin-bottom: 12px;
            word-break: break-all;
        }
        
        .metadata-grid {
            display: grid;
            gap: 8px;
            margin-bottom: 15px;
        }
        
        .metadata-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
        }
        
        .metadata-label {
            color: #666;
            font-weight: 500;
        }
        
        .metadata-value {
            color: #333;
            font-family: monospace;
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 4px;
        }
        
        .metadata-comment {
            background: #e3f2fd;
            padding: 8px;
            border-radius: 6px;
            font-size: 12px;
            color: #1565c0;
            margin-bottom: 10px;
            word-break: break-word;
        }
        
        .gps-section {
            border-top: 1px solid #eee;
            padding-top: 15px;
        }
        
        .gps-input {
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
        }
        
        .gps-input input {
            flex: 1;
            padding: 6px 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 12px;
        }
        
        .gps-buttons {
            display: flex;
            gap: 6px;
        }
        
        .btn-small {
            padding: 4px 8px;
            border: none;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .btn-save {
            background: #4caf50;
            color: white;
        }
        
        .btn-map {
            background: #2196f3;
            color: white;
        }
        
        .btn-clear {
            background: #f44336;
            color: white;
        }
        
        .btn-small:hover {
            transform: translateY(-1px);
            opacity: 0.9;
        }
        
        .gps-display {
            font-size: 11px;
            color: #666;
            margin-top: 5px;
        }
        
        /* Lightbox styles */
        .lightbox {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .lightbox.active {
            display: flex;
        }
        
        .lightbox-content {
            max-width: 95%;
            max-height: 95%;
            position: relative;
        }
        
        .lightbox video {
            max-width: 100%;
            max-height: 80vh;
            border-radius: 10px;
        }
        
        .lightbox-close {
            position: absolute;
            top: -50px;
            right: 0;
            color: white;
            font-size: 40px;
            cursor: pointer;
            background: none;
            border: none;
            transition: opacity 0.3s ease;
        }
        
        .lightbox-close:hover {
            opacity: 0.7;
        }
        
        .lightbox-info {
            color: white;
            text-align: center;
            margin-top: 15px;
            background: rgba(0,0,0,0.5);
            padding: 10px;
            border-radius: 8px;
        }
        
        .no-results {
            text-align: center;
            color: white;
            font-size: 18px;
            margin-top: 50px;
            opacity: 0.7;
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
                gap: 20px;
            }
            
            .controls {
                flex-direction: column;
                align-items: stretch;
            }
            
            .search-box {
                max-width: none;
            }
            
            .filter-buttons {
                justify-content: center;
            }
            
            .header h1 {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎵 AudioMoth Spectrogram Gallery</h1>
            <p>Interactive gallery with metadata extraction and GPS tagging</p>
        </div>
        
        <div class="controls">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Search by filename, comment, or device...">
                <span class="search-icon">🔍</span>
            </div>
            <div class="filter-buttons">
                <button class="filter-btn active" data-filter="all">All</button>
                <button class="filter-btn" data-filter="has-comment">With Comments</button>
                <button class="filter-btn" data-filter="has-gps">With GPS</button>
                <button class="filter-btn" data-filter="long">Long Recordings</button>
            </div>
        </div>
        
        <div class="stats" id="stats">
            Loading recordings...
        </div>
        
        <div class="grid" id="grid">
EOF

# Generate cards for each thumbnail
echo "Extracting metadata from WAV files..."
for thumbnail in "${thumbnails[@]}"; do
    # Extract base name (remove -thumbnail.png)
    basename=${thumbnail%-thumbnail.png}
    
    # Look for corresponding WAV file
    wav_file=""
    for ext in .WAV .wav; do
        if [ -f "${basename}${ext}" ]; then
            wav_file="${basename}${ext}"
            break
        fi
    done
    
    # Extract metadata
    if [ -n "$wav_file" ]; then
        metadata_info=$(extract_metadata "$wav_file")
        IFS='|' read -r comment artist duration size bitrate <<< "$metadata_info"
        echo "  Processed: $basename"
    else
        comment=""
        artist=""
        duration=""
        size=""
        bitrate=""
        echo "  Warning: No WAV file found for $basename"
    fi
    
    # Check if corresponding video exists
    video_file="${basename}.mp4"
    has_video="false"
    if [ -f "$video_file" ]; then
        has_video="true"
    fi
    
    # Generate card HTML
    cat >> index.html << EOF
            <div class="card" data-filename="$basename" data-comment="$comment" data-artist="$artist" data-duration="$duration">
                <div class="card-media" onclick="openLightbox('$video_file', '$basename', '$has_video')">
                    <img src="$thumbnail" alt="$basename" class="thumbnail">
EOF

    if [ "$has_video" == "true" ]; then
        echo "                    <div class=\"play-overlay\">▶</div>" >> index.html
    fi

    cat >> index.html << EOF
                </div>
                <div class="card-content">
                    <div class="card-title">$basename</div>
EOF

    # Add comment if exists
    if [ -n "$comment" ] && [ "$comment" != "null" ]; then
        echo "                    <div class=\"metadata-comment\">📝 $comment</div>" >> index.html
    fi

    # Add metadata grid
    echo "                    <div class=\"metadata-grid\">" >> index.html
    
    if [ -n "$duration" ] && [ "$duration" != "null" ]; then
        echo "                        <div class=\"metadata-item\"><span class=\"metadata-label\">Duration:</span><span class=\"metadata-value\">$duration</span></div>" >> index.html
    fi
    
    if [ -n "$size" ] && [ "$size" != "null" ]; then
        echo "                        <div class=\"metadata-item\"><span class=\"metadata-label\">Size:</span><span class=\"metadata-value\">$size</span></div>" >> index.html
    fi
    
    if [ -n "$bitrate" ] && [ "$bitrate" != "null" ]; then
        echo "                        <div class=\"metadata-item\"><span class=\"metadata-label\">Bitrate:</span><span class=\"metadata-value\">${bitrate}bps</span></div>" >> index.html
    fi
    
    if [ -n "$artist" ] && [ "$artist" != "null" ]; then
        echo "                        <div class=\"metadata-item\"><span class=\"metadata-label\">Device:</span><span class=\"metadata-value\">$artist</span></div>" >> index.html
    fi

    # Add GPS section
    cat >> index.html << EOF
                    </div>
                    <div class="gps-section">
                        <div class="gps-input">
                            <input type="text" placeholder="Latitude" class="gps-lat" data-file="$basename">
                            <input type="text" placeholder="Longitude" class="gps-lng" data-file="$basename">
                        </div>
                        <div class="gps-buttons">
                            <button class="btn-small btn-save" onclick="saveGPS('$basename')">Save</button>
                            <button class="btn-small btn-map" onclick="openMap('$basename')">Map</button>
                            <button class="btn-small btn-clear" onclick="clearGPS('$basename')">Clear</button>
                        </div>
                        <div class="gps-display" id="gps-display-$basename"></div>
                    </div>
                </div>
            </div>
EOF
done

# Close HTML and add JavaScript
cat >> index.html << 'EOF'
        </div>
        
        <div class="no-results" id="noResults" style="display: none;">
            No recordings match your search criteria
        </div>
    </div>
    
    <!-- Lightbox -->
    <div id="lightbox" class="lightbox" onclick="closeLightbox()">
        <div class="lightbox-content" onclick="event.stopPropagation()">
            <button class="lightbox-close" onclick="closeLightbox()">&times;</button>
            <video id="lightbox-video" controls>
                <source id="lightbox-source" src="" type="video/mp4">
                Your browser does not support the video tag.
            </video>
            <div class="lightbox-info" id="lightbox-info"></div>
        </div>
    </div>
    
    <script>
        // GPS data storage
        let gpsData = JSON.parse(localStorage.getItem('audiomoth-gps') || '{}');
        
        // Initialize page
        document.addEventListener('DOMContentLoaded', function() {
            loadGPSData();
            updateStats();
            setupSearch();
            setupFilters();
        });
        
        // Load saved GPS data
        function loadGPSData() {
            Object.keys(gpsData).forEach(filename => {
                const data = gpsData[filename];
                const latInput = document.querySelector(`.gps-lat[data-file="${filename}"]`);
                const lngInput = document.querySelector(`.gps-lng[data-file="${filename}"]`);
                const display = document.getElementById(`gps-display-${filename}`);
                
                if (latInput && lngInput && display) {
                    latInput.value = data.lat || '';
                    lngInput.value = data.lng || '';
                    updateGPSDisplay(filename);
                }
            });
        }
        
        // Save GPS coordinates
        function saveGPS(filename) {
            const latInput = document.querySelector(`.gps-lat[data-file="${filename}"]`);
            const lngInput = document.querySelector(`.gps-lng[data-file="${filename}"]`);
            
            const lat = latInput.value.trim();
            const lng = lngInput.value.trim();
            
            if (lat && lng) {
                if (isValidCoordinate(lat, lng)) {
                    gpsData[filename] = { lat: lat, lng: lng };
                    localStorage.setItem('audiomoth-gps', JSON.stringify(gpsData));
                    updateGPSDisplay(filename);
                    updateStats();
                    
                    // Visual feedback
                    const btn = event.target;
                    const originalText = btn.textContent;
                    btn.textContent = '✓ Saved';
                    btn.style.background = '#4caf50';
                    setTimeout(() => {
                        btn.textContent = originalText;
                        btn.style.background = '';
                    }, 1000);
                } else {
                    alert('Please enter valid coordinates.\nLatitude: -90 to 90\nLongitude: -180 to 180');
                }
            } else {
                alert('Please enter both latitude and longitude');
            }
        }
        
        // Validate coordinates
        function isValidCoordinate(lat, lng) {
            const latitude = parseFloat(lat);
            const longitude = parseFloat(lng);
            return !isNaN(latitude) && !isNaN(longitude) && 
                   latitude >= -90 && latitude <= 90 && 
                   longitude >= -180 && longitude <= 180;
        }
        
        // Clear GPS data
        function clearGPS(filename) {
            delete gpsData[filename];
            localStorage.setItem('audiomoth-gps', JSON.stringify(gpsData));
            
            const latInput = document.querySelector(`.gps-lat[data-file="${filename}"]`);
            const lngInput = document.querySelector(`.gps-lng[data-file="${filename}"]`);
            
            latInput.value = '';
            lngInput.value = '';
            updateGPSDisplay(filename);
            updateStats();
        }
        
        // Update GPS display
        function updateGPSDisplay(filename) {
            const display = document.getElementById(`gps-display-${filename}`);
            const data = gpsData[filename];
            
            if (data && display) {
                display.innerHTML = `📍 ${data.lat}, ${data.lng}`;
                display.style.color = '#2196f3';
            } else if (display) {
                display.innerHTML = 'No GPS coordinates set';
                display.style.color = '#999';
            }
        }
        
        // Open in maps
        function openMap(filename) {
            const data = gpsData[filename];
            if (data) {
                const url = `https://www.google.com/maps?q=${data.lat},${data.lng}`;
                window.open(url, '_blank');
            } else {
                alert('No GPS coordinates saved for this recording');
            }
        }
        
        // Update statistics
        function updateStats() {
            const cards = document.querySelectorAll('.card');
            const withGPS = Object.keys(gpsData).length;
            const withComments = document.querySelectorAll('.metadata-comment').length;
            
            document.getElementById('stats').textContent = 
                `${cards.length} recordings • ${withComments} with comments • ${withGPS} with GPS coordinates`;
        }
        
        // Search functionality
        function setupSearch() {
            const searchInput = document.getElementById('searchInput');
            searchInput.addEventListener('input', filterCards);
        }
        
        // Filter functionality
        function setupFilters() {
            const filterBtns = document.querySelectorAll('.filter-btn');
            filterBtns.forEach(btn => {
                btn.addEventListener('click', function() {
                    filterBtns.forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    filterCards();
                });
            });
        }
        
        // Filter cards based on search and active filter
        function filterCards() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const activeFilter = document.querySelector('.filter-btn.active').dataset.filter;
            const cards = document.querySelectorAll('.card');
            let visibleCount = 0;
            
            cards.forEach(card => {
                const filename = card.dataset.filename.toLowerCase();
                const comment = (card.dataset.comment || '').toLowerCase();
                const artist = (card.dataset.artist || '').toLowerCase();
                const duration = card.dataset.duration || '';
                
                // Text search
                const matchesSearch = !searchTerm || 
                    filename.includes(searchTerm) || 
                    comment.includes(searchTerm) || 
                    artist.includes(searchTerm);
                
                // Filter criteria
                let matchesFilter = true;
                switch(activeFilter) {
                    case 'has-comment':
                        matchesFilter = card.querySelector('.metadata-comment') !== null;
                        break;
                    case 'has-gps':
                        matchesFilter = gpsData[card.dataset.filename] !== undefined;
                        break;
                    case 'long':
                        const durationMatch = duration.match(/(\d+)m/);
                        matchesFilter = durationMatch && parseInt(durationMatch[1]) > 5;
                        break;
                }
                
                if (matchesSearch && matchesFilter) {
                    card.style.display = '';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });
            
            document.getElementById('noResults').style.display = visibleCount === 0 ? 'block' : 'none';
        }
        
        // Lightbox functionality
        function openLightbox(videoSrc, filename, hasVideo) {
            if (hasVideo === 'false') {
                alert('Video file not found for this recording');
                return;
            }
            
            const lightbox = document.getElementById('lightbox');
            const video = document.getElementById('lightbox-video');
            const source = document.getElementById('lightbox-source');
            const info = document.getElementById('lightbox-info');
            
            source.src = videoSrc;
            video.load();
            
            // Build info display
            const gps = gpsData[filename];
            const gpsText = gps ? `📍 ${gps.lat}, ${gps.lng}` : 'No GPS data';
            info.innerHTML = `
                <strong>${filename}</strong><br>
                ${gpsText}
            `;
            
            lightbox.classList.add('active');
        }
        
        function closeLightbox() {
            const lightbox = document.getElementById('lightbox');
            const video = document.getElementById('lightbox-video');
            
            lightbox.classList.remove('active');
            video.pause();
            video.currentTime = 0;
        }
        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeLightbox();
            }
        });
        
        // Auto-save GPS data as user types
        document.addEventListener('input', function(e) {
            if (e.target.classList.contains('gps-lat') || e.target.classList.contains('gps-lng')) {
                const filename = e.target.dataset.file;
                const latInput = document.querySelector(`.gps-lat[data-file="${filename}"]`);
                const lngInput = document.querySelector(`.gps-lng[data-file="${filename}"]`);
                
                // Auto-save if both fields have valid data
                if (latInput.value && lngInput.value && 
                    isValidCoordinate(latInput.value, lngInput.value)) {
                    setTimeout(() => saveGPS(filename), 1000);
                }
            }
        });
    </script>
</body>
</html>
EOF

echo "Generated enhanced index.html with:"
echo "  ✓ Metadata extraction from WAV files"
echo "  ✓ Interactive GPS coordinate entry"
echo "  ✓ Search and filtering capabilities"
echo "  ✓ Modern responsive design"
echo "  ✓ Local storage for GPS data"
echo "  ✓ Google Maps integration"
echo "  ✓ ${#thumbnails[@]} audio recordings processed"