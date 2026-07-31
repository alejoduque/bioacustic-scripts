"""
All tunable parameters for the bioacoustic toolkit.

Every feature exposed by the wizard (`bioacoustics.sh`) and the CLI
(`detect_events.sh`) is driven by these dataclasses, so a preset is just
a Config instance.
"""

from dataclasses import dataclass, field


# Audible-range band table. Bands are half-open [lo, hi) in Hz and are clipped
# to Nyquist at analysis time, so a 48 kHz recording simply reports zero energy
# in any band above 24 kHz rather than inventing content.
AUDIBLE_BANDS = {
    "geophony": (0, 2000),           # wind, rain, water, distant thunder
    "biophony_low": (2000, 4000),    # anurans, large mammals, dove/tinamou calls
    "biophony_mid": (4000, 8000),    # most passerine song, many orthopterans
    "biophony_high": (8000, 16000),  # cicadas, katydids, high passerines
    "ultrasonic": (16000, 24000),    # the low edge of bat calls, if SR allows
}

# Ultrasonic band table, used when analysing at the recorder's native rate.
# Splits chosen for neotropical dry-forest bat assemblages:
#   16-40 kHz   Molossidae (free-tailed bats), some Vespertilionidae, katydids
#   40-80 kHz   most Vespertilionidae and Phyllostomidae search-phase calls
#   80-160 kHz  high-frequency Phyllostomidae, terminal feeding buzzes
ULTRASONIC_BANDS = {
    "geophony": (0, 2000),
    "biophony_low": (2000, 4000),
    "biophony_mid": (4000, 8000),
    "biophony_high": (8000, 16000),
    "ultrasonic_low": (16000, 40000),
    "ultrasonic_mid": (40000, 80000),
    "ultrasonic_high": (80000, 160000),
}


@dataclass
class SpectralConfig:
    """STFT and spectral analysis parameters."""
    frame_size: int = 2048
    hop_size: int = 512  # 75% overlap
    window: str = "hann"

    # Recordings above target_sr are downsampled to it before detection, which
    # bounds cost and keeps time/frequency resolution matched to bird syllables.
    # Set to 0 to analyse at the recorder's native rate — required for bats,
    # since anything above target_sr/2 is otherwise discarded by the anti-alias
    # filter. See Config.ultrasonic.
    target_sr: int = 48000

    # Ecological frequency bands (Hz)
    bands: dict = field(default_factory=lambda: dict(AUDIBLE_BANDS))

    @property
    def analysis_window_s(self) -> float:
        """STFT window length in seconds at the given rate (see resolution())."""
        return self.frame_size / max(self.target_sr, 1)

    def resolution(self, sample_rate: int) -> tuple[float, float]:
        """(frequency resolution in Hz, time resolution in ms) at a given rate."""
        return (sample_rate / self.frame_size,
                1000.0 * self.hop_size / sample_rate)


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

    # Fixed-length clips anchored on the event onset, rather than the event
    # padded by pre/post-roll. Set fixed_duration_s to 60 with pre_s 30 to get
    # "30 seconds before the onset, 30 seconds after" — a uniform one-minute
    # clip whatever the event's own length. Without this a 40-second event
    # yields a 70-second file, and dense events yield near-duplicate clips.
    # 0 disables it and restores the pre/post-roll behaviour.
    fixed_duration_s: float = 0.0
    fixed_pre_s: float = 30.0

    # Minimum spacing between the onsets that earn a clip. With 60-second
    # windows, two events eight seconds apart produce two almost identical
    # files; this suppresses the second. Defaults to half the clip length.
    min_separation_s: float = 0.0

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
    # Size of the spectrogram area. With legend=enable ffmpeg pads axes, labels
    # and the dBFS bar around it, so these defaults yield a 1280x720 file.
    width: int = 996
    height: int = 592
    dynamic_range: int = 72
    max_freq: int = 10000
    # Below roughly 200 Hz a field spectrogram carries rumble, wind on the
    # case and DC drift, not signal — and on a log axis that dead range eats
    # a third of the plot height. Raised off zero so the space goes to the
    # frequencies the event actually occupies.
    min_freq: int = 200

    # Bracket the plot around the bands the event actually carried, rather
    # than the whole spectrum. band_lo_hz/band_hi_hz already span every band
    # holding a meaningful share of the event's energy (see
    # pipeline._event_freq_range), so the margin here only needs to add a
    # little breathing room, not manufacture context for a single narrow band.
    focus_on_event: bool = True
    # Asymmetric on purpose. Widening upward mostly adds noise floor, while
    # widening downward keeps anuran and low-passerine activity in view — the
    # content most easily lost when a louder high band sets the focus.
    focus_margin_octaves_up: float = 0.5
    focus_margin_octaves_down: float = 1.0

    # Width in pixels of the metadata column padded onto the right of the
    # frame. 0 removes the column.
    metadata_column_px: int = 360
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
    # Kept close together on purpose. At 24px against a 13px column the same
    # face reads as a different, brighter one: a 1-pixel outline is
    # proportionally much thinner on large glyphs, so the stroke looks bolder.
    header_font_size: int = 16
    date_font_size: int = 15
    label_font_size: int = 16
    column_font_size: int = 13
    column_line_spacing: int = 3

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

    # Analyse at the recorder's native rate and extend the band table to cover
    # bat echolocation. Only meaningful for recordings made above 48 kHz.
    ultrasonic: bool = False


def apply_ultrasonic(config: Config, adjust_timing: bool = True) -> Config:
    """
    Switch a Config into ultrasonic mode, in place.

    Four things have to change together, or bats stay invisible or unusable:
      1. no downsampling, so content above 24 kHz survives
      2. a band table that reaches past 16 kHz
      3. a shorter STFT window, because echolocation pulses are 1-10 ms and a
         2048-sample window at 192 kHz already spans 10.7 ms — a whole call
      4. event timing on a bat's scale rather than a chorus's: a pass is one to
         three seconds and passes are separated by seconds, so the audible
         defaults (merge anything within 5 s, discard anything under 2 s)
         collapse a night of foraging into one undifferentiated block

    Video framing (max frequency, log axis) is set per recording from its
    actual sample rate; see pipeline.video_config_for.

    Pass adjust_timing=False to keep detector timings the caller set explicitly.
    """
    config.ultrasonic = True
    config.spectral.target_sr = 0          # 0 = keep native rate
    config.spectral.bands = dict(ULTRASONIC_BANDS)
    config.spectral.frame_size = 1024
    config.spectral.hop_size = 256
    if adjust_timing:
        config.detector.merge_gap_s = 1.0
        config.detector.min_event_duration_s = 0.3
    return config


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
    "dense": {
        "threshold_factor": 8.0,
        "min_event_duration_s": 0.3,
        "merge_gap_s": 0.25,
        "description": "For continuously active soundscapes (dawn chorus, "
                       "insect-saturated nights) where the others merge "
                       "everything into one event.",
    },
}


def apply_sensitivity(detector: DetectorConfig, preset: str) -> DetectorConfig:
    """
    Apply a named sensitivity preset to a DetectorConfig in place.

    A note on `dense`, measured on 2.1 hours of Manakai dawn and dusk
    recordings. The threshold is in MAD units of the LOCAL flux, so it adapts
    to level — but not to how continuously a soundscape changes. In a dawn
    chorus the flux is not only loud but restlessly variable, so the adaptive
    baseline rises with it and ordinary settings never stop triggering: at the
    balanced default the 90th-percentile event ran 499 s and events covered
    98% of the recording, which is the detector saying only "sound exists".
    At threshold 8.0 with a 0.25 s merge gap the same recordings give a 90th
    percentile of 5.8 s and 46% coverage — events that fit inside their clip
    and stand apart from the background.
    """
    spec = SENSITIVITY_PRESETS.get(preset)
    if not spec:
        return detector
    detector.threshold_factor = spec["threshold_factor"]
    detector.min_event_duration_s = spec["min_event_duration_s"]
    detector.merge_gap_s = spec["merge_gap_s"]
    return detector
