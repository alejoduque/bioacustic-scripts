# Bioacoustic Scripts

A toolkit for processing, analyzing, and visualizing AudioMoth field recordings. Includes spectral analysis tools, spectrogram generators, and an intelligent acoustic event detector built on deep ecology principles.

**Live gallery:** https://etc.altred.xyz/staticbioacustics/index.html

---

## Bioacoustic Event Detector

The centerpiece of this toolkit. An intelligent acoustic event detection system that analyzes the frequency spectrum of AudioMoth WAV recordings over time, identifies meaningful spectral shifts (species transitions, new vocalizations, weather changes), and produces clips only around those events — each with a spectrogram video, ecological classification, OSC output for modular synthesis, and a phenological calendar.

### Philosophy: Parliament of the Living

The classification framework draws from **deep ecology** and the concept of a **parliament of the living**: all acoustic participants — biological, geological, and human — have inherent ecological value and are cataloged by their role in the soundscape, not by human utility. Every detected event is a "voice" in this parliament, and the system measures acoustic democracy through Shannon entropy of role distribution.

### Architecture

A Python package (`bioacoustic_detector/`) with a bash wrapper (`detect_events.sh`) following the project convention. Dependencies: numpy, scipy, soundfile, metamoth, python-osc.

```
bioacoustic_detector/
  __init__.py          # Package init
  config.py            # All tunable parameters
  spectral.py          # STFT, spectral flux, centroid, flatness, band energies
  detector.py          # Adaptive-threshold event detection
  classifier.py        # Deep ecology taxonomy & classification
  indices.py           # Ecoacoustic indices (ACI, BIO, NDSI, ADI, AEI)
  clipper.py           # WAV clip extraction with pre/post-roll
  video.py             # ffmpeg spectrogram MP4 generation
  metadata.py          # AudioMoth metadata via metamoth + path-based habitat/season
  report.py            # HTML report with Plotly.js
  phenology.py         # Phenological calendar from cross-recording acoustic patterns
  osc_output.py        # OSC message generation for Eurorack, ILDA, SuperCollider
  cli.py               # CLI entry point
```

### Quick Start

```bash
# Single file
./detect_events.sh path/to/recording.WAV

# Entire directory (recursive)
./detect_events.sh path/to/recordings/

# With phenological calendar (requires multiple recordings)
./detect_events.sh path/to/recordings/ --phenology

# JSON-only analysis (no clips, no video)
./detect_events.sh path/to/recording.WAV --json-only

# Custom sensitivity
./detect_events.sh path/to/recording.WAV --threshold 1.5 --pre-roll 30
```

The bash wrapper automatically creates a Python virtual environment at `~/.bioacoustic_detector_venv` and installs all dependencies on first run. No manual setup required.

### CLI Options

```
./detect_events.sh <WAV_FILE_OR_DIR> [options]

  -o, --output-dir         Output directory (default: ./detected_events)
  --threshold              Spectral flux threshold in MAD units (default: 2.5)
  --pre-roll               Seconds before event onset in clips (default: 20)
  --baseline-window        Baseline window in seconds (default: 60)
  --min-event-duration     Minimum event duration in seconds (default: 2)
  --max-freq               Max frequency Hz for analysis/video (default: 10000)
  --no-video               Skip spectrogram MP4 generation
  --json-only              Output JSON metadata only (no clips, video, or reports)

  # OSC options
  --osc-live               Replay events as live OSC messages to target host
  --osc-host               OSC target host (default: 127.0.0.1)
  --osc-port               OSC target port (default: 57120, SuperCollider default)
  --no-osc                 Skip OSC/SuperCollider output generation

  # Phenology options
  --phenology              Generate phenological calendar (requires multiple recordings)
```

### Spectral Analysis

The detector computes a Short-Time Fourier Transform (STFT) with frame_size=2048, hop=512 (75% overlap), Hann window. At 48kHz this gives ~23Hz frequency resolution and ~10.7ms time resolution — sufficient for bird syllables (50-200ms). Recordings above 48kHz are downsampled to 48kHz for detection, but clips preserve the original sample rate.

**Spectral features extracted per frame:**

- **Spectral flux** — half-wave rectified L2-norm measuring the rate of spectral change between consecutive frames. This is the primary event detection signal.
- **Spectral centroid** — the "center of mass" of the spectrum in Hz. Maps to perceived brightness/pitch.
- **Spectral flatness** (Wiener entropy) — ratio of geometric to arithmetic mean of the power spectrum. 1.0 = white noise, 0.0 = pure tone. Distinguishes tonal vocalizations from broadband noise.
- **Band energies** for 6 ecological frequency bands:

| Band | Range | Ecological content |
|------|-------|--------------------|
| Geophony | 0–2 kHz | Wind, rain, water flow |
| Biophony low | 2–4 kHz | Amphibians, large mammals |
| Biophony mid | 4–8 kHz | Birds, many insects |
| Biophony high | 8–16 kHz | Insects, bats |
| Ultrasonic | 16–24 kHz | Bats (if sample rate allows) |

### Event Detection

Events are detected using an **adaptive threshold** algorithm:

1. Compute a running median and MAD (median absolute deviation) of spectral flux over a 60-second causal baseline window
2. An event triggers when spectral flux exceeds `median + 2.5 * 1.4826 * MAD`
3. Nearby events within 5 seconds of each other are merged into a single event
4. Merged events shorter than 2 seconds are discarded
5. Each event clip includes 20 seconds of pre-roll before onset and 10 seconds of post-roll after offset, capped at 5 minutes maximum

The MAD-based approach is robust to non-stationary backgrounds (rain onset, dawn chorus buildup) because the baseline adapts continuously.

### Deep Ecology Classification

Each event is classified by its **ecological role** in the soundscape, not by species identity. Classification uses time of day (from AudioMoth timestamp), dominant frequency band, spectral flatness, event duration, and energy distribution.

**Biophonic voices** (the Parliament):
- `dawn_chorus_participant` — Mid-frequency activity during dawn hours (4:00–7:00)
- `dusk_chorus_participant` — Mid-frequency activity during dusk hours (17:00–19:30)
- `nocturnal_voice` — Night-time vocalizations (20:00–4:00)
- `territorial_announcement` — Tonal mid-frequency vocalizations of moderate duration
- `alarm_or_alert` — Short, intense mid-frequency events
- `insect_chorus` — Sustained high-frequency activity
- `amphibian_assembly` — Tonal low-frequency sustained signals

**Geophonic elements** (Voice of the Earth):
- `rain_event` — Long-duration broadband noise in the geophony band
- `wind_event` — Moderate-duration broadband noise in the geophony band
- `water_flow` — Noise-like signals in the geophony band

**Anthrophonic intrusions:**
- `mechanical_intrusion` — Low-frequency sustained noise
- `aircraft_passage` — Low-frequency passage patterns

**Acoustic transitions** (temporal ecotones):
- `silence_to_activity` — Large flux increase from previous event
- `activity_to_silence` — Large flux decrease from previous event
- `community_shift` — Energy spread across multiple bands

Each classification includes a **confidence score** (0–1) and human-readable reasoning.

### Ecoacoustic Indices

Five standard ecoacoustic indices are computed per event and per recording:

| Index | Reference | Description |
|-------|-----------|-------------|
| **ACI** | Pieretti et al. 2011 | Acoustic Complexity Index — temporal variability within frequency bins. High = complex biophonic activity. |
| **BIO** | Boelman et al. 2007 | Bioacoustic Index — area under the mean spectrum curve between 2–8 kHz. |
| **NDSI** | Kasten et al. 2012 | Normalized Difference Soundscape Index — (biophony - anthrophony) / total. Range: -1 (all anthrophony) to +1 (all biophony). |
| **ADI** | Villanueva-Rivera et al. 2011 | Acoustic Diversity Index — Shannon entropy of frequency band activity proportions. |
| **AEI** | Villanueva-Rivera et al. 2011 | Acoustic Evenness Index — Gini coefficient of frequency band activity. |

**Parliament summary** statistics per recording:
- Total voices (event count)
- Domain percentages (biophony / geophony / anthrophony / transition)
- **Democracy index** — Shannon entropy of role distribution. Higher = more diverse acoustic community.
- **Niche partitioning score** — Shannon entropy of frequency band usage. Higher = more spectral niche diversity.

### Spectrogram Videos

Each event clip gets a spectrogram MP4 video that mirrors the ffmpeg filter chain from `make-spectrogram-movie-fixed.sh`:

- `showspectrum` filter: 996x592, linear frequency scale, cool colormap, log gain scale, 72dB dynamic range, scroll mode
- Header text overlay (top-left): habitat name
- Date text overlay (top-right): recording date and time
- Classification label (bottom-left, yellow): ecological role, confidence, and dominant frequency band
- H.264 encoding, AAC audio at 128kbps

### OSC Output (Open Sound Control)

Every detected event generates OSC messages tagged with full ecological metadata, designed for **Eurorack modular synthesis**, **ILDA laser control**, **SuperCollider**, and other OSC-capable instruments.

**Two modes:**
- **Batch mode** (default): Writes `.osc` bundle file + SuperCollider `.scd` score file
- **Live/playback mode** (`--osc-live`): Replays events in real-time to a configurable OSC target

**OSC address namespace:**

```
/parliament/event              — new event trigger (bang)
/parliament/event/onset        — onset time (float, seconds)
/parliament/event/duration     — event duration (float, seconds)
/parliament/event/role         — ecological role tag (string)
/parliament/event/domain       — acoustic domain (string: biophony/geophony/anthrophony)
/parliament/event/band         — dominant frequency band (string)
/parliament/event/centroid     — spectral centroid Hz (float)
/parliament/event/flatness     — spectral flatness 0-1 (float)
/parliament/event/flux         — peak spectral flux (float)
/parliament/event/confidence   — detection confidence 0-1 (float)
/parliament/event/aci          — acoustic complexity index (float)
/parliament/event/ndsi         — normalized difference soundscape index (float)
/parliament/event/bio          — bioacoustic index (float)
/parliament/event/adi          — acoustic diversity index (float)
/parliament/habitat            — habitat type (string)
/parliament/season             — season (string)
/parliament/temperature        — ambient temperature C (float)
/parliament/hour               — hour of day 0-23 (int)
/parliament/democracy_index    — acoustic democracy index (float)

# ILDA laser control
/ilda/color                    — mapped from dominant band (int, ILDA color index)
/ilda/intensity                — mapped from confidence (float 0-1)
/ilda/angle                    — mapped from spectral centroid (float, normalized)
/ilda/speed                    — mapped from spectral flux (float)

# Phenological calendar triggers
/phenology/event               — phenological event trigger
/phenology/type                — event type (string)
/phenology/day_of_year         — day of year 1-365 (int)
/phenology/dawn_chorus_time    — dawn chorus onset, minutes after midnight (float)
```

**Eurorack mapping notes:**
- Centroid -> V/Oct pitch CV (log-scaled from 261.63Hz = 0V)
- Flux -> gate/trigger intensity
- Flatness -> timbre CV (0 = tonal, 1 = noise)
- NDSI -> bipolar CV (-5V to +5V mapping)

**SuperCollider score (.scd):** Each event becomes a timed OSC bundle compatible with `Score.play` and NRT rendering.

### Phenological Calendar

When processing multiple recordings (`--phenology` flag), the detector builds a **phenological calendar** tracking how acoustic communities shift across time:

**Temporal resolution layers:**
- **Diel cycle** (24h): dawn chorus onset time, dusk transition, nocturnal peak activity
- **Multi-day**: acoustic community stability, arrival/departure of vocal species groups
- **Seasonal**: biophonic richness shifts, insect chorus intensity, amphibian breeding chorus

**Phenological events detected:**
- `breeding_chorus_onset` — amphibian/insect choruses intensify across consecutive recordings
- `migration_acoustic_shift` — new frequency niches appear/disappear (ADI change)
- `rain_season_transition` — geophonic rain events increase, biophonic patterns shift
- `dawn_chorus_advance_delay` — dawn chorus onset time shifts with season
- `nocturnal_community_change` — night-time assemblage shifts

**Outputs:** `phenological_calendar.json` with dated entries, and an HTML calendar visualization (heatmap: hours x days, colored by acoustic activity intensity).

### Output Structure

```
detected_events/
  {recording_stem}/
    events.json                         # Full event metadata + classifications + indices
    events.osc                          # OSC bundle file
    events_score.scd                    # SuperCollider score file
    event_001_{onset}s-{offset}s.wav    # Audio clip (original sample rate)
    event_001_{onset}s-{offset}s.mp4    # Spectrogram video
    ...
    report.html                         # Per-file HTML report
  phenological_calendar.json            # Cross-recording phenology
  phenological_calendar.html            # Calendar heatmap visualization
  summary_report.html                   # Batch summary
  parliament_osc_score.scd              # Combined SuperCollider score
```

### HTML Reports

Reports use the same visual style as the existing AudioMoth metadata reports (gradient #667eea -> #764ba2, Plotly.js 3.3.0):

- **Parliament of the Living** summary panel with domain pie chart, democracy index, niche partitioning score
- **Event timeline** — colored blocks on time axis by acoustic domain
- **Spectral flux curve** with event markers
- **Acoustic indices** comparison bar chart per event
- **Event cards** with embedded `<video>` players for each clip's spectrogram MP4, showing classification, confidence, centroid, band, and indices

---

## Other Tools

### Spectrogram Movie Generator (`make-spectrogram-movie-fixed.sh`)

Generates scrolling spectrogram MP4 videos from WAV files using ffmpeg's `showspectrum` filter. Works with any WAV filename format. Features configurable dynamic range, frequency scale, colormap, and text overlays with recording date/location.

```bash
./make-spectrogram-movie-fixed.sh recording1.WAV recording2.WAV ...
```

### Spectrogram Thumbnail Generator (`make-spectrogram-thumbnail-fixed.sh`)

Generates static spectrogram PNG images (full-size + thumbnail) from AudioMoth WAV files using ffmpeg's `showspectrumpic` filter. Based on Nathan Wolek's original script, modified for YYYYMMDD_HHMMSS.WAV format.

```bash
./make-spectrogram-thumbnail-fixed.sh recording1.WAV recording2.WAV ...
```

### Master Processing Script (`master_script.sh`)

Orchestrates batch processing: generates spectrogram thumbnails, movies, and HTML gallery tables for a directory of AudioMoth recordings.

```bash
./master_script.sh
```

### AudioMoth Metadata Processor (`AudioMothRECS_LaLuna/audiomoth_processing.sh`)

Extracts AudioMoth metadata (datetime, temperature, battery, gain, sample rate) using the `metamoth` Python library. Generates interactive HTML reports with Plotly.js charts (temperature over time, recording timeline), an embedded audio player, and sortable/filterable tables. Automatically parses habitat type and season from directory structure.

```bash
cd AudioMothRECS_LaLuna
./audiomoth_processing.sh "Epoca lluvias/Bosque de galería y-o ripario/"
```

### HTML Gallery Generator (`enhanced_html_generator.sh`)

Creates an interactive HTML gallery from spectrogram thumbnails with metadata extraction and GPS coordinate entry.

### Video Utilities

- **`split-video.sh`** — Split video files at specified timestamps with re-encoding
- **`vid2gif.sh`** — Convert video clips to optimized GIFs

### HDR DNG Processing (`HDR-DNG-DJI-IMGS/`)

Batch processing scripts for DNG raw image files from DJI drones with HDR tone mapping.

---

## Requirements

- **bash** (all shell scripts)
- **ffmpeg** with showspectrum/showspectrumpic filters (spectrogram generation)
- **Python 3.10+** (event detector, metadata processor)
- **metamoth** (AudioMoth WAV metadata parsing)
- **numpy, scipy, soundfile** (spectral analysis)
- **python-osc** (OSC output)

The event detector's bash wrapper handles Python dependency installation automatically via a virtual environment.
