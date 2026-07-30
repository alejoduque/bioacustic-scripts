# Bioacoustic Scripts

A toolkit for turning AudioMoth field recordings into **phenological data that can be driven over OSC**.

It listens for moments when the soundscape changes — a species starting up, rain arriving, the dawn chorus turning over — cuts a short video clip of each one, classifies it by ecological role, and accumulates those events into a dated calendar that an instrument can follow: Eurorack, ILDA laser, SuperCollider, anything that speaks OSC.

**Live gallery:** https://etc.altred.xyz/staticbioacustics/index.html

---

## How to run

### First time

```bash
git clone git@github.com:alejoduque/bioacustic-scripts.git
cd bioacustic-scripts
chmod +x bioacoustics.sh detect_events.sh
./bioacoustics.sh
```

That's the whole setup. On first launch the script finds a Python 3.10+ interpreter, creates a virtualenv at `~/.bioacoustic_detector_venv`, and installs `numpy`, `scipy`, `soundfile`, `metamoth` and `python-osc` into it. Takes a minute or two once; every later run starts immediately. Nothing is installed system-wide and nothing else needs configuring.

Two things worth knowing before you start:

- **ffmpeg is optional but recommended.** Without it you still get clips, `events.json`, OSC exports, the calendar and the reports — but no spectrogram video, stills or GIFs. `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Debian/Ubuntu).
- **Recording filenames matter for phenology.** The AudioMoth `YYYYMMDD_HHMMSS.WAV` format is how the toolkit knows when each recording was made. Files named otherwise still produce events and clips, but they cannot be placed on a calendar.

Check your environment at any time:

```bash
./bioacoustics.sh doctor
```

### The guided way

```bash
./bioacoustics.sh
```

One entry point, one menu:

```
 1  Detect events and cut video clips      the core pipeline — start here
 2  Phenological calendar                  dated ecological series + OSC exports
 3  OSC                                    stream, serve or export for instruments
 4  Event clip gallery                     browse the clips by event type
 5  AudioMoth metadata report              headers, temperature, battery
 6  Media utilities                        whole-file spectrogram, GIF, split
 7  HDR photo batch (DJI DNG)              bracketed stills from the same surveys
 8  Environment check                      what is installed
```

Each option explains what it does, then asks only what it cannot infer — where your recordings are, how sensitive detection should be, which kinds of event you want clips of, whether to render video. Defaults are shown in brackets, so Enter accepts them. Before anything runs you get a plan to confirm:

```
Plan
    recordings : 11 file(s)
        output : ./detected_events
   sensitivity : balanced (threshold 2.5 MAD)
  clip padding : -20s / +10s
       domains : all
   event types : all
         media : video, still, reels
     phenology : yes

Run this? (Y/n)
```

Answers persist to `~/.bioacoustics_wizard.json`, so the second session is mostly pressing Enter. Typing `q` inside a flow returns to the menu; `q` at the menu quits. Nothing is destructive — every flow writes into an output folder you choose.

### The direct way

Every feature is also a subcommand, for scripting and repeat runs:

```bash
# Analyse a folder: event clips, videos, OSC, calendar, gallery
./detect_events.sh recordings/ --phenology

# Same thing spelled out
./bioacoustics.sh detect recordings/ --phenology -o ./results

# One recording, more sensitive, no video
./detect_events.sh recordings/20250315_053000.WAV --sensitivity subtle --no-video

# Only rain and wind, with GIF previews
./detect_events.sh recordings/ --domains geophony --gif

# Stream the calendar to an instrument, one day per second, on repeat
./bioacoustics.sh osc phenology ./results --loop

# Let the instrument query instead: answers /phenology/query/*
./bioacoustics.sh osc serve ./results --listen-port 57121

# Rebuild outputs without re-analysing the audio
./bioacoustics.sh phenology ./results
./bioacoustics.sh gallery ./results
```

Help for any subcommand:

```bash
./bioacoustics.sh --help
./bioacoustics.sh detect --help
```

A path as the first argument is shorthand for `detect`, so `./detect_events.sh rec.WAV --threshold 1.5` works as it always did.

### Four typical workflows

**Survey a single card of recordings.** Detection is the expensive step; everything else reads its output.

```bash
./detect_events.sh /Volumes/AUDIOMOTH/ -o ./luna_marzo --phenology
open ./luna_marzo/gallery.html          # browse the clips by event type
open ./luna_marzo/summary_report.html   # the batch at a glance
```

**Tune sensitivity before committing to a long run.** `--json-only` reports what would be detected without writing clips or rendering video — the same analysis, a fraction of the time and disk once ffmpeg is in play. (In one test of 11 × 100 s recordings: 80 KB of JSON instead of 155 MB of media.)

```bash
./detect_events.sh recordings/ --sensitivity salient --json-only -o /tmp/probe
./detect_events.sh recordings/ --sensitivity subtle  --json-only -o /tmp/probe2
# compare the event counts, then re-run for real with the setting you liked
```

Spectral analysis is the fixed cost and runs either way, so the saving is in the rendering, not the listening.

**Follow a season phenologically.** Point it at everything you have; the calendar needs recordings from at least two days.

```bash
./detect_events.sh "Epoca lluvias/" -o ./season --phenology --days-per-second 2
open ./season/phenological_calendar.html
column -s, -t ./season/phenological_series.csv | less -S
```

**Drive an installation.** Analyse once, then stream or serve as often as you like.

```bash
./detect_events.sh season/ -o ./season --phenology
cat ./season/osc_address_map.txt                      # what you'll receive
./bioacoustics.sh osc phenology ./season --loop --host 192.168.1.40 --port 57120
```

---

## Why events, not recordings

Earlier versions rendered one scrolling spectrogram per recording. A twelve-second amphibian assembly inside an hour of tape is invisible that way, and there is nothing to point an instrument at.

The pipeline now works per event:

```
audio → spectral features → adaptive-threshold detection → classification
      → one clip per event (with context) → spectrogram video, still, GIF
      → one reel per event type → events.json → OSC → report
```

and then across recordings:

```
results → phenological calendar → OSC score / live stream / query server
        → event gallery → batch summary
```

Clips are filed by what they are, so each kind of voice gets its own folder of evidence:

```
detected_events/
  20250315_053000/
    events.json                     # full metadata: events, classifications, indices
    events.osc                      # timed OSC bundle for this recording
    events_score.scd                # SuperCollider score
    report.html                     # per-recording report
    clips/
      biophony/dawn_chorus_participant/
        event_003_dawn_chorus_participant_40.8s-45.8s.wav
        event_003_dawn_chorus_participant_40.8s-45.8s.mp4
        event_003_..._-spectrogram.png
        event_003_..._-thumbnail.png
      geophony/rain_event/…
      transition/community_shift/…
    reels/
      reel_dawn_chorus_participant.mp4    # every clip of one type, concatenated
  phenological_calendar.json        # the calendar, incl. per-day OSC frames
  phenological_calendar.html        # heatmap, CV series, dawn drift, wavetable
  phenological_series.csv           # one tidy row per day
  phenology.osc                     # timed OSC bundle for the whole season
  phenology_score.scd               # SuperCollider score for the season
  osc_address_map.txt               # generated address reference
  gallery.html                      # every clip, grouped by event type
  summary_report.html               # the batch at a glance
```

Event videos are colour-coded by acoustic domain — biophony green, geophony cool, anthrophony fiery, transitions magma — and labelled with habitat, date, offset into the recording, ecological role, confidence, dominant band, NDSI and ACI.

---

## Phenological data over OSC

This is the point of the toolkit. A season of recordings becomes a control stream.

```bash
# Replay 90 days of field recording in 90 seconds
./bioacoustics.sh osc phenology detected_events/ --days-per-second 1

# Installation mode: repeat until stopped
./bioacoustics.sh osc phenology detected_events/ --loop --port 57120

# Let the instrument ask instead of being pushed at
./bioacoustics.sh osc serve detected_events/ --listen-port 57121
```

**Every scalar is sent twice** — the raw ecological value, then the same value scaled to 0–1 across the dataset — so a patch can take absolute numbers or a control voltage without knowing the season's range:

```
/phenology/day              0  "2025-03-10"  69          index, date, day of year
/phenology/day/activity     5.0   1.0                    events per recording, cv
/phenology/day/richness     8.0   1.0                    distinct roles, cv
/phenology/day/biophony     0.75  0.75                   share of events, cv
/phenology/day/ndsi         0.93  0.96                   soundscape index, cv
/phenology/day/dawn         330.7 0.70                   dawn chorus onset (min), cv
/phenology/day/hourly       0 0 0 0 0 6 0 …              24 ints
/phenology/day/role         "amphibian_assembly" 4 0.20  role, count, share
/phenology/event            "breeding_chorus_onset" "2025-03-14" 73  2.1
/phenology/diel/table       0.0 0.0 … 0.94 …             24 floats: a diel wavetable
/phenology/range/<field>    min max                      the normalization used
```

Normalized fields: `activity`, `richness`, `biophony`, `geophony`, `anthrophony`, `ndsi`, `adi`, `aci`, `dawn`.

The query server answers `/phenology/query/meta`, `/query/day <int>`, `/query/date <str>`, `/query/next`, `/query/prev`, `/query/events` and `/query/reply_port <int>`.

Per-event OSC (`/parliament/event/*`) is also emitted, including `/parliament/event/voct` — the spectral centroid pre-converted to V/Oct with 261.63 Hz at 0 V — plus `/ilda/{color,intensity,angle,speed}` for laser control.

The full address map is written next to your results as `osc_address_map.txt`, generated from the code rather than copied here:

```bash
./bioacoustics.sh osc map detected_events/
```

**Phenological shifts detected across days:** `breeding_chorus_onset` (low + high biophony energy both jump), `migration_acoustic_shift` (ADI turnover), `rain_season_transition` (geophonic events increase), `dawn_chorus_advance_delay` (onset time drifts), `nocturnal_community_change` (night assemblage turns over).

---

## Command reference

```
./bioacoustics.sh [subcommand] [options]

  detect      analyse recordings → event clips, videos, OSC, reports
  phenology   build/refresh the calendar and its OSC exports
  osc         export | phenology | events | serve | map
  gallery     rebuild the event-clip gallery from existing results
  media       spectrogram | poster | split | gif
  metadata    AudioMoth metadata report
  doctor      check tooling and report what is available
  wizard      the guided front-end (default when run with no arguments)
```

A path as the first argument means `detect`, so `./detect_events.sh rec.WAV --threshold 1.5` still works.

### detect

```
  -o, --output-dir DIR        where results go (./detected_events)
      --sensitivity NAME      subtle | balanced | salient
      --threshold N           spectral flux threshold in MAD units (2.5)
      --pre-roll N            seconds of context before onset (20)
      --post-roll N           seconds of context after offset (10)
      --baseline-window N     adaptive baseline window (60)
      --min-event-duration N  discard shorter events (2)
      --merge-gap N           merge events closer than this (5)

      --roles LIST            only clip these event types
      --domains LIST          biophony,geophony,anthrophony,transition
      --min-confidence N      skip classifications below this (0-1)

      --organize-by MODE      role | domain | flat
      --max-freq N            top frequency in spectrogram renders (10000)
      --no-video              skip MP4 rendering
      --no-poster             skip PNG + thumbnail
      --gif                   also render a looping GIF per clip
      --no-reels              skip the per-type concatenated reels
      --no-style-by-domain    one colormap for every event type
      --no-gallery            skip gallery.html
      --json-only             metadata only — no clips, media or reports

      --phenology             build the calendar afterwards
      --days-per-second N     calendar playback rate baked into OSC exports (1)
      --no-csv                skip the CSV export

      --osc-live              replay events live as they are found
      --osc-host / --osc-port OSC target (127.0.0.1 : 57120)
      --no-osc                skip OSC and SuperCollider output
```

Sensitivity presets: **subtle** (1.5 MAD, many events), **balanced** (2.5 MAD, the default), **salient** (4.0 MAD, only strong shifts).

---

## Replaced scripts

Everything below still runs; each one now forwards to the unified pipeline and prints the replacement command.

| Old script | Now | What changed |
|---|---|---|
| `make-spectrogram-movie-fixed.sh` | `bioacoustics.sh media spectrogram` | Same filter chain. Event clips are the default path; this is the whole-file escape hatch. Overlays no longer break on commas/colons in habitat names. |
| `make-spectrogram-thumbnail-fixed.sh` | `bioacoustics.sh media poster` | Same `showspectrumpic` recipe, now also applied per event clip. Thumbnails are 256×144 (were 128×72). |
| `master_script.sh` | `bioacoustics.sh detect` | Three chained scripts became stages of one pipeline, operating on events instead of whole recordings. |
| `enhanced_html_generator.sh` | `bioacoustics.sh gallery` | Was byte-identical to the file below. One card per event grouped by role; reads `events.json` instead of scanning for `*-thumbnail.png`; self-contained lightbox; no ffprobe/jq/numfmt dependency. GPS tagging carried over, same `localStorage` key. |
| `make-html-lightbox-table-fixed.sh` | `bioacoustics.sh gallery` | Duplicate of the above (same md5). |
| `vid2gif.sh` | `bioacoustics.sh media gif` | ffmpeg `palettegen`/`paletteuse` instead of mplayer + ImageMagick + gifsicle. No temp frame dumps, no hard-coded `/opt/homebrew` paths. |
| `split-video.sh` | `bioacoustics.sh media split` | Same size-budget approach, no `bc` dependency, audio re-encoded so each part plays standalone. |

Unchanged and reachable from the wizard: `AudioMothRECS_LaLuna/audiomoth_processing.sh` (metadata report) and `HDR-DNG-DJI-IMGS` (bracketed DNG → HDR).

---

## How detection works

### Spectral analysis

STFT with `frame_size=2048`, `hop=512` (75% overlap), Hann window. At 48 kHz that gives ~23 Hz frequency and ~10.7 ms time resolution — enough for bird syllables of 50–200 ms. Recordings above 48 kHz are downsampled for detection; clips keep the original sample rate.

Per frame: **spectral flux** (half-wave rectified L2 norm — the detection signal), **spectral centroid** (brightness, in Hz), **spectral flatness** (Wiener entropy; 1.0 = white noise, 0.0 = pure tone), and energy in six ecological bands:

| Band | Range | Ecological content |
|------|-------|--------------------|
| Geophony | 0–2 kHz | Wind, rain, water flow |
| Biophony low | 2–4 kHz | Amphibians, large mammals |
| Biophony mid | 4–8 kHz | Birds, many insects |
| Biophony high | 8–16 kHz | Insects, bats |
| Ultrasonic | 16–24 kHz | Bats (if sample rate allows) |

### Event detection

1. Running median and MAD of spectral flux over a 60 s causal baseline
2. Trigger when flux exceeds `median + 2.5 × 1.4826 × MAD`
3. Merge events within 5 s of each other
4. Discard merged events shorter than 2 s
5. Pad each clip with pre/post-roll, capped at 5 minutes

The MAD baseline adapts continuously, so non-stationary backgrounds — rain onset, dawn chorus buildup — do not swamp detection.

### Deep ecology classification: Parliament of the Living

Events are catalogued by their **role in the soundscape**, not by species identity. All acoustic participants — biological, geological, human — are treated as having inherent ecological value, and the system measures acoustic democracy as the Shannon entropy of role distribution.

**Biophonic voices:** `dawn_chorus_participant`, `dusk_chorus_participant`, `nocturnal_voice`, `territorial_announcement`, `alarm_or_alert`, `insect_chorus`, `amphibian_assembly`

**Geophonic elements:** `rain_event`, `wind_event`, `water_flow`

**Anthrophonic intrusions:** `mechanical_intrusion`, `aircraft_passage`

**Acoustic transitions (temporal ecotones):** `silence_to_activity`, `activity_to_silence`, `community_shift`

Classification uses time of day (from the AudioMoth timestamp), dominant band, spectral flatness, duration and energy distribution, and reports a confidence score with human-readable reasoning.

### Ecoacoustic indices

Computed per event and per recording:

| Index | Reference | Description |
|-------|-----------|-------------|
| **ACI** | Pieretti et al. 2011 | Temporal variability within frequency bins. High = complex biophonic activity. |
| **BIO** | Boelman et al. 2007 | Area under the mean spectrum curve, 2–8 kHz. |
| **NDSI** | Kasten et al. 2012 | (biophony − anthrophony) / total. −1 = all anthrophony, +1 = all biophony. |
| **ADI** | Villanueva-Rivera et al. 2011 | Shannon entropy of band activity proportions. |
| **AEI** | Villanueva-Rivera et al. 2011 | Gini coefficient of band activity. |

Per-recording parliament statistics: total voices, domain percentages, **democracy index** (entropy of role distribution) and **niche partitioning** (entropy of band usage).

---

## Package layout

```
bioacoustics.sh          Single entry point — wizard, or any subcommand
detect_events.sh         Direct access to the detect pipeline

bioacoustic_detector/
  wizard.py              Guided front-end to every feature
  cli.py                 Subcommands and argument parsing
  pipeline.py            The stage chain, per file and per batch
  config.py              Every tunable parameter, plus sensitivity presets
  spectral.py            STFT, flux, centroid, flatness, band energies
  detector.py            Adaptive-threshold event detection
  classifier.py          Deep ecology taxonomy
  indices.py             ACI, BIO, NDSI, ADI, AEI
  clipper.py             Clip extraction, event filters, role-based filing
  video.py               Event clip videos, posters, GIFs, per-type reels
  media.py               ffmpeg plumbing; video split and GIF conversion
  gallery.py             Event-clip gallery with lightbox and GPS tagging
  phenology.py           Calendar, OSC frames, CSV, HTML
  osc_output.py          OSC messages, bundles, SuperCollider scores, streaming
  osc_server.py          Bidirectional OSC query server
  metadata.py            AudioMoth metadata; habitat/season from paths
  report.py              Per-recording and batch HTML reports
  store.py               events.json read/write with portable paths
```

---

## Requirements

- **Python 3.10 or newer.** macOS ships 3.9 as `/usr/bin/python3`; the launcher searches for a newer interpreter and rebuilds its virtualenv if it finds an older one. Install with `brew install python@3.12` if needed.
- **ffmpeg** — optional but needed for spectrogram video, stills and GIFs. Without it you still get clips, `events.json`, OSC exports, the calendar and the reports; the pipeline says so and carries on. `brew install ffmpeg`.
- Python packages (installed automatically into the managed venv): `numpy`, `scipy`, `soundfile`, `metamoth`, `python-osc`.

`./bioacoustics.sh doctor` reports on all of the above.

---

## Troubleshooting

**"Python 3.10 or newer is required but was not found."**
Install a newer interpreter (`brew install python@3.12`) and run again. The launcher searches `python3.14` down to `python3.10`, then `python3`, and also looks inside `/opt/homebrew/bin` and `/usr/local/bin` in case Homebrew is not on your `PATH`. It will not use macOS's system 3.9.

**No spectrogram videos appeared.**
ffmpeg is missing — the run says so as it goes and produces everything else. Install it and re-run `detect` on the same input: media is rendered during detection, so there is no separate render step to resume. The clips and JSON from the first pass are simply overwritten.

**"No WAV files found in: …"**
The path is checked as given, relative to where you are standing (not to the repo). Quote paths containing spaces or accents: `./detect_events.sh "Epoca lluvias/Bosque de galería y-o ripario/"`. Both `.WAV` and `.wav` are found, recursively.

**Too many or too few events.**
Start with `--sensitivity subtle | balanced | salient`, and only reach for `--threshold` (MAD units — lower is more sensitive) if the presets do not land where you want. `--min-event-duration` discards brief blips; `--merge-gap` decides how far apart two triggers must be to count as separate events. Probe with `--json-only` first, it costs seconds.

**"Only one recording — the calendar needs several to compare."**
Phenology is a cross-recording product. It needs recordings from at least two different days, each carrying a parseable timestamp — either an AudioMoth `YYYYMMDD_HHMMSS.WAV` filename or intact AudioMoth metadata. The run reports how many of your files have usable timestamps.

**Nothing arrives at the instrument.**
Check the target with `--host` and `--port` (default `127.0.0.1:57120`, SuperCollider's default). `osc serve` listens on `--listen-port` (default 57121) and *replies* to `--host`/`--port`, which can be redirected at runtime by sending `/phenology/query/reply_port <int>`. `cat osc_address_map.txt` for the exact addresses your results emit.

**A gallery link opens nothing.**
Media paths inside `events.json` are stored relative to each recording's folder, so the whole output tree can be moved or published as a unit — but moving `gallery.html` on its own breaks its links. Regenerate it in place with `./bioacoustics.sh gallery <output_dir>`.

**An old script printed a note about a new command.**
That's expected. The seven retired scripts still work; they forward to the pipeline and name their replacement. See [Replaced scripts](#replaced-scripts).
