# AudioMoth Metadata Processor

A comprehensive tool for processing and visualizing AudioMoth WAV file metadata with an integrated web-based player and interactive charts.

```
 _______________
|  [=]      [=] |
|   AudioMoth   |
|_______________|
```

## Features

- Extract metadata from AudioMoth WAV files (datetime, temperature, battery, location)
- Generate interactive HTML reports with sortable tables
- Integrated audio player with full metadata display
- Interactive temperature and recording analysis charts
- Filter recordings by location and search by filename
- Local HTTP server for audio playback

## Requirements

- Python 3.6 or higher
- Internet connection (for initial setup and chart libraries)

## Installation

### macOS / Linux

1. Download the scripts to your working directory:
   - `audiomoth_links_graphs.sh`
   - `audiomoth_server.py`

2. Make the main script executable:
   ```bash
   chmod +x audiomoth_links_graphs.sh
   ```

3. The script will automatically:
   - Detect Python 3
   - Create a virtual environment on first run
   - Install the required `metamoth` library

### Windows

Use Git Bash or WSL (Windows Subsystem for Linux) and follow the macOS/Linux instructions.

## Usage

### Step 1: Generate the HTML Report

Process all WAV files in a directory:

```bash
./audiomoth_links_graphs.sh /path/to/recordings
```

Process current directory:

```bash
./audiomoth_links_graphs.sh .
```

Specify custom output file:

```bash
./audiomoth_links_graphs.sh /path/to/recordings custom_report.html
```

The script will:
- Recursively find all .WAV files
- Extract metadata from each file
- Generate an HTML report with interactive features

### Step 2: Start the Local Server

Navigate to the directory containing the generated report:

```bash
cd /path/to/recordings
python3 audiomoth_server.py
```

Or specify the directory:

```bash
python3 audiomoth_server.py /path/to/recordings
```

The server will:
- Start on port 8000 by default
- Automatically open your browser
- Display the report at `http://localhost:8000/audiomoth_reporte.html`

Custom port:

```bash
python3 audiomoth_server.py --port 8080
```

### Step 3: Explore Your Data

In the web interface you can:

- **Play audio files**: Click "Play" button to open integrated player
- **View metadata**: See temperature, location, datetime, battery level
- **Filter recordings**: Search by filename or filter by location
- **Analyze data**: View interactive charts:
  - Temperature vs. Time of Day
  - Temperature by Location
  - Recording Distribution by Hour
- **Sort table**: Click column headers to sort
- **Copy file paths**: Use the modal player to copy paths to clipboard

## Directory Structure

The script works best with organized directory structures:

```
AudioMothRecs/
├── Epoca lluvias/
│   ├── Bosque de galería/
│   │   ├── 20240727_183300.WAV
│   │   └── 20240727_190000.WAV
│   └── Pastos limpios/
│       └── 20240728_060000.WAV
└── Epoca seca/
    └── Vegetación secundaria/
        └── 20250118_042100.WAV
```

The tool automatically extracts:
- Site information from folder names
- Season (rainy/dry) from path
- Land cover type from parent folder

## Optional Configuration

Edit the Python script to add GPS coordinates manually:

```python
DEPLOYMENT_INFO = {
    "24E1440163ED0711": {
        "latitud": 4.7110,
        "longitud": -74.0721,
        "fecha_instalacion": "2024-07-27"
    }
}

LOCATION_COORDS = {
    "Bosque de galería y-o ripario": {
        "latitud": 4.7110, 
        "longitud": -74.0721
    }
}
```

## Troubleshooting

### Python not found (macOS)

Install Python 3 via Homebrew:

```bash
brew install python3
```

### Port already in use

Use a different port:

```bash
python3 audiomoth_server.py --port 8080
```

### Audio files won't play

Ensure you're using the local server (not opening HTML file directly). Modern browsers block `file://` URLs for security.

### Charts not displaying

Check browser console (F12) for errors. Verify internet connection for Plotly CDN.

### Corrupted virtual environment

Remove and regenerate:

```bash
rm -rf ~/.audiomoth_venv
./audiomoth_links_graphs.sh .
```

## File Output

The script generates:

- `audiomoth_reporte.html` - Interactive HTML report with:
  - Summary statistics
  - Sortable and filterable data table
  - Interactive charts (Plotly.js)
  - Integrated audio player modal
  - Responsive design for mobile/desktop

## Keyboard Shortcuts

In the web interface:

- `ESC` - Close audio player modal
- Click outside modal - Close modal
- Column headers - Sort table

## Technical Details

**Metadata Extraction**: Uses `metamoth` library to parse AudioMoth comment chunks from WAV files.

**Audio Playback**: Local HTTP server serves files with proper MIME types and CORS headers.

**Charts**: Plotly.js for interactive visualizations (temperature trends, recording patterns).

**No External Dependencies in Browser**: All data embedded in HTML file.

## License

This tool is provided as-is for research and conservation purposes.

## Credits

- `metamoth` library for metadata parsing
- Plotly.js for interactive charts
- AudioMoth hardware by Open Acoustic Devices
