# Field calibration protocol

**English** · [Español](CALIBRACION.md) · [← README](../README.en.md)

Everything in this toolkit has so far been verified on **synthetic audio** written to exercise specific code paths. That proves the pipeline does what it claims mechanically. It says nothing about whether the ecological thresholds are right for any real site.

This document is the plan for closing that gap once recordings from the tropical dry forest are available. It is written to be reproducible and citable: each step states what is measured, what is decided from it, and what would falsify the decision.

Two things are open. Everything else follows from them.

---

## First field recordings (Manakai, October 2024)

The first real AudioMoth data from the study site: 2.2 hours, six of seven files
recorded at **192 kHz** — a deliberate ultrasonic deployment. Two 60-minute
dawn files (04:00, 05:00), plus shorter excerpts the recordist had already named
`paso murcielagos` (bat pass) and `buho` (owl). Those names are informal labels,
and they made two things testable immediately.

**What worked.** On the file named as a bat pass, ultrasonic mode detected
`bat_echolocation` in `ultrasonic_mid` at 102.7 s and 111.3 s — brief events,
1.7 s and 3.8 s. That is the first confirmation of ultrasonic mode against a
human-identified recording rather than a synthetic fixture.

**What broke, and how it was found.** The file named for an owl produced eight
`bat_echolocation` events, two of them lasting **36 and 40 seconds**. No bat
echolocates for 36 seconds. Rendering those events and looking at them settled
it: they are unbroken horizontal bands at 17-30 kHz — a **katydid chorus**.
Genuine echolocation is visible in the same recording as brief vertical sweeps
above 40 kHz, but it is not what carries the band's energy.

The rule was the problem, and it was the same error as the geophony one in the
opposite direction: it assigned `bat_echolocation` to *any* event whose dominant
band was ultrasonic, including the branch that explicitly returned "sustained
ultrasonic activity - a foraging bout". In a neotropical forest the 16-40 kHz
band is occupied continuously by stridulating insects that are far louder in
aggregate than any bat. The band table's own comment said katydids live there;
the rule ignored it.

**The fix, from the images rather than from a guess.** Duration separates them —
a pass lasts one to three seconds, a chorus runs for minutes. Sustained
ultrasonic energy (>10 s) now classifies as `insect_chorus`; brief events remain
`bat_echolocation` but at 0.5 confidence with reasoning that says the same band
carries katydids and the call needs verifying. On the owl file this moved five
events from bat to insect and left the genuinely brief ones alone.

**Still open.** Telling a katydid from a bat *within* a short ultrasonic event
needs the pulse-structure work that is currently blocked on modulation
resolution. Until then, treat `bat_echolocation` as a candidate list to review,
not a count.

**A practical limit found at the same time.** The two 60-minute 192 kHz files
cannot be processed as-is: at the native rate with a 256-sample hop they need
about 11 GB for the magnitude array plus 5.5 GB for the audio, against 17 GB of
RAM. Analysis currently holds the whole spectrogram in memory. Long ultrasonic
recordings need either chunked processing or analysis in slices.

---

### Tuned settings for Manakai (2026-07-31)

Swept threshold × merge-gap over 2.1 hours of raw recordings — both 60-minute
dawn files and the dusk file, streamed once each and re-detected against the
cached series, so 35 combinations cost barely more than one pass.

The first sweep found **nothing workable**, which was informative: it judged
threshold by clips-per-hour, and in the fixed-window pipeline those are
independent controls.

  threshold + merge_gap  decide WHERE events are and how long they run
  min_separation         decides HOW MANY of them become clips

Separated, the answer is clear. For event geometry — an event should fit inside
the 60 s clip meant to hold it, and coverage should stay well below 100 % or the
detector is only reporting that sound exists:

| κ | merge gap | events/h | median | p90 | coverage |
|---|---|---|---|---|---|
| 2.5 | 1.0 s | 24 | 7.4 s | 499 s | 98 % |
| 4.0 | 0.25 s | 441 | 1.2 s | 13.4 s | 84 % |
| 6.0 | 0.25 s | 668 | 0.9 s | 5.9 s | 64 % |
| **8.0** | **0.25 s** | **619** | **0.9 s** | **5.8 s** | **46 %** |
| 12.0 | 0.25 s | 498 | 0.8 s | 3.6 s | 24 % |

κ = 8.0 with a 0.25 s merge gap is the most sensitive setting that keeps events
bounded and distinguishable — available as `--sensitivity dense`. Note that
raising κ past 6 *increases* the event count before it falls: a lower threshold
merges neighbouring calls into one long event rather than finding more of them.

Then separation sets the review budget independently, at that fixed geometry:

| `--min-separation` | clips/h | review time per hour recorded |
|---|---|---|
| 30 s | 91 | 91 min — more clip than recording |
| 120 s | 28 | 28 min |
| **300 s** | **12** | **12 min — a 5:1 compression** |
| 600 s | 6 | 6 min |

Recommended for this site:

```bash
./detect_events.sh <recordings>/ --ultrasonic --sensitivity dense \
    --clip-duration 60 --clip-pre 30 --min-separation 300
```

On one dawn hour that yields 548 bounded events (median 0.8 s, max 47 s) and 12
one-minute clips, against 12 events of median 108 s and max 1780 s at the
defaults. It does **not** fix the classification: 393 of those 548 still fall
through to `community_shift`, and the 116 `bat_echolocation` events remain
candidates rather than counts, for the reasons in the sections above.

---

## Open item 1 — Recorder sample rate must be chosen before deployment

**The decision.** What AudioMoth sample rate to deploy at, per site and per season.

**Why it cannot be deferred.** Sampling at rate *fs* represents frequencies only up to Nyquist = *fs*/2. Above that, energy does not disappear — it **aliases**, folding to `|fs − f|` and appearing at a frequency that was never present. Nothing downstream can detect that this happened, and no reprocessing can undo it. A card recorded at the wrong rate is permanently missing the band you did not choose.

This is not theoretical. While building the test corpus a synthetic 105 kHz caller was written into a 192 kHz file; it appeared at 87 kHz and was classified from that phantom frequency, with no warning anywhere in the pipeline.

| Rate | Nyquist | Reaches | Misses | Cost |
|---|---|---|---|---|
| 48 kHz | 24 kHz | birds, anurans, orthopterans | essentially all echolocation | 1× |
| 96 kHz | 48 kHz | + Molossidae, some Vespertilionidae | high Phyllostomidae | 2× |
| 192 kHz | 96 kHz | + nearly all neotropical echolocation | the highest CF species | 4× |
| 256 / 384 kHz | 128 / 192 kHz | everything expected in the Neotropics | — | 5–8× |

Cost is storage, battery and analysis time together — a 192 kHz deployment fills a card four times faster and shortens battery life correspondingly.

**Protocol.**

1. **Pilot before committing.** Deploy at least one unit at 192 kHz for a full night at each habitat type, alongside the 48 kHz units.
2. **Measure occupancy, not presence.** Run `--ultrasonic` on the pilot and read the per-band energies from `events.json`. The question is not "are there bats" (there are) but *which bands carry energy*, and how often.
3. **Decide per habitat.** If `ultrasonic_high` (80–160 kHz) is consistently empty, 192 kHz is sufficient and 96 kHz may be. If it is occupied, 192 kHz is the floor.
4. **Record the decision and its evidence** in the deployment metadata, so a later reader can tell an absent species from an unrepresentable one.

**What would falsify it.** Energy piled against the top of the plot with no structure below it — a signature of aliasing rather than of a high-frequency caller. If that appears, re-record the same site one rate higher and compare; genuine content moves to its true frequency, an alias moves somewhere else entirely.

**Deployment hygiene that costs nothing and cannot be fixed later:**

- **Set the clock and the timezone.** Every diel rule (dawn chorus, nocturnal, dusk) keys on the AudioMoth timestamp. A wrong timezone silently relabels a dawn chorus as nocturnal, and the error is invisible in the output.
- **Cover dawn every day.** Dawn onset is defined as the first biophonic event between 03:00 and 08:00. A duty cycle that skips a morning produces a spurious "delay" indistinguishable from a real phenological shift.
- **Keep the directory convention.** Habitat and season are parsed from the path (`Época lluvias/Bosque de galería y-o ripario/`). It is the only place that information enters the analysis.

---

## First external results (2026-07-30, before any field data)

Item 2 no longer has to wait for La Luna. `alp-data` exposes **AnuraSet** — 27 h of expert-annotated neotropical anurans from two Brazilian biomes — and the detector can be scored against it today:

```bash
~/.bioacoustic_detector_venv/bin/pip install alp-data     # optional dependency
./bioacoustics.sh validate --dataset anuraset --limit 25 --sweep
```

**25 recordings, 266 expert annotations** (median 0.61 s, 75 % shorter than 2 s).

| | config | detections | precision | recall | F1 |
|---|---|---|---|---|---|
| Defaults | κ=2.5, min 2 s, merge 5 s | 30 | 0.57 | 0.06 | **0.11** |
| Best of sweep | κ=3, min 0.25 s, merge 0.25 s | 399 | 0.23 | 0.35 | **0.28** |

Onset-matched at ±0.5 s, one-to-one. Three things follow.

**1. The default timings cannot match this corpus, by construction.** 75 % of annotations are shorter than `min_event_duration = 2 s`. Recall of 0.06 at defaults is a units mismatch, not a detector failure — we answer "when did the soundscape change?", the annotators answered "where is every call?". Tuning to call scale improves F1 2.4×, and precision/recall trade smoothly across the grid (κ=1.5, min 0.1 s reaches recall 0.61 at precision 0.14).

**2. F1 ≈ 0.28 is the honest ceiling of a generic change detector on dense chorus.** It is a baseline to beat, not a result to defend. A model trained for the task would do far better; that is the argument for the learned-feature route.

**3. The classifier finding is the important one — and it invalidates an assumption, not a threshold.**

Of the 17 detections that matched an annotation under default settings, **16 were assigned `dominant_band = geophony`**, and therefore fell through every biophonic rule to `community_shift`. Domain accuracy against a corpus that is *entirely anuran*: **6 %**.

The cause is the band table itself. `geophony` is defined as 0–2 kHz, but on these recordings the sub-2 kHz band holds 97 % of the energy — whether from frogs calling low, from water and wind near the ponds, or both. **Band energy alone cannot separate a frog from a stream**, so a rule keyed on the dominant band will assign geophony to an anuran chorus every time.

This could not have been found on synthetic audio. The synthetic "amphibians" in the test corpus were generated at 2.6–3.1 kHz — inside `biophony_low` — because that is what the band table assumes. The fixture and the code encoded the same assumption and agreed with each other. Only externally annotated recordings could break the tie.

**What this implies for the two candidate fixes below:** option (a), retuning thresholds, cannot repair this — no threshold on `flatness` or `centroid` recovers a distinction that the band table has already destroyed. The work is option (b), and specifically:

- compute flatness and centroid **within the dominant band**, so "noisy" is judged relative to the event rather than the whole spectrum
- add a **temporal-structure** feature. This is what actually separates the two cases: an anuran chorus is periodic at call rate, rain is not. Autocorrelation of the band envelope, or the modulation spectrum, would carry that and is cheap to compute from data already in memory.
- treat the low band as **ambiguous by default** rather than as geophony, and let the temporal feature resolve it

---

## Attempt at the fix, and what it established (2026-07-30)

The obvious response to the finding above is to add features that describe the
event's own band and its temporal structure. Both are now implemented and
recorded in `events.json`:

| Feature | Measures |
|---|---|
| `band_crest` | peak-to-mean of the mean spectrum within the dominant band |
| `band_entropy` | normalised entropy across that band's bins — spread vs concentrated |
| `band_centroid` | where inside its own band the energy sits |
| `periodicity` / `pulse_rate_hz` | amplitude modulation measured **within the event** |
| `context_periodicity` / `context_rate_hz` | the same over a ≥4 s window **around** the event |

**They are not wired into classification, and should not be until the
measurement below is repeated with the missing data.** Recording them costs
nothing and gives the eventual calibration real features to fit.

### Measured on 60 AnuraSet recordings

186 detections matching an expert anuran annotation, against 202 detections from
AnuraSet files carrying no annotation:

| | anuran (n=186) | unannotated (n=202) |
|---|---|---|
| `band_crest` median | 35.06 | 35.61 |
| `band_entropy` median | 0.271 | 0.214 |
| `periodicity` median | 0.000 | 0.112 |

**No separation. On periodicity the ordering is inverted.** At every threshold
tried, the negative class was retained at an equal or higher rate than the
positive one.

### Why this is inconclusive rather than a refutation

Three defects in the experiment, all identified from the numbers:

1. **The negative class contains no rain.** "AnuraSet files with no anuran
   annotation" are pond recordings at night; what is in them is largely
   *insects*, which are more tonal and far more regularly pulsed than frogs.
   That explains the inverted periodicity directly. The experiment compared
   frogs against other biophony, not against weather.
2. **A repetition rate cannot be measured inside a single repetition.** At a
   62.5 Hz frame rate a 0.25 s detection is 15 frames, too few to hold two
   cycles of anything slower than about 4 Hz. Measured directly: a synthetic
   3 Hz chorus scores 0.000 in a 0.25 s window, 0.675 at 0.5 s, and 1.000 from
   2 s upward. The median anuran `periodicity` of 0.000 is this artefact.
3. **The envelope frame rate caps what modulation is visible.** Sampling the
   band envelope every 512 samples resolves modulation only up to ~31 Hz, below
   typical anuran pulse rates. The within-event values cluster at 15.6 Hz, the
   edge of the search range — a sign of hitting the limit, not of measuring it.

An earlier version of the periodicity measure was also simply wrong, and the
fixture hid it: synthetic rain scored **0.93**, higher than any real chorus,
because it is generated as noise multiplied by a Hann window and a smooth
envelope autocorrelates near 1.0 at every lag. Detrending did not fix it —
normalised autocorrelation is scale-invariant, so shrinking the residual does
not make it less smooth. The measure now takes the *prominence of the first
local peak*, which tests the property that actually matters: a pulse train's
autocorrelation comes back up at the period, a swell's merely decays. The Hann
fixture now scores 0.000 and a 5 Hz pulse train 1.000.

### What is needed to finish this

- **A labelled geophony corpus.** `AudioSet` is registered in `alp-data` but
  ships no split paths, so it is not usable as-is. Rain and wind recordings with
  labels — ESC-50, FSD50K, or field recordings annotated at the site — would let
  the real comparison run. This is the blocker.
- **Modulation measured at the right resolution**, either from a finer hop for
  the envelope alone or from a proper modulation spectrum, so pulse rates above
  31 Hz are visible.
- **Then** fit thresholds, and re-run `validate` to confirm the domain accuracy
  of 6 % actually moves.

Until then the honest position is the one stated below: `dominant_band` and the
numeric features are trustworthy, `role` is a hypothesis.

---

## Open item 2 — Classifier thresholds are uncalibrated

**The decision.** The numeric thresholds at the top of `bioacoustic_detector/classifier.py` that map measured features onto ecological roles.

**The evidence that they need work.** Across the 45-event synthetic corpus, five of the sixteen roles were emitted **zero times**: `rain_event`, `wind_event`, `water_flow`, `mechanical_intrusion` and `aircraft_passage`. Geophonic content was present, correctly measured and clearly visible in the spectrograms — it simply never satisfied the rules.

Two properties of the features explain it, and both matter for how the fix is designed:

- **Spectral flatness is computed over the whole spectrum.** A signal that is perfectly noise-like *within its own band* still scores low when it occupies only part of the range. Band-limited rain (60–1900 Hz) measured **0.21 and 0.29** against a threshold of **0.30**. The measure answers "is this recording noisy?", not "is this event noisy?".
- **Spectral centroid is magnitude-weighted over the whole spectrum**, so a wide low-level noise floor drags it upward. The same rain events reported centroids of **6.5 and 7.7 kHz** despite having no energy at all above 2 kHz — which is why the anthrophony rule (`centroid < 1500`) missed them too.

Neither is an arithmetic error. Both are the documented behaviour of global spectral descriptors applied to band-limited events.

**Two candidate fixes, to be decided by the data, not in advance:**

- **(a) Retune the thresholds.** Cheapest, no code change beyond constants. Risks fitting one site's noise floor.
- **(b) Compute flatness and centroid *within the dominant band* as additional features**, keeping the global ones for comparability with published index literature. More faithful to what the rules are trying to express, and more likely to transfer between sites. Costs a small amount of code and invalidates nothing already recorded, since it adds fields rather than changing existing ones.

Option (b) is the more defensible for a thesis; option (a) is the right first move to see how far it gets.

**Protocol.**

1. **Over-segment deliberately.** Run at `--sensitivity subtle`. Missing an event cannot be recovered by annotation; a false positive can be discarded in seconds.

   ```bash
   ./detect_events.sh <recordings>/ -o ./calib --sensitivity subtle --phenology
   ```

2. **Annotate in gallery order.** `gallery.html` groups clips by proposed role, so an annotator confirms or rejects a single hypothesis at a time — far faster than labelling from scratch, and it makes disagreements between annotators visible as clusters.
3. **Record the human label alongside the machine label**, never replacing it. The pair (proposed, verified) is the measurement; the proposal alone is not.
4. **Target a minimum of ~50 verified events per role you intend to trust**, and be explicit about roles that cannot reach it. Some will not, and that is a finding rather than a failure.
5. **Fit the thresholds to the verified set**, then re-run detection — cheap, versus re-annotating.
6. **Report per-role precision and recall**, not overall accuracy. With this class imbalance (11 of 45 events were one role in the test corpus) overall accuracy is close to meaningless.
7. **Hold out the phenological series.** A calibration that cannot reproduce a known dry-to-wet transition at the site has fitted noise.

**What would falsify a calibration.** Thresholds that separate roles cleanly on one habitat and collapse on another indicate the feature, not the threshold, is wrong — which is the signal to move to option (b).

---

## Interpretation rules that hold until calibration is done

These are not provisional caveats to be forgotten; they are how the current output should be read in any analysis or publication.

| Field | Status | Use as |
|---|---|---|
| `onset_s`, `offset_s`, `duration_s` | measured | segmentation, ±1 frame |
| `band_energies`, `peak_flux` | measured | features, directly comparable |
| `dominant_band` | measured (argmax) | **the trustworthy categorical** |
| `aci`, `bio`, `ndsi`, `adi`, `aei` | measured, published definitions | features, comparable across studies |
| `domain` | inferred, 4 classes | defensible weak label |
| `role` | **inferred, uncalibrated** | a hypothesis to be verified |
| `confidence` | **hand-assigned constant** | rule specificity ranking, not a probability |

`confidence` in particular is neither learned nor estimated: each rule branch returns a fixed number chosen by the author. It ranks rules by how specific they are and must never be reported as a probability.

Two structural biases survive any threshold calibration and must be stated in any write-up:

1. **Detection is change-driven, not presence-driven.** A cicada singing continuously for an hour yields one event at onset and nothing after. Absence of events is absence of *change*, not absence of sound.
2. **Transition rules pre-empt content rules.** The first event of any new acoustic regime is labelled `silence_to_activity` or `activity_to_silence` regardless of source. In the test corpus this absorbed most rain onsets.

---

## Sequence once recordings arrive

1. Inventory: sample rates, date range, habitats, duty cycle, clock/timezone sanity → decides whether Item 1 is already fixed by what was recorded.
2. `--json-only` sweep at all three sensitivities to see event yield per habitat before committing to rendering.
3. Full run with media on a representative subset; annotate via the gallery.
4. Calibrate (Item 2), re-run, re-measure precision and recall per role.
5. Rebuild the phenological calendar and compare against known site events — first rains, observed chorus onsets, anything the field team recorded independently.
6. Only then treat `role` as a label, and only for the roles that earned it.
