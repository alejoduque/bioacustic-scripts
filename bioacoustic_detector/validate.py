"""
Cross-validation of the detector against externally annotated datasets.

The detector's thresholds were tuned by hand and verified only on synthetic
audio. This module measures them against recordings someone else annotated,
which is the only way to get precision and recall that are not circular.

Reference data comes from `alp-data` (Earth Species Project), which exposes
several strongly-labelled passive-acoustic datasets through one interface.
`alp-data` is an OPTIONAL dependency — nothing else in the toolkit imports this
module, and it explains how to install itself if missing.

    ./bioacoustics.sh validate --dataset anuraset --limit 40 --sweep

What is being measured
----------------------
Our detector answers "when did the soundscape change?", not "where is every
call?". Those are different questions, and comparing them naively produces
numbers that look like failure but are really a units mismatch:

  * In AnuraSet, 81% of expert annotations are shorter than 2 s — our default
    `min_event_duration`. At defaults we cannot match them even in principle.
  * Some files carry a single 60-second "bout" annotation covering the whole
    recording. Time-overlap precision against such a reference is trivially
    1.00 and means nothing.

So the primary metric here is **onset detection**: for each annotated onset,
did we fire within a tolerance? That is robust to the bout/call granularity
mismatch and is what a change detector can honestly be scored on. Overlap and
time-level metrics are reported alongside, with reference coverage included so
degenerate files are visible rather than silently inflating the score.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import numpy as np

from .config import DetectorConfig, SpectralConfig
from .detector import detect_events
from .spectral import analyze

INSTALL_HINT = (
    "Reference datasets need the optional 'alp-data' package:\n"
    "    ~/.bioacoustic_detector_venv/bin/pip install alp-data\n"
    "It requires Python 3.11+ and pulls in polars, pandas and librosa."
)

# Strongly-labelled datasets in alp-data — those carrying onset/offset times.
# Each entry names the alp_data class and the split to read.
REFERENCE_DATASETS: dict[str, dict] = {
    "anuraset": {
        "class": "AnuraSetStrong",
        "split": "all",
        "sample_rate": 32000,
        "expected_domain": "biophony",
        "expected_role": "amphibian_assembly",
        "notes": "27 h of expert-annotated neotropical anurans, 42 species, "
                 "two Brazilian biomes (Canas et al. 2023). The closest public "
                 "analogue to a tropical dry forest anuran assemblage.",
    },
    "powdermill": {
        "class": "Powdermill",
        "split": "all",
        "sample_rate": 32000,
        "expected_domain": "biophony",
        "expected_role": "",
        "notes": "Dawn chorus of North American passerines, hand-annotated.",
    },
}


@dataclass
class Interval:
    """One annotated or detected time span."""
    onset_s: float
    offset_s: float
    label: str = ""

    @property
    def duration_s(self) -> float:
        return max(0.0, self.offset_s - self.onset_s)


@dataclass
class Scores:
    """Counts and derived rates for one matching criterion."""
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def add(self, other: "Scores") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    def as_dict(self) -> dict:
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn,
                "precision": round(self.precision, 4),
                "recall": round(self.recall, 4),
                "f1": round(self.f1, 4)}


@dataclass
class FileResult:
    """Everything measured for one reference recording under one config."""
    filename: str
    duration_s: float
    n_reference: int
    n_detected: int
    reference_coverage: float   # fraction of the file the annotations span
    detected_coverage: float
    onset: Scores = field(default_factory=Scores)
    overlap: Scores = field(default_factory=Scores)
    time_precision: float = 0.0
    time_recall: float = 0.0


# --- matching ---------------------------------------------------------------

def match_onsets(detected: list[Interval], reference: list[Interval],
                 tolerance_s: float) -> Scores:
    """
    Greedy one-to-one matching of detected onsets to annotated onsets.

    Each annotation may claim at most one detection and vice versa, so a single
    detection covering ten calls counts once — it cannot inflate recall.
    Candidates are matched nearest-first, which is the standard event-based
    convention for sound event detection.
    """
    pairs = sorted(
        ((abs(d.onset_s - r.onset_s), di, ri)
         for di, d in enumerate(detected)
         for ri, r in enumerate(reference)
         if abs(d.onset_s - r.onset_s) <= tolerance_s),
        key=lambda p: p[0],
    )

    used_d: set[int] = set()
    used_r: set[int] = set()
    for _, di, ri in pairs:
        if di in used_d or ri in used_r:
            continue
        used_d.add(di)
        used_r.add(ri)

    return Scores(tp=len(used_r),
                  fp=len(detected) - len(used_d),
                  fn=len(reference) - len(used_r))


def _iou(a: Interval, b: Interval) -> float:
    lo = max(a.onset_s, b.onset_s)
    hi = min(a.offset_s, b.offset_s)
    inter = max(0.0, hi - lo)
    union = a.duration_s + b.duration_s - inter
    return inter / union if union > 0 else 0.0


def match_overlap(detected: list[Interval], reference: list[Interval],
                  min_iou: float = 0.2) -> Scores:
    """Greedy one-to-one matching by intersection-over-union."""
    pairs = sorted(
        ((_iou(d, r), di, ri)
         for di, d in enumerate(detected)
         for ri, r in enumerate(reference)
         if _iou(d, r) >= min_iou),
        key=lambda p: -p[0],
    )

    used_d: set[int] = set()
    used_r: set[int] = set()
    for _, di, ri in pairs:
        if di in used_d or ri in used_r:
            continue
        used_d.add(di)
        used_r.add(ri)

    return Scores(tp=len(used_r),
                  fp=len(detected) - len(used_d),
                  fn=len(reference) - len(used_r))


def time_level(detected: list[Interval], reference: list[Interval],
               duration_s: float, resolution_hz: int = 100
               ) -> tuple[float, float, float, float]:
    """
    Frame-level precision/recall plus the coverage of each mask.

    Coverage is returned so a reader can spot the degenerate case: when the
    reference spans the entire recording (AnuraSet does this whenever a species
    choruses continuously), time-level precision is 1.0 by construction and
    carries no information.
    """
    n = max(1, int(duration_s * resolution_hz))
    det = np.zeros(n, dtype=bool)
    ref = np.zeros(n, dtype=bool)

    for iv in detected:
        det[int(iv.onset_s * resolution_hz):int(min(iv.offset_s, duration_s) * resolution_hz)] = True
    for iv in reference:
        ref[int(iv.onset_s * resolution_hz):int(min(iv.offset_s, duration_s) * resolution_hz)] = True

    tp = float(np.sum(det & ref))
    precision = tp / max(float(det.sum()), 1.0)
    recall = tp / max(float(ref.sum()), 1.0)
    return precision, recall, float(ref.mean()), float(det.mean())


# --- reference loading ------------------------------------------------------

def load_reference_samples(dataset: str, limit: int = 20,
                           data_root: str = "", stride_sample: bool = True):
    """
    Yield (filename, audio, sample_rate, [Interval, ...]) from a reference set.

    Samples are taken at an even stride across the manifest rather than from the
    front, because these corpora are ordered by recording site — the first N
    rows would all come from one location and one night.
    """
    spec = REFERENCE_DATASETS.get(dataset)
    if spec is None:
        raise ValueError(f"Unknown reference dataset {dataset!r}. "
                         f"Available: {', '.join(REFERENCE_DATASETS)}")

    # The reference buckets are world-readable, but the cloud layer logs a
    # credentials warning per file before falling back to anonymous access.
    # Quiet it here rather than making the user read it 40 times.
    for noisy in ("alp_data", "gcsfs", "fsspec", "google"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    try:
        import alp_data
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise ImportError(INSTALL_HINT) from exc

    cls = getattr(alp_data, spec["class"])
    kwargs = {"split": spec["split"], "sample_rate": spec["sample_rate"]}
    if data_root:
        kwargs["data_root"] = data_root
    ds = cls(**kwargs)

    total = len(ds)
    if limit <= 0 or limit >= total:
        indices = range(total)
    elif stride_sample:
        step = total / limit
        indices = [int(i * step) for i in range(limit)]
    else:
        indices = range(limit)

    for idx in indices:
        row = ds[idx]
        audio = np.asarray(row["audio"], dtype="float64")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        # Not every dataset reports the rate back: Powdermill sets
        # row["sample_rate"], AnuraSetStrong does not. Both honour the rate we
        # asked for, so fall back to that rather than guessing.
        sr = int(row.get("sample_rate") or spec["sample_rate"])

        table = row["selection_table"]
        intervals = [
            Interval(onset_s=float(r["Begin Time (s)"]),
                     offset_s=float(r["End Time (s)"]),
                     label=str(r.get("Species", r.get("Annotation", ""))))
            for _, r in table.iterrows()
        ]
        intervals.sort(key=lambda iv: iv.onset_s)

        name = str(row.get("audio_file_name") or row.get("audio_path") or idx)
        yield Path(name).name, audio, sr, intervals


# --- evaluation -------------------------------------------------------------

def evaluate_config(spectral_result: dict, duration_s: float,
                    reference: list[Interval], detector: DetectorConfig,
                    filename: str, onset_tolerance_s: float,
                    min_iou: float) -> FileResult:
    """Score one detector configuration against one file's annotations."""
    events = detect_events(spectral_result["flux"],
                           spectral_result["frame_times"],
                           duration_s, detector)
    detected = [Interval(e.onset_s, e.offset_s) for e in events]

    t_prec, t_rec, ref_cov, det_cov = time_level(detected, reference, duration_s)

    return FileResult(
        filename=filename,
        duration_s=duration_s,
        n_reference=len(reference),
        n_detected=len(detected),
        reference_coverage=round(ref_cov, 4),
        detected_coverage=round(det_cov, 4),
        onset=match_onsets(detected, reference, onset_tolerance_s),
        overlap=match_overlap(detected, reference, min_iou),
        time_precision=round(t_prec, 4),
        time_recall=round(t_rec, 4),
    )


def parse_reference_datetime(filename: str):
    """
    Recover a timestamp from a reference filename.

    AnuraSet names files `SITE_YYYYMMDD_HHMMSS.wav`, so the diel rules — which
    key on hour of day — can be exercised exactly as they would be on AudioMoth
    data. Without this the classifier would default to midday for every file
    and the whole diel branch would go untested.
    """
    from datetime import datetime
    stem = Path(filename).stem
    parts = stem.split("_")
    for i in range(len(parts) - 1):
        try:
            return datetime.strptime(f"{parts[i]}_{parts[i + 1]}",
                                     "%Y%m%d_%H%M%S")
        except ValueError:
            continue
    return None


def classify_matched(spectral_result: dict, detected: list[Interval],
                     reference: list[Interval], tolerance_s: float,
                     recording_datetime, spectral: SpectralConfig) -> list[dict]:
    """
    Classify the detections that matched an annotation.

    Only matched detections are classified: an unmatched one has no ground
    truth to be scored against, and including them would measure the detector's
    false positives a second time under a different name.
    """
    from .classifier import classify_event

    frame_times = spectral_result["frame_times"]
    magnitude = spectral_result["magnitude"]
    n_frames = magnitude.shape[0]

    out = []
    prev_flux = None
    for d in detected:
        near = [r for r in reference if abs(r.onset_s - d.onset_s) <= tolerance_s]
        if not near:
            continue

        f0 = int(np.searchsorted(frame_times, d.onset_s))
        f1 = int(np.searchsorted(frame_times, d.offset_s))
        f0 = max(0, min(f0, n_frames - 1))
        f1 = max(f0 + 1, min(f1 + 1, n_frames))

        bands = {name: float(np.mean(series[f0:f1]))
                 for name, series in spectral_result["band_energies"].items()}
        peak_flux = float(np.max(spectral_result["flux"][f0:f1]))

        cls = classify_event(
            d.onset_s, d.offset_s,
            float(np.mean(spectral_result["centroid"][f0:f1])),
            float(np.mean(spectral_result["flatness"][f0:f1])),
            peak_flux, bands,
            recording_datetime=recording_datetime,
            prev_event_flux=prev_flux, config=spectral,
        )
        prev_flux = peak_flux
        out.append({"role": cls.role, "domain": cls.domain,
                    "dominant_band": cls.dominant_band,
                    "reference_label": near[0].label})
    return out


def default_grid() -> list[DetectorConfig]:
    """
    Parameter grid spanning chorus scale down to individual-call scale.

    The default settings sit at the coarse end on purpose (they are tuned for
    "a new voice joined the soundscape"), so a sweep that only explored around
    them would never reach the granularity these reference corpora annotate at.
    """
    grid = []
    for kappa in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        for min_dur, merge in ((0.1, 0.1), (0.25, 0.25), (0.5, 0.5),
                               (1.0, 1.0), (2.0, 5.0)):
            grid.append(DetectorConfig(threshold_factor=kappa,
                                       min_event_duration_s=min_dur,
                                       merge_gap_s=merge))
    return grid


def label_of(cfg: DetectorConfig) -> str:
    return (f"k={cfg.threshold_factor:g} min={cfg.min_event_duration_s:g}s "
            f"merge={cfg.merge_gap_s:g}s")


def run(dataset: str = "anuraset", limit: int = 20, sweep: bool = False,
        onset_tolerance_s: float = 0.5, min_iou: float = 0.2,
        data_root: str = "", spectral: SpectralConfig | None = None,
        configs: list[DetectorConfig] | None = None,
        progress: bool = True) -> dict:
    """
    Run the full cross-validation and return a report dict.

    The spectral analysis — by far the expensive step — runs ONCE per file and
    every configuration is scored against the cached result, so a 30-point
    sweep costs barely more than a single run.
    """
    spectral = spectral or SpectralConfig()
    if configs is None:
        configs = default_grid() if sweep else [DetectorConfig()]

    spec = REFERENCE_DATASETS[dataset]
    per_config: dict[str, list[FileResult]] = {label_of(c): [] for c in configs}
    files_seen = 0
    ref_durations: list[float] = []
    # Classification is scored for ONE configuration, and which one matters a
    # great deal: most role rules test duration, so scoring them on 0.1-second
    # events from a grid corner would fail every rule by construction and look
    # like a classifier problem. When sweeping, use the toolkit's own defaults —
    # "the events this tool actually produces" — rather than an arbitrary point
    # in the grid. With an explicit single config, score that one.
    classify_with = DetectorConfig() if sweep else configs[0]
    classifications: list[dict] = []

    for filename, audio, sr, reference in load_reference_samples(
            dataset, limit=limit, data_root=data_root):
        duration_s = len(audio) / sr
        if progress:
            print(f"  [{files_seen + 1}] {filename}  {duration_s:.0f}s  "
                  f"{len(reference)} annotations")

        result = analyze(audio, sr, spectral)
        ref_durations += [iv.duration_s for iv in reference]

        for cfg in configs:
            per_config[label_of(cfg)].append(
                evaluate_config(result, duration_s, reference, cfg, filename,
                                onset_tolerance_s, min_iou))

        if reference:
            events = detect_events(result["flux"], result["frame_times"],
                                   duration_s, classify_with)
            classifications += classify_matched(
                result, [Interval(e.onset_s, e.offset_s) for e in events],
                reference, onset_tolerance_s,
                parse_reference_datetime(filename), spectral)
        files_seen += 1

    if not files_seen:
        raise RuntimeError("No reference files were loaded.")

    summaries = []
    for cfg in configs:
        rows = per_config[label_of(cfg)]
        onset, overlap = Scores(), Scores()
        for r in rows:
            onset.add(r.onset)
            overlap.add(r.overlap)
        summaries.append({
            "config": label_of(cfg),
            "threshold_factor": cfg.threshold_factor,
            "min_event_duration_s": cfg.min_event_duration_s,
            "merge_gap_s": cfg.merge_gap_s,
            "n_detected": sum(r.n_detected for r in rows),
            "n_reference": sum(r.n_reference for r in rows),
            "onset": onset.as_dict(),
            "overlap": overlap.as_dict(),
            "time_precision": round(float(np.mean([r.time_precision for r in rows])), 4),
            "time_recall": round(float(np.mean([r.time_recall for r in rows])), 4),
        })

    summaries.sort(key=lambda s: -s["onset"]["f1"])

    roles: dict[str, int] = {}
    domains: dict[str, int] = {}
    bands: dict[str, int] = {}
    for c in classifications:
        roles[c["role"]] = roles.get(c["role"], 0) + 1
        domains[c["domain"]] = domains.get(c["domain"], 0) + 1
        bands[c["dominant_band"]] = bands.get(c["dominant_band"], 0) + 1
    expected_domain = spec.get("expected_domain", "")
    n_cls = len(classifications)

    return {
        "dataset": dataset,
        "dataset_notes": spec["notes"],
        "n_files": files_seen,
        "onset_tolerance_s": onset_tolerance_s,
        "min_iou": min_iou,
        "reference_annotation_duration": {
            "median_s": round(median(ref_durations), 3) if ref_durations else 0,
            "n": len(ref_durations),
            "fraction_under_2s": round(
                float(np.mean([d < 2 for d in ref_durations])), 3)
            if ref_durations else 0,
        },
        "mean_reference_coverage": round(float(np.mean(
            [r.reference_coverage for r in next(iter(per_config.values()))])), 4),
        "classification": {
            "config": label_of(classify_with),
            "n_matched_events_classified": n_cls,
            "expected_domain": expected_domain,
            "expected_role": spec.get("expected_role", ""),
            "domain_accuracy": round(
                domains.get(expected_domain, 0) / n_cls, 4) if n_cls else None,
            "role_accuracy": round(
                roles.get(spec.get("expected_role", ""), 0) / n_cls, 4)
            if n_cls and spec.get("expected_role") else None,
            "domains": dict(sorted(domains.items(), key=lambda kv: -kv[1])),
            "roles": dict(sorted(roles.items(), key=lambda kv: -kv[1])),
            "dominant_bands": dict(sorted(bands.items(), key=lambda kv: -kv[1])),
        },
        "results": summaries,
        "per_file": [
            {"config": label, "files": [
                {"filename": r.filename, "n_reference": r.n_reference,
                 "n_detected": r.n_detected,
                 "reference_coverage": r.reference_coverage,
                 "onset": r.onset.as_dict()} for r in rows]}
            for label, rows in per_config.items()
        ],
    }


def print_report(report: dict, top: int = 12) -> None:
    """Print the report as a table, with the caveats that make it readable."""
    ann = report["reference_annotation_duration"]
    print()
    print("=" * 78)
    print(f"Detector vs {report['dataset']}  —  {report['n_files']} recordings")
    print("=" * 78)
    print(f"  {report['dataset_notes']}")
    print()
    print(f"  Reference annotations : {ann['n']}, median {ann['median_s']:.2f}s, "
          f"{ann['fraction_under_2s']:.0%} under 2s")
    print(f"  Mean reference coverage: {report['mean_reference_coverage']:.0%} "
          f"of each recording")
    if report["mean_reference_coverage"] > 0.8:
        print("    ! The reference spans almost the whole recording, so "
              "time-level precision")
        print("      is near 1.0 by construction. Read the onset columns, not "
              "the time ones.")
    print(f"  Onset tolerance       : ±{report['onset_tolerance_s']}s"
          f"   |   overlap IoU ≥ {report['min_iou']}")
    print()

    header = (f"{'config':<34}{'det':>6}{'ref':>6}"
              f"{'onsetP':>8}{'onsetR':>8}{'onsetF1':>9}{'iouF1':>7}")
    print(header)
    print("-" * len(header))
    for row in report["results"][:top]:
        o = row["onset"]
        print(f"{row['config']:<34}{row['n_detected']:>6}{row['n_reference']:>6}"
              f"{o['precision']:>8.2f}{o['recall']:>8.2f}{o['f1']:>9.2f}"
              f"{row['overlap']['f1']:>7.2f}")

    best = report["results"][0]
    print()
    print(f"Best onset F1: {best['config']}  →  "
          f"P {best['onset']['precision']:.2f}  "
          f"R {best['onset']['recall']:.2f}  "
          f"F1 {best['onset']['f1']:.2f}")
    cls = report.get("classification", {})
    if cls.get("n_matched_events_classified"):
        print()
        print("-" * 78)
        print(f"Classification of the {cls['n_matched_events_classified']} matched "
              f"detections   [{cls['config']}]")
        print("-" * 78)
        if cls.get("domain_accuracy") is not None:
            print(f"  Domain '{cls['expected_domain']}' assigned: "
                  f"{cls['domain_accuracy']:.0%}")
        if cls.get("role_accuracy") is not None:
            print(f"  Role   '{cls['expected_role']}' assigned: "
                  f"{cls['role_accuracy']:.0%}")
        print("  Domains: " + ", ".join(f"{k} {v}" for k, v in cls["domains"].items()))
        print("  Roles  : " + ", ".join(f"{k} {v}" for k, v in cls["roles"].items()))
        print("  Bands  : " + ", ".join(f"{k} {v}" for k, v in
                                         cls.get("dominant_bands", {}).items()))
        print()
        print("  Every annotation in this corpus is an anuran, so the domain")
        print("  figure is a fair score. The role figure is not a simple error")
        print("  rate: the diel rules fire on hour-of-day, so a frog calling at")
        print("  04:00 is filed as a dawn chorus participant by design.")
        print("  Note that most role rules test duration, so this figure moves")
        print("  with the detector settings that produced the events.")

    print()
    print("Interpretation: the table above is DETECTION — did we fire when the")
    print("annotator marked something. Classification is scored separately and")
    print("only on detections that matched, since the rest have no ground truth.")


def write_report(report: dict, output_path: str) -> str:
    Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path
