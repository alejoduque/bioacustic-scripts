"""
STFT and spectral feature extraction for bioacoustic analysis.

Features: spectral flux (half-wave rectified L2), spectral centroid,
spectral flatness (Wiener entropy), and band energies for 6 ecological bands.
"""

import numpy as np
from scipy.signal import resample_poly, get_window
from math import gcd

from .config import SpectralConfig


def downsample(audio: np.ndarray, sr: int, target_sr: int) -> tuple[np.ndarray, int]:
    """Downsample audio to target sample rate using polyphase resampling."""
    if sr <= target_sr:
        return audio, sr
    g = gcd(sr, target_sr)
    up = target_sr // g
    down = sr // g
    return resample_poly(audio, up, down).astype(np.float64), target_sr


def stft(audio: np.ndarray, frame_size: int, hop_size: int,
         window: str = "hann") -> np.ndarray:
    """
    Compute the Short-Time Fourier Transform.

    Returns complex spectrogram of shape (n_frames, n_fft_bins)
    where n_fft_bins = frame_size // 2 + 1.
    """
    win = get_window(window, frame_size, fftbins=True)
    n_samples = len(audio)
    n_frames = 1 + (n_samples - frame_size) // hop_size

    # Pre-allocate
    n_fft = frame_size // 2 + 1
    S = np.empty((n_frames, n_fft), dtype=np.complex128)

    for i in range(n_frames):
        start = i * hop_size
        frame = audio[start:start + frame_size] * win
        S[i] = np.fft.rfft(frame)

    return S


def magnitude_spectrum(S: np.ndarray) -> np.ndarray:
    """Magnitude spectrum from complex STFT."""
    return np.abs(S)


def power_spectrum(S: np.ndarray) -> np.ndarray:
    """Power spectrum from complex STFT."""
    return np.abs(S) ** 2


def spectral_flux(mag: np.ndarray) -> np.ndarray:
    """
    Half-wave rectified L2-norm spectral flux.

    Measures the rate of spectral change between consecutive frames.
    """
    diff = np.diff(mag, axis=0)
    # Half-wave rectification: only positive changes (new energy)
    diff = np.maximum(diff, 0)
    flux = np.sqrt(np.sum(diff ** 2, axis=1))
    # Prepend 0 for first frame
    return np.concatenate([[0.0], flux])


def spectral_centroid(mag: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """
    Spectral centroid — the "center of mass" of the spectrum.
    Returns frequency in Hz per frame.
    """
    mag_sum = np.sum(mag, axis=1)
    mag_sum = np.where(mag_sum == 0, 1.0, mag_sum)  # avoid division by zero
    return np.sum(mag * freqs[np.newaxis, :], axis=1) / mag_sum


def spectral_flatness(mag: np.ndarray) -> np.ndarray:
    """
    Spectral flatness (Wiener entropy).
    Ratio of geometric mean to arithmetic mean of the power spectrum.
    1.0 = white noise, 0.0 = pure tone.
    """
    pwr = mag ** 2
    # Add tiny epsilon to avoid log(0)
    eps = 1e-20
    pwr = np.maximum(pwr, eps)

    geo_mean = np.exp(np.mean(np.log(pwr), axis=1))
    arith_mean = np.mean(pwr, axis=1)
    arith_mean = np.where(arith_mean == 0, 1.0, arith_mean)
    return geo_mean / arith_mean


def band_energies(mag: np.ndarray, freqs: np.ndarray,
                  bands: dict, sr: int) -> dict[str, np.ndarray]:
    """
    Compute energy in ecological frequency bands.

    Returns dict mapping band name to energy time series.
    Bands whose upper frequency exceeds Nyquist are zeroed out.
    """
    nyquist = sr / 2.0
    energies = {}
    for name, (lo, hi) in bands.items():
        if lo >= nyquist:
            energies[name] = np.zeros(mag.shape[0])
            continue
        hi = min(hi, nyquist)
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            energies[name] = np.zeros(mag.shape[0])
        else:
            energies[name] = np.sum(mag[:, mask] ** 2, axis=1)
    return energies


def compute_freq_axis(frame_size: int, sr: int) -> np.ndarray:
    """Compute frequency values for each FFT bin."""
    n_fft = frame_size // 2 + 1
    return np.linspace(0, sr / 2, n_fft)


def analyze(audio: np.ndarray, sr: int,
            config: SpectralConfig | None = None) -> dict:
    """
    Run full spectral analysis on audio.

    Returns dict with keys:
        - flux: spectral flux time series
        - centroid: spectral centroid (Hz) per frame
        - flatness: spectral flatness per frame
        - band_energies: dict of band name -> energy time series
        - magnitude: magnitude spectrogram (n_frames, n_fft)
        - freqs: frequency axis
        - sr: sample rate used for analysis
        - hop_size: hop size used
        - frame_times: time in seconds for each frame
    """
    if config is None:
        config = SpectralConfig()

    # Mono
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    # Downsample for detection
    audio_ds, sr_ds = downsample(audio, sr, config.target_sr)

    # STFT
    S = stft(audio_ds, config.frame_size, config.hop_size, config.window)
    mag = magnitude_spectrum(S)
    freqs = compute_freq_axis(config.frame_size, sr_ds)

    n_frames = mag.shape[0]
    frame_times = np.arange(n_frames) * config.hop_size / sr_ds

    return {
        "flux": spectral_flux(mag),
        "centroid": spectral_centroid(mag, freqs),
        "flatness": spectral_flatness(mag),
        "band_energies": band_energies(mag, freqs, config.bands, sr_ds),
        "magnitude": mag,
        "freqs": freqs,
        "sr": sr_ds,
        "hop_size": config.hop_size,
        "frame_times": frame_times,
    }
