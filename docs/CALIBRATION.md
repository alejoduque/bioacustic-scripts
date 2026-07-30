# Field calibration protocol

**English** · [Español](CALIBRACION.md) · [← README](../README.md)

Everything in this toolkit has so far been verified on **synthetic audio** written to exercise specific code paths. That proves the pipeline does what it claims mechanically. It says nothing about whether the ecological thresholds are right for any real site.

This document is the plan for closing that gap once recordings from the tropical dry forest are available. It is written to be reproducible and citable: each step states what is measured, what is decided from it, and what would falsify the decision.

Two things are open. Everything else follows from them.

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
