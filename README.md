# Bioacoustic Scripts

**English** · [Español](README.es.md)

A toolkit for turning AudioMoth field recordings into **phenological data that can be driven over OSC**.

It listens for moments when the soundscape changes — a species starting up, rain arriving, the dawn chorus turning over — cuts a short video clip of each one, classifies it by ecological role, and accumulates those events into a dated calendar that an instrument can follow: Eurorack, ILDA laser, SuperCollider, anything that speaks OSC.

**Live gallery:** https://etc.altred.xyz/staticbioacustics/index.html
**Field calibration protocol:** [docs/CALIBRATION.md](docs/CALIBRATION.md) — what to do when the real recordings arrive

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

## Reading a spectrogram clip

Every rendered clip encodes four independent channels of information. Nothing is decorative.

| Channel | Carries | Set by |
|---|---|---|
| **Vertical axis** | frequency — which part of the spectrum the sound occupies | `--max-freq`, or Nyquist in ultrasonic mode |
| **Horizontal axis** | time within the clip, scrolling right to left | clip length = event + pre/post-roll |
| **Brightness** | energy in dBFS over a 72 dB range, log-scaled | `dynamic_range`, `gain_scale` |
| **Hue** | the acoustic **domain** the classifier assigned | `domain_colors` in `config.py` |

Text is white with a 1-pixel black outline and no filled box, so it stays legible over any colormap without hiding the spectrogram beneath it — and so that colour in the frame means exactly one thing: the acoustic domain.

### Why colour maps to domain

A colormap is a categorical signal, and there is only one categorical decision worth spending it on. Frequency is already the vertical axis; amplitude is already brightness. What neither axis shows is **what kind of participant** made the sound — and that is the entire point of the classification.

So the colormap answers "who is speaking?" at a glance, before you read a single label:

| Domain | Colormap | Reads as | What lives here |
|---|---|---|---|
| **biophony** | `green` | living, vegetal | birds, frogs, insects, bats — anything alive |
| **geophony** | `cool` (blue/teal) | water, air, cold | rain, wind, thunder, flowing water |
| **anthrophony** | `fiery` (orange/red) | intrusion, alarm | engines, aircraft, machinery |
| **transition** | `magma` (pink/purple) | a boundary, not a voice | the soundscape changing state |

Scrubbing a folder of clips, an assemblage reads as a colour distribution: a green night is a biophonically active one, a blue night was rained out, orange means a road or a pump was audible. That property is what makes the gallery scannable across hundreds of events, and it is why the domain — not the role — gets the colour. Sixteen roles would need sixteen colormaps that nobody could distinguish; four domains are separable at a glance.

Transitions get `magma` deliberately. They are not a voice at all — they mark the *seam* where one acoustic community gives way to another. Giving them a hue that belongs to neither the living green nor the elemental blue keeps that distinction visible.

### The chain from FFT to colour

Colour is the last link in a chain that starts with the raw samples. Each step is a decision made from the step before it, and nothing in it is a species identification:

```
samples
  → STFT magnitude |X(t,f)|            frame_size 2048, hop 512, Hann
  → spectral flux  Φ(t)                half-wave rectified L2 of successive frames
  → adaptive threshold                 median + 2.5 × 1.4826 × MAD, 60 s causal window
  → event onset/offset                 contiguous frames above threshold, merged, filtered
  → per-event features                 band energies, centroid, flatness, duration, indices
  → ecological ROLE                    rule-based, 16 categories        (the caption)
  → acoustic DOMAIN                    role → {biophony, geophony, anthrophony, transition}
  → COLORMAP                           domain → {green, cool, fiery, magma}
```

The **role** is the finest judgement the system makes, and the label prints it with a confidence (`Dawn Chorus Participant (80%) | biophony mid`). The **domain** is the coarse, robust rollup — a rain event misfiled as wind is still geophony, still blue. Colour is therefore more trustworthy than the caption above it, which is exactly why colour carries the at-a-glance meaning and the caption carries the detail.

### Two worked examples

These are real frames from the verification corpus, and each one is internally consistent — you can check the classification against the picture and the numbers against both.

**A dawn chorus participant, rendered green.**

Two chirps sweep 4.7 → 6.7 kHz against near-silence. The energy sits squarely in `biophony_mid` (4–8 kHz, the passerine band); the recording timestamp is 05:30, inside the 04:00–07:00 dawn window; the sweeps are tonal, so flatness is low. Rules fire in that order and produce `dawn_chorus_participant` at 0.80 confidence, domain biophony, colormap green. The caption reads `Dawn Chorus Participant (80%) | biophony mid`, and `NDSI +1.00` confirms it: essentially all energy is in the 2–8 kHz biophonic band and none in the 1–2 kHz anthropogenic one.

**A rain shower, rendered magma — and why it is not labelled `rain_event`.**

A solid block of noise fills everything below ~1.9 kHz for the whole clip, with nothing above it. `dominant_band` is `geophony` (0–2 kHz) and `NDSI −0.99` agrees: essentially all energy sits in the low band the index treats as non-biophonic. The picture and the arithmetic match perfectly.

The label, however, reads `Silence To Activity (70%) | geophony`, and the clip renders in transition magma rather than geophony blue. Two rules combine to produce that:

1. **Transition rules take precedence over content rules.** When an event's peak flux is more than 5× the previous event's, it is filed as `silence_to_activity` whatever is making the sound. A rain onset is exactly such a jump. This is deliberate — the seam between acoustic regimes is ecologically interesting — but it means the first event of any new regime is usually a transition.
2. **The `rain_event` rule did not fire even for the later, non-jumping events.** It requires `flatness > 0.30`; the measured flatness of those blocks was **0.21 and 0.29**.

The second point is a calibration gap worth knowing before trusting labels in bulk, and it comes from a property of the features rather than a coding error:

- **Spectral flatness is computed over the whole spectrum.** A signal that is perfectly noise-like *within its own band* still scores low when it occupies only part of the range. The measure answers "is this recording noisy?", not "is this event noisy?".
- **Spectral centroid is magnitude-weighted over the whole spectrum**, so a wide low-level noise floor drags it upward. Those same rain events reported centroids of **6.5 and 7.7 kHz** despite having no energy at all above 2 kHz — which is why the anthrophony rule (`centroid < 1500`) missed them too.

In the 45-event verification corpus, `rain_event`, `wind_event`, `water_flow`, `mechanical_intrusion` and `aircraft_passage` were therefore **never emitted**. Geophonic content was real, visible and correctly measured — it simply fell through to the transition and fallback rules.

The thresholds live at the top of `classifier.py` as named constants (`GEOPHONY_FLATNESS`, `ANTHROPHONY_CENTROID_HZ`, …) precisely so they can be recalibrated against annotated field recordings. **Until that calibration happens on real tropical dry forest data, treat `dominant_band` and the numeric features as the trustworthy signal and `role` as a hypothesis.** For the same reason, domain colour is more reliable than the caption above it.

---

## Ultrasound: bats, Nyquist, and what gets thrown away

AudioMoth records at 8, 16, 32, 48, 96, 192, 250, 256 or 384 kHz. Anything above 48 kHz is a deliberate choice to record bats, and it changes what the toolkit has to do.

### The hard limit

Sampling at rate *fs* can represent frequencies only up to **Nyquist = fs/2**. Above that, content does not vanish — it **aliases**, folding down to `|fs − f|` and appearing at a frequency that was never there:

| AudioMoth rate | Nyquist | Reaches | Misses |
|---|---|---|---|
| 48 kHz | 24 kHz | birds, frogs, insects, the lowest bats | most echolocation |
| 96 kHz | 48 kHz | Molossidae, some Vespertilionidae | high Phyllostomidae |
| 192 kHz | 96 kHz | nearly all neotropical echolocation | the highest CF species |
| 256 / 384 kHz | 128 / 192 kHz | everything | — |

This is not hypothetical. While building the test corpus a synthetic 105 kHz caller was written into a 192 kHz file; it appeared at 87 kHz (`|192 − 105|`) and was classified from that aliased frequency. A real species above Nyquist produces exactly the same artefact, and nothing downstream can tell the difference. **Choose the recorder's sample rate from the assemblage you expect, and treat energy near the top of the plot with suspicion.**

### Why the default discards ultrasound

By default the detector downsamples to 48 kHz before analysis. That is the right choice for a bird-and-frog survey — it bounds cost and matches the STFT resolution to bird syllables — but the anti-alias filter removes everything above 24 kHz **permanently for that analysis**. Bats become invisible; they do not appear as weak events, they do not appear at all.

Rather than fail silently, a recording sampled above 2× the analysis rate triggers a warning:

```
! This recording carries content up to 96 kHz, but analysis downsamples to 48 kHz.
  Everything above 24 kHz — bat echolocation, high katydids — is discarded.
  Re-run with --ultrasonic to analyse at the native rate.
```

### What `--ultrasonic` changes

```bash
./detect_events.sh recordings/ --ultrasonic
```

Four things move together, because changing any one alone leaves bats unusable:

| | Default | `--ultrasonic` | Why |
|---|---|---|---|
| Analysis rate | 48 kHz | native (192 kHz…) | anything above Nyquist/2 is otherwise filtered out |
| STFT window | 2048 / 512 hop | 1024 / 256 hop | at 192 kHz a 2048 window spans 10.7 ms — longer than an entire call |
| Band table | 5 bands to 24 kHz | 7 bands to 160 kHz | `ultrasonic` alone cannot separate a Molossid from a Phyllostomid |
| Event timing | merge 5 s, min 2 s | merge 1 s, min 0.3 s | a pass lasts 1–3 s; the audible defaults fuse a night of foraging into one block |

Explicit `--merge-gap` / `--min-event-duration` flags override the timing defaults.

The video also re-frames itself: the axis runs to Nyquist instead of 10 kHz, and switches to a **logarithmic** frequency scale so 0–10 kHz still occupies a readable share of a 0–96 kHz plot instead of being crushed into the bottom 10%.

### The ultrasonic band table

Splits chosen for neotropical dry-forest assemblages:

| Band | Range | Typical occupants |
|---|---|---|
| `ultrasonic_low` | 16–40 kHz | Molossidae (free-tailed bats), some Vespertilionidae, high katydids |
| `ultrasonic_mid` | 40–80 kHz | most Vespertilionidae and Phyllostomidae search-phase calls |
| `ultrasonic_high` | 80–160 kHz | high-frequency Phyllostomidae, terminal feeding buzzes |

An event whose dominant band is any of these classifies as `bat_echolocation` (domain biophony, so it renders green). That rule is checked *before* the diel rules, because a dominant band above 16 kHz is unambiguous — no bird, frog or engine puts its main energy there.

Verified on a synthetic 192 kHz recording containing four deliberately different sources:

| Synthesized | Detected at | Band | Role |
|---|---|---|---|
| 60→25 kHz FM sweeps + feeding buzz | 0.07 s | `ultrasonic_mid` | `bat_echolocation` |
| 85 kHz CF tone | 10.34 s | `ultrasonic_high` | `bat_echolocation` |
| 12 kHz katydid band | 14.05 s | `biophony_high` | `insect_chorus` |
| 30→18 kHz sweeps | 24.00 s | `ultrasonic_low` | `bat_echolocation` |

The same file analysed **without** `--ultrasonic` yielded two `insect_chorus` events and no bats at all — the katydids survived downsampling, everything else was filtered away.

### Cost

Analysing at 192 kHz with a 256-sample hop produces 750 frames per second, eight times the audible default. The adaptive baseline is a running median over a 60-second window, which is O(frames × window) — at that frame rate an hour of tape would take days. It is therefore evaluated at up to 2000 anchor points and linearly interpolated between them, with the first 512 frames always computed exactly (that is the one stretch where the statistic genuinely moves fast, while the window is still filling).

The approximation was checked against the exact computation across the audible corpus: **identical event counts, identical onsets, and two event offsets out of 45 differing by 32 ms and 75 ms** — a threshold crossing on a decaying tail landing one or two frames apart. The speedup is 5.6× at 48 kHz and the difference between usable and unusable at 192 kHz.

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
  validate    score the detector against externally annotated datasets
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
      --max-clip-duration N   cap on clip length in seconds (300)
      --ultrasonic            analyse at the native rate, extend the bands to
                              cover bat echolocation, and switch event timing
                              to a bat's scale. Required for recordings made
                              above 48kHz; without it everything above 24kHz
                              is discarded.

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

The three sensitivity presets and what they change are tabulated under [Event detection](#event-detection).

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

Audio is mixed to mono, optionally downsampled (polyphase, `scipy.signal.resample_poly`), then transformed frame by frame:

$$X(t,k) = \sum_{n=0}^{N-1} x(tH + n)\,w(n)\,e^{-2\pi i kn/N}$$

with **N = frame_size = 2048**, **H = hop_size = 512** (75 % overlap) and *w* a periodic Hann window. Only the real half is kept, giving `N/2 + 1 = 1025` bins.

Resolution follows directly from *N*, *H* and the rate:

| | 48 kHz (default) | 192 kHz + `--ultrasonic` |
|---|---|---|
| Frequency resolution `fs/N` | 23.4 Hz | 187.5 Hz |
| Window length `N/fs` | 42.7 ms | 5.3 ms |
| Frame spacing `H/fs` | 10.7 ms | 1.3 ms |

The default is matched to bird syllables (50–200 ms); the ultrasonic setting trades frequency detail for the time detail a 1–10 ms echolocation pulse requires. This is the classic uncertainty trade — you cannot have both, and the right side depends on what you are listening for.

**Per-frame features** (all from the magnitude spectrum `|X|`):

| Feature | Definition | Reads as |
|---|---|---|
| Spectral flux | $\Phi(t) = \sqrt{\sum_k \max(0,\,\lvert X(t,k)\rvert - \lvert X(t-1,k)\rvert)^2}$ | rate of spectral *change*; half-wave rectified so only new energy counts. **This is the detection signal.** |
| Spectral centroid | $C(t) = \left(\sum_k f_k \lvert X \rvert\right) / \left(\sum_k \lvert X \rvert\right)$ | brightness, in Hz |
| Spectral flatness | $F(t) = \exp\left(\overline{\ln \lvert X \rvert^2}\right) / \overline{\lvert X \rvert^2}$ | 1.0 = white noise, 0.0 = pure tone (Wiener entropy) |
| Band energy | $E_b(t) = \sum_{f_k \in b} \lvert X(t,k)\rvert^2$ | power per ecological band |

Two caveats that matter for interpretation and for any model trained on these: **centroid and flatness are both global** — computed across the entire spectrum, not within the event's own band. A band-limited event therefore reports a flatness that reflects how much of the *whole* spectrum it fills, and a centroid pulled upward by the wideband noise floor. See the rain example above for measured numbers.

**Ecological bands.** Half-open `[lo, hi)` in Hz, clipped to Nyquist so a 48 kHz recording reports zero energy above 24 kHz rather than inventing it.

| Band | Range | Ecological content |
|------|-------|--------------------|
| `geophony` | 0–2 kHz | wind, rain, water flow, distant thunder |
| `biophony_low` | 2–4 kHz | anurans, large mammals, doves and tinamous |
| `biophony_mid` | 4–8 kHz | most passerine song, many orthopterans |
| `biophony_high` | 8–16 kHz | cicadas, katydids, high passerines |
| `ultrasonic` | 16–24 kHz | the low edge of bat calls, if the rate allows |

With `--ultrasonic` the last band is replaced by `ultrasonic_low` (16–40 kHz), `ultrasonic_mid` (40–80 kHz) and `ultrasonic_high` (80–160 kHz).

### Event detection

An event is a moment when the spectrum *changes*, measured against what the recording has been doing recently:

$$\Phi(t) > \mathrm{median}_{W}(\Phi) + \kappa \cdot 1.4826 \cdot \mathrm{MAD}_{W}(\Phi)$$

where *W* is a **60-second causal window** (look-back only, so detection could run live), κ is `--threshold` (default 2.5), and 1.4826 is the constant that makes the MAD a consistent estimator of the standard deviation for normally distributed data.

Median and MAD rather than mean and σ because a robust baseline is the whole point: a single loud event must not raise the bar that judges the events around it. The MAD's breakdown point is 50 % — half the window can be outliers before the estimate moves.

1. Compute the running median and MAD of Φ over the causal window
2. Trigger where Φ exceeds the threshold; contiguous frames form a region
3. Merge regions closer than `--merge-gap` (5 s default)
4. Discard merged events shorter than `--min-event-duration` (2 s default)
5. Pad each clip with pre/post-roll, capped at `--max-clip-duration`

Because the baseline adapts continuously, non-stationary backgrounds — rain arriving, a dawn chorus building over twenty minutes — raise the threshold with them rather than saturating the detector.

**Sensitivity presets** move κ and the timing together:

| Preset | κ (MAD units) | Min duration | Merge gap |
|---|---|---|---|
| `subtle` | 1.5 | 1.0 s | 3 s |
| `balanced` (default) | 2.5 | 2.0 s | 5 s |
| `salient` | 4.0 | 3.0 s | 8 s |

Note that κ is in **robust standard deviations of the local flux**, not an absolute level — the same setting behaves comparably at a loud site and a quiet one, which is what makes cross-site comparison meaningful.

### Deep ecology classification: Parliament of the Living

Events are catalogued by their **role in the soundscape**, not by species identity. All acoustic participants — biological, geological, human — are treated as having inherent ecological value, and the system measures acoustic democracy as the Shannon entropy of role distribution.

**Biophonic voices:** `dawn_chorus_participant`, `dusk_chorus_participant`, `nocturnal_voice`, `territorial_announcement`, `alarm_or_alert`, `insect_chorus`, `amphibian_assembly`, `bat_echolocation` (ultrasonic mode only)

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

All five are computed twice: once per event (over that event's frames only) and once per whole recording. The per-event values are what land in `events.json` and on the video captions; the per-recording values feed the calendar.

Per-recording parliament statistics, both Shannon entropies over the event set:

$$H = -\sum_i p_i \log_2 p_i$$

- **Democracy index** — *p* over the distribution of ecological **roles**. Higher means no single kind of voice dominates the assemblage.
- **Niche partitioning** — *p* over the distribution of dominant **bands**. Higher means the community is spread across the spectrum rather than crowded into one band.

Both inherit the classifier's calibration: the democracy index is only as meaningful as the role assignment beneath it, whereas niche partitioning rests on band energies and is therefore the sturdier of the two.

---

## Phenological phases and how they relate to the colours

The calendar layer is where colour, classification and season meet. Each day of recording is reduced to a frame of scalars; a phase is a **sustained change in the composition of those frames**, not a property any single clip has.

### From clips to phases

```
event clips (coloured by domain)
  → daily aggregation   role counts, domain shares, band energies, mean indices
  → per-day frame       activity, richness, biophony/geophony/anthrophony shares…
  → normalization       every field also scaled to 0-1 across the dataset (cv)
  → phase detection     day-over-day comparisons crossing a threshold
```

The domain shares in each day's frame are literally *the proportion of that day's clips rendered in each colour*. A gallery whose cards turn from green to blue over a fortnight is the same fact as `cv_geophony` rising and `cv_biophony` falling, and the same fact as a `rain_season_transition` event on the calendar. Colour, CSV column and OSC message are three renderings of one measurement.

### The five phase detectors

| Phase | Fires when | Reads from | Threshold |
|---|---|---|---|
| `breeding_chorus_onset` | `biophony_low` **and** `biophony_high` energy both more than double vs the previous day | band energies | `breeding_energy_ratio` = 2.0 |
| `migration_acoustic_shift` | ADI changes by more than 0.5 between days — frequency niches opening or closing | mean ADI | `adi_shift` = 0.5 |
| `rain_season_transition` | geophonic event count jumps by more than 3 in a day | domain counts | `geophony_event_jump` = 3 |
| `dawn_chorus_advance_delay` | first biophonic event of the morning shifts by more than 15 min | dawn onset times | `dawn_shift_minutes` = 15 |
| `nocturnal_community_change` | the set of night-active roles gains or loses a member | role sets | any change |

Why these five: they are the phenological signals that a **soundscape** can carry without species identification. Breeding choruses are a reproductive phase (anurans in the low band, orthopterans in the high one — hence requiring both to move together, which distinguishes a chorus from a passing noise source). Dawn chorus timing tracks photoperiod and is one of the most reliable seasonal clocks in the tropics, where temperature cues are weak. In a **tropical dry forest** specifically, the wet/dry transition is the dominant annual event, and it announces itself twice over: directly as geophony, and indirectly as the anuran explosion that follows the first rains within days.

Dawn onset deserves a caveat: it is currently defined as the first biophonic event between 03:00 and 08:00, which depends on a recording actually existing at that hour. Gaps in a duty cycle become spurious "delays". For phenology, schedule recordings to cover dawn every day rather than sampling opportunistically.

### The colour of a season

Because the colormap is chosen by domain, a season has a visual signature you can read directly from the gallery or the calendar heatmap:

- **Dry season, dawn** — mostly green, concentrated in `biophony_mid`, high `democracy_index` as many bird species overlap
- **First rains** — magma transitions appear as regimes change, then blue geophony blocks
- **Wet season, night** — green again but shifted low (`biophony_low`, anuran chorus) and high (`biophony_high`, orthopterans), with the middle emptier; `niche_partitioning` rises
- **Any season, near a road** — fiery bands recur at human hours, and `NDSI` falls toward zero or below

Those are the patterns the indices are designed to quantify, and the reason both the colour and the number are kept for every event.

---

## Using this as a dataset (machine learning)

The pipeline is a **weak-labelling and segmentation front end**, not a classifier to be trusted as ground truth. Read this section before training anything on its output.

### What each artefact is good for

| Artefact | Suitable as | Not suitable as |
|---|---|---|
| `clips/**/*.wav` | training audio, already segmented to events with context | — |
| `onset_s`, `offset_s`, `duration_s` | segmentation targets; derived from signal, not judgement | precise boundaries (threshold crossings, ±1 frame) |
| `band_energies`, `centroid`, `flatness`, `peak_flux` | input features; deterministic functions of the audio | — |
| `aci`, `bio`, `ndsi`, `adi`, `aei` | input features; published, comparable across studies | — |
| `dominant_band` | a reliable coarse label — it is just an argmax over measured energy | species identity |
| `domain` | a defensible 4-class weak label | ground truth where transitions dominate |
| `role` | a **hypothesis** from hand-tuned thresholds | a training target without human verification |
| `confidence` | a hand-assigned constant per rule branch | a calibrated probability |

That last row matters: `confidence` is not learned or estimated. Each rule returns a fixed number the author assigned to it (0.8 for a dawn chorus match, 0.3 for a fallback). It ranks rules by how specific they are — nothing more.

### `events.json` schema

One file per recording, media paths relative to that file's directory.

```jsonc
{
  "filename": "20250310_053000.WAV",
  "recording_datetime": "2025-03-10T05:30:00",   // null if unparseable
  "duration_s": 100.0,
  "sample_rate": 48000,
  "habitat": "Lagunas, lagos y ciénagas naturales",  // from directory name
  "season": "Época lluvias",
  "temperature_c": 24.5,                          // AudioMoth header, may be null
  "indices":   { "aci": …, "bio": …, "ndsi": …, "adi": …, "aei": … },  // whole recording
  "band_energies": { "geophony": …, "biophony_low": … },               // event mean
  "parliament": { "total_voices": …, "domain_percentages": {…},
                  "role_counts": {…}, "democracy_index": …,
                  "niche_partitioning": … },
  "n_events": 6,
  "n_clips": 6,
  "events": [{
    "event_index": 3,
    "onset_s": 40.8, "offset_s": 45.8, "duration_s": 5.0,
    "clip_start_s": 20.8, "clip_end_s": 55.8,   // includes pre/post-roll
    "peak_flux": …, "mean_flux": …,
    "centroid": 5412.0,        // Hz, magnitude-weighted, whole-spectrum
    "flatness": 0.081,         // 0-1, whole-spectrum
    "band_energies": { … },    // per band, this event's frames only
    "role": "dawn_chorus_participant",
    "domain": "biophony",
    "confidence": 0.8,         // fixed per rule — see caveat above
    "dominant_band": "biophony_mid",
    "reasoning": "Mid-frequency activity during dawn hours (h=5)",
    "aci": …, "bio": …, "ndsi": …, "adi": …, "aei": …,
    "clip_path": "clips/biophony/dawn_chorus_participant/event_003_….wav",
    "video_path": "…mp4", "poster_path": "…png",
    "thumbnail_path": "…png", "gif_path": ""
  }]
}
```

`phenological_series.csv` is one row per day: the raw fields, then `cv_*` copies of each scaled to 0–1 across the dataset. `phenological_calendar.json` holds the same frames plus the detected phases and the normalization ranges used.

### Known biases to design around

1. **Detection is change-driven, not presence-driven.** A cicada that sings continuously for an hour produces one event at onset and nothing after. Absence of events is not absence of sound — it is absence of *change*. Any model trained on these clips inherits a sampling bias toward onsets and transitions.
2. **Transition rules pre-empt content rules.** The first event of a new regime is labelled `silence_to_activity` or `activity_to_silence` regardless of source. In the verification corpus that swallowed most rain onsets.
3. **Some roles never fire at current thresholds.** `rain_event`, `wind_event`, `water_flow`, `mechanical_intrusion` and `aircraft_passage` were emitted zero times across 45 events, for the feature reasons documented earlier. Do not read a zero count as an absence of rain.
4. **Diel rules depend on a correct clock.** Roles keyed to hour-of-day are only as good as the AudioMoth's timestamp, and the wrong timezone silently relabels a dawn chorus as nocturnal.
5. **Class imbalance is severe and site-specific.** 11 of 45 events in the test corpus were one role.
6. **Ultrasound is absent unless asked for.** Anything trained on default-mode output has never seen a bat.

### A reasonable path to a trained model

1. Run detection at `--sensitivity subtle` to over-segment — better to discard than to miss.
2. Use `dominant_band` and the numeric features as the trustworthy layer; treat `role` as a pre-sort for annotation, not a label.
3. Have a human verify clips in gallery order — grouping by role means an annotator confirms or rejects one hypothesis at a time, which is much faster than labelling from scratch.
4. Calibrate the thresholds at the top of `classifier.py` against those verified labels; re-running detection is cheap compared with re-annotating.
5. Keep the phenological CSV as a **held-out validation signal** — a model that cannot reproduce a known dry-to-wet transition is not modelling the site.

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
- **A drawtext-capable ffmpeg**, if you want captions burned into the clip videos. Homebrew's stock `ffmpeg` bottle is built without libfreetype and therefore has no `drawtext` filter, so labels are silently unavailable — spectrogram, legend, colours and audio are unaffected. `brew install ffmpeg-full` provides it; the toolkit prefers that build automatically, or set `FFMPEG_BIN=/path/to/ffmpeg` to choose your own.
- Python packages (installed automatically into the managed venv): `numpy`, `scipy`, `soundfile`, `metamoth`, `python-osc`.
- **Optional:** `alp-data` (Python 3.11+), only for `./bioacoustics.sh validate`. Nothing else imports it, and the command tells you how to install it if missing.

`./bioacoustics.sh doctor` reports on all of the above.

---

## Troubleshooting

**"Python 3.10 or newer is required but was not found."**
Install a newer interpreter (`brew install python@3.12`) and run again. The launcher searches `python3.14` down to `python3.10`, then `python3`, and also looks inside `/opt/homebrew/bin` and `/usr/local/bin` in case Homebrew is not on your `PATH`. It will not use macOS's system 3.9.

**Videos render but carry no caption.**
Your ffmpeg has no `drawtext` filter — it was built without libfreetype, which is the case for Homebrew's current stock bottle. `./bioacoustics.sh doctor` shows which filters your build has. The clip's role, confidence, band, habitat and date are still in the filename, the gallery card, the report and `events.json`; only the burned-in text is missing. To get it:

```bash
brew install ffmpeg-full     # keg-only; the toolkit finds and prefers it
# or
export FFMPEG_BIN=/path/to/an/ffmpeg-with-drawtext
```

**No spectrogram videos appeared.**
ffmpeg is missing — the run says so as it goes and produces everything else. Install it and re-run `detect` on the same input: media is rendered during detection, so there is no separate render step to resume. The clips and JSON from the first pass are simply overwritten.

**"No WAV files found in: …"**
The path is checked as given, relative to where you are standing (not to the repo). Quote paths containing spaces or accents: `./detect_events.sh "Epoca lluvias/Bosque de galería y-o ripario/"`. Both `.WAV` and `.wav` are found, recursively.

**Too many or too few events.**
Start with `--sensitivity subtle | balanced | salient`, and only reach for `--threshold` (MAD units — lower is more sensitive) if the presets do not land where you want. `--min-event-duration` discards brief blips; `--merge-gap` decides how far apart two triggers must be to count as separate events. Probe with `--json-only` first — same analysis, none of the rendering. See [Event detection](#event-detection) for what κ actually measures.

**"Only one recording — the calendar needs several to compare."**
Phenology is a cross-recording product. It needs recordings from at least two different days, each carrying a parseable timestamp — either an AudioMoth `YYYYMMDD_HHMMSS.WAV` filename or intact AudioMoth metadata. The run reports how many of your files have usable timestamps.

**Nothing arrives at the instrument.**
Check the target with `--host` and `--port` (default `127.0.0.1:57120`, SuperCollider's default). `osc serve` listens on `--listen-port` (default 57121) and *replies* to `--host`/`--port`, which can be redirected at runtime by sending `/phenology/query/reply_port <int>`. `cat osc_address_map.txt` for the exact addresses your results emit.

**A gallery link opens nothing.**
Media paths inside `events.json` are stored relative to each recording's folder, so the whole output tree can be moved or published as a unit — but moving `gallery.html` on its own breaks its links. Regenerate it in place with `./bioacoustics.sh gallery <output_dir>`.

**An old script printed a note about a new command.**
That's expected. The seven retired scripts still work; they forward to the pipeline and name their replacement. See [Replaced scripts](#replaced-scripts).
