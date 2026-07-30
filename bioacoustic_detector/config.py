"""
All tunable parameters for the bioacoustic toolkit.

Every feature exposed by the wizard (`bioacoustics.sh`) and the CLI
(`detect_events.sh`) is driven by these dataclasses, so a preset is just
a Config instance.
"""

from dataclasses import dataclass, field


@dataclass
class SpectralConfig:
    """STFT and spectral analysis parameters."""
    frame_size: int = 2048
    hop_size: int = 512  # 75% overlap
    window: str = "hann"
    target_sr: int = 48000  # Downsample recordings >48kHz to this for detection

    # Ecological frequency bands (Hz)
    bands: dict = field(default_factory=lambda: {
        "geophony": (0, 2000),        # wind, rain, water
        "biophony_low": (2000, 4000),  # amphibians, large mammals
        "biophony_mid": (4000, 8000),  # birds, many insects
        "biophony_high": (8000, 16000),  # insects, bats
        "ultrasonic": (16000, 24000),  # bats (if SR allows)
    })


@dataclass
class DetectorConfig:
    """Event detection parameters."""
    baseline_window_s: float = 60.0   # Seconds for adaptive baseline
    threshold_factor: float = 2.5     # MAD multiplier
    mad_scale: float = 1.4826         # MAD to std dev conversion (normal distribution)
    min_event_duration_s: float = 2.0
    merge_gap_s: float = 5.0          # Events within this gap are merged
    pre_roll_s: float = 20.0          # Seconds before onset in clip
    post_roll_s: float = 10.0         # Seconds after offset in clip
    max_clip_duration_s: float = 300.0  # 5 minutes max per clip


@dataclass
class ClipConfig:
    """
    How event clips are selected, laid out on disk, and rendered.

    This is where the toolkit's "one clip per event type" intent lives:
    clips are grouped into per-role (or per-domain) subdirectories so each
    kind of voice in the parliament has its own folder of video evidence.
    """
    # "role" -> clips/<domain>/<role>/, "domain" -> clips/<domain>/, "flat" -> clips/
    organize_by: str = "role"

    # Per-clip renders
    make_video: bool = True     # scrolling spectrogram MP4
    make_poster: bool = True    # static spectrogram PNG + thumbnail (gallery covers)
    make_gif: bool = False      # looping GIF preview

    # One concatenated video per event type ("what does a dawn chorus look like here?")
    make_reels: bool = True
    reel_max_clips: int = 24

    # Event selection filters (empty tuple = keep everything)
    roles: tuple = ()
    domains: tuple = ()
    min_confidence: float = 0.0


@dataclass
class VideoConfig:
    """
    Spectrogram render parameters.

    Defaults reproduce the look of the retired make-spectrogram-movie-fixed.sh,
    with per-domain colormaps layered on top so event types are visually
    distinguishable at a glance.
    """
    width: int = 996
    height: int = 592
    dynamic_range: int = 72
    max_freq: int = 10000
    min_freq: int = 0
    freq_scale: str = "lin"
    gain_scale: str = "log"
    color: str = "cool"          # fallback when style_by_domain is False
    slide: str = "scroll"
    legend: str = "enable"

    # Visual identity per acoustic domain (ffmpeg showspectrum colormaps)
    style_by_domain: bool = True
    domain_colors: dict = field(default_factory=lambda: {
        "biophony": "green",
        "geophony": "cool",
        "anthrophony": "fiery",
        "transition": "magma",
    })

    # Text overlays
    overlay_text: bool = True
    font_file: str = ""          # auto-detected when empty
    header_font_size: int = 24
    date_font_size: int = 20
    label_font_size: int = 20

    # Static poster / thumbnail (replaces make-spectrogram-thumbnail-fixed.sh)
    poster_width: int = 1280
    poster_height: int = 720
    poster_color: str = "fruit"
    thumb_width: int = 256
    thumb_height: int = 144

    # GIF preview
    gif_width: int = 480
    gif_fps: int = 12

    # Encoding
    video_codec: str = "libx264"
    video_preset: str = "medium"
    video_crf: int = 23
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"

    def color_for(self, domain: str) -> str:
        """Colormap to use for an event of the given acoustic domain."""
        if not self.style_by_domain:
            return self.color
        return self.domain_colors.get(domain, self.color)


@dataclass
class PhenologyConfig:
    """Phenological calendar parameters."""
    # Thresholds for detecting long-term acoustic shifts
    breeding_energy_ratio: float = 2.0   # x increase in bio_low+bio_high across days
    adi_shift: float = 0.5               # absolute ADI change flagged as niche shift
    geophony_event_jump: int = 3         # extra geophonic events flagged as rain onset
    dawn_shift_minutes: float = 15.0     # dawn chorus advance/delay threshold

    # Export
    write_csv: bool = True               # tidy CSV, one row per day
    normalize_for_cv: bool = True        # add 0..1 fields ready for control voltage


@dataclass
class OSCConfig:
    """
    OSC output parameters.

    Phenological data is the primary payload: a season of recordings is
    replayed as a time-compressed stream that an Eurorack / ILDA / SuperCollider
    rig can follow.
    """
    host: str = "127.0.0.1"
    port: int = 57120  # SuperCollider default
    live: bool = False

    namespace: str = "/parliament"
    phenology_namespace: str = "/phenology"

    # Phenology streaming: how fast the calendar plays back
    days_per_second: float = 1.0
    loop: bool = False

    # Bidirectional server (installations query/seek the calendar over OSC)
    serve: bool = False
    listen_host: str = "0.0.0.0"
    listen_port: int = 57121


@dataclass
class Config:
    """Master configuration combining all sub-configs."""
    spectral: SpectralConfig = field(default_factory=SpectralConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    clip: ClipConfig = field(default_factory=ClipConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    phenology: PhenologyConfig = field(default_factory=PhenologyConfig)
    osc: OSCConfig = field(default_factory=OSCConfig)

    output_dir: str = "./detected_events"
    no_video: bool = False
    json_only: bool = False
    no_osc: bool = False
    build_phenology: bool = False
    build_gallery: bool = True


# --- Sensitivity presets, surfaced by name in the wizard ---

SENSITIVITY_PRESETS: dict[str, dict] = {
    "subtle": {
        "threshold_factor": 1.5,
        "min_event_duration_s": 1.0,
        "merge_gap_s": 3.0,
        "description": "Many events. Catches quiet transitions; expect false positives.",
    },
    "balanced": {
        "threshold_factor": 2.5,
        "min_event_duration_s": 2.0,
        "merge_gap_s": 5.0,
        "description": "Default. Good yield on dawn/dusk choruses and weather onsets.",
    },
    "salient": {
        "threshold_factor": 4.0,
        "min_event_duration_s": 3.0,
        "merge_gap_s": 8.0,
        "description": "Only strong shifts. Few, high-confidence clips.",
    },
}


def apply_sensitivity(detector: DetectorConfig, preset: str) -> DetectorConfig:
    """Apply a named sensitivity preset to a DetectorConfig in place."""
    spec = SENSITIVITY_PRESETS.get(preset)
    if not spec:
        return detector
    detector.threshold_factor = spec["threshold_factor"]
    detector.min_event_duration_s = spec["min_event_duration_s"]
    detector.merge_gap_s = spec["merge_gap_s"]
    return detector
