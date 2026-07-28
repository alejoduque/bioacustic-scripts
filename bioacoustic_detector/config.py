"""
All tunable parameters for the bioacoustic event detector.
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
class VideoConfig:
    """Spectrogram video generation parameters (mirrors make-spectrogram-movie-fixed.sh)."""
    width: int = 996
    height: int = 592
    dynamic_range: int = 72
    max_freq: int = 10000
    min_freq: int = 0
    freq_scale: str = "lin"
    gain_scale: str = "log"
    color: str = "cool"
    slide: str = "scroll"
    legend: str = "enable"
    # Encoding
    video_codec: str = "libx264"
    video_preset: str = "medium"
    video_crf: int = 23
    audio_codec: str = "aac"
    audio_bitrate: str = "128k"


@dataclass
class OSCConfig:
    """OSC output parameters."""
    host: str = "127.0.0.1"
    port: int = 57120  # SuperCollider default
    live: bool = False


@dataclass
class Config:
    """Master configuration combining all sub-configs."""
    spectral: SpectralConfig = field(default_factory=SpectralConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    osc: OSCConfig = field(default_factory=OSCConfig)

    output_dir: str = "./detected_events"
    no_video: bool = False
    json_only: bool = False
    no_osc: bool = False
    phenology: bool = False
