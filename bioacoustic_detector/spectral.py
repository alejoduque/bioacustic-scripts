"""
STFT and spectral feature extraction for bioacoustic analysis.

Features: spectral flux (half-wave rectified L2), spectral centroid,
spectral flatness (Wiener entropy), and band energies for 6 ecological bands.
"""

import numpy as np
import soundfile as sf
from scipy.signal import find_peaks, get_window, resample_poly
from math import gcd

from .config import SpectralConfig


def downsample(audio: np.ndarray, sr: int, target_sr: int) -> tuple[np.ndarray, int]:
    """
    Downsample audio to target sample rate using polyphase resampling.

    target_sr of 0 (or any rate at or above the source) returns the audio
    untouched — that is how ultrasonic mode keeps everything above 24 kHz,
    which the anti-alias filter would otherwise remove for good.
    """
    if target_sr <= 0 or sr <= target_sr:
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


# --- within-band and temporal features -------------------------------------
#
# The global centroid and flatness answer "is this RECORDING noisy?", because
# they average across the whole spectrum. Validation against AnuraSet showed
# that is the wrong question: an anuran chorus below 2 kHz and rain below 2 kHz
# produce nearly the same global descriptors, so no threshold on them can tell
# a frog from a stream. These features ask about the event's own band, and about
# how its energy is organised in time — which is where the two genuinely differ.

def band_mask(freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Boolean mask selecting the FFT bins of one band."""
    return (freqs >= lo) & (freqs < hi)


def band_crest(mag: np.ndarray, mask: np.ndarray) -> float:
    """
    Peak-to-mean ratio of the mean spectrum within one band.

    High when the band's energy sits in a few narrow peaks (a call with a
    dominant frequency and harmonics), low when it is spread smoothly across
    the band (rain, wind, water).

    Used in preference to a within-band Wiener flatness, which is what this
    module tried first: the geometric mean underflows as soon as any bin is
    near zero — measured at 3e-10 against a band mean of 15 on real audio — so
    flatness saturated at 0 for anurans and background alike and separated
    nothing. Crest is a ratio of means and has no such failure mode.
    """
    if not np.any(mask) or mag.size == 0:
        return 0.0
    spectrum = np.mean(mag[:, mask], axis=0)
    mean = float(np.mean(spectrum))
    return float(np.max(spectrum) / mean) if mean > 0 else 0.0


def band_entropy(mag: np.ndarray, mask: np.ndarray) -> float:
    """
    Normalised Shannon entropy of the energy distribution across a band's bins.

    1.0 = energy spread evenly over the band (noise-like), 0.0 = all energy in
    one bin (pure tone). The stable counterpart to within-band flatness: it is
    computed on a normalised probability vector, so no bin can drag it to zero.
    """
    if not np.any(mask) or mag.size == 0:
        return 0.0
    spectrum = np.mean(mag[:, mask] ** 2, axis=0)
    total = float(np.sum(spectrum))
    n_bins = int(np.count_nonzero(mask))
    if total <= 0 or n_bins < 2:
        return 0.0
    p = spectrum / total
    p = p[p > 0]
    return float(-np.sum(p * np.log(p)) / np.log(n_bins))


def within_band_centroid(mag: np.ndarray, freqs: np.ndarray,
                         mask: np.ndarray) -> float:
    """Spectral centroid within one band, in Hz."""
    if not np.any(mask) or mag.size == 0:
        return 0.0
    band_mag = mag[:, mask]
    band_freqs = freqs[mask]
    total = np.sum(band_mag)
    if total <= 0:
        return float(np.mean(band_freqs))
    return float(np.sum(band_mag * band_freqs[np.newaxis, :]) / total)


def band_envelope(mag: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Per-frame energy within one band — the amplitude envelope of the band."""
    if not np.any(mask) or mag.size == 0:
        return np.zeros(mag.shape[0])
    return np.sum(mag[:, mask] ** 2, axis=1)


def envelope_periodicity(envelope: np.ndarray, frame_rate_hz: float,
                         min_rate_hz: float = 0.5,
                         max_rate_hz: float = 20.0) -> tuple[float, float]:
    """
    Strength and rate of periodic amplitude modulation.

    Returns (periodicity 0-1, pulse rate in Hz).

    This is the feature that separates a chorus from weather. A calling
    assemblage is a pulse train — individual calls repeat at a species-typical
    rate, and even overlapping callers leave strong modulation in the band
    envelope. Rain and wind are aperiodic: their envelope autocorrelation decays
    without a peak.

    Implemented as the normalised autocorrelation of the DETRENDED envelope,
    with the peak taken over lags corresponding to `min_rate_hz`..`max_rate_hz`.
    Returns (0, 0) when the event is too short to resolve the slowest rate,
    rather than reporting a spurious peak from one or two cycles.

    The strength is taken from the first prominent LOCAL PEAK of the
    autocorrelation, not from its maximum value. That distinction is the whole
    measure. Normalised autocorrelation is scale-invariant, so any smooth
    envelope — a shower fading in and out, a fixture windowed with a Hann taper —
    correlates near 1.0 at short lags no matter how small its variation is;
    detrending does not help, because it shrinks the residual without making it
    less smooth. What separates a pulse train from a smooth swell is that the
    former's autocorrelation *comes back up* at the period, and the latter's
    simply decays. Requiring a peak tests for exactly that, and the first
    qualifying peak gives the fundamental rate rather than one of its multiples.
    """
    n = len(envelope)
    if n < 8 or frame_rate_hz <= 0:
        return 0.0, 0.0

    min_lag = max(1, int(frame_rate_hz / max_rate_hz))
    max_lag = int(frame_rate_hz / min_rate_hz)
    # Need at least two full cycles of the slowest rate examined
    max_lag = min(max_lag, n // 2)
    if max_lag <= min_lag:
        return 0.0, 0.0

    # Detrend: remove variation slower than min_rate_hz
    trend_window = min(n, max(3, int(frame_rate_hz / min_rate_hz)))
    if trend_window > 1:
        kernel = np.ones(trend_window) / trend_window
        trend = np.convolve(envelope, kernel, mode="same")
        x = envelope - trend
    else:
        x = envelope - np.mean(envelope)

    x = x - np.mean(x)
    denom = float(np.dot(x, x))
    if denom <= 0:
        return 0.0, 0.0

    ac = np.correlate(x, x, mode="full")[n - 1:] / denom
    window = ac[min_lag:max_lag + 1]
    if window.size < 3:
        return 0.0, 0.0

    peaks, props = find_peaks(window, prominence=0.05)
    if peaks.size == 0:
        return 0.0, 0.0

    first = int(peaks[0])
    lag = first + min_lag
    # Report the peak's prominence, not its height: height inherits whatever
    # smooth correlation the envelope already had, prominence is the part that
    # is actually periodic.
    strength = float(np.clip(props["prominences"][0], 0.0, 1.0))
    return strength, float(frame_rate_hz / lag)


# A repetition rate cannot be measured inside a single repetition. At a 62.5 Hz
# frame rate a 0.25 s detection is 15 frames, which cannot hold two cycles of
# anything slower than ~4 Hz — measured periodicity was 0.000 for most real
# anuran detections for exactly this reason. Modulation is therefore measured
# over a context window around the event, not over the event alone.
MIN_PERIODICITY_WINDOW_S = 4.0


def event_band_features(mag: np.ndarray, freqs: np.ndarray,
                        band_range: tuple[float, float],
                        frame_rate_hz: float,
                        context_mag: np.ndarray | None = None) -> dict:
    """
    All within-band and temporal features for one event's dominant band.

    `mag` is the magnitude spectrogram restricted to the event's frames, and is
    what the spectral shape features (crest, entropy, centroid) describe.

    `context_mag` is a longer window around the event, used only for the
    temporal features. Call rate is a property of the sequence an event belongs
    to, not of the event: measuring it on a single 0.25 s call yields nothing at
    all. Falls back to `mag` when no context is supplied, which is correct for
    events already longer than MIN_PERIODICITY_WINDOW_S.
    """
    mask = band_mask(freqs, band_range[0], band_range[1])

    # Two time scales, because they measure different things and it is not yet
    # established which one carries the frog/weather distinction:
    #   periodicity          within the event — pulse structure inside a call
    #   context_periodicity  over a wider window — the repetition rate of calls
    # Measured on real anuran calls, the two disagree sharply (0.47 vs 0.06 on
    # the same events), so collapsing them into one number would throw away the
    # evidence needed to choose. Both are recorded; neither is yet used to
    # classify. See docs/CALIBRATION.md.
    periodicity, pulse_rate = envelope_periodicity(
        band_envelope(mag, mask), frame_rate_hz)

    if context_mag is not None:
        ctx_periodicity, ctx_rate = envelope_periodicity(
            band_envelope(context_mag, mask), frame_rate_hz)
    else:
        ctx_periodicity, ctx_rate = periodicity, pulse_rate

    return {
        "band_crest": round(band_crest(mag, mask), 3),
        "band_entropy": round(band_entropy(mag, mask), 4),
        "band_centroid": round(within_band_centroid(mag, freqs, mask), 1),
        "periodicity": round(periodicity, 4),
        "pulse_rate_hz": round(pulse_rate, 3),
        "context_periodicity": round(ctx_periodicity, 4),
        "context_rate_hz": round(ctx_rate, 3),
    }


def compute_freq_axis(frame_size: int, sr: int) -> np.ndarray:
    """Compute frequency values for each FFT bin."""
    n_fft = frame_size // 2 + 1
    return np.linspace(0, sr / 2, n_fft)


def stream_features(path: str, config: SpectralConfig | None = None,
                    block_frames: int = 4096,
                    progress: bool = False) -> dict:
    """
    Per-frame spectral features for a whole recording, without ever holding the
    magnitude spectrogram in memory.

    Returns the same per-frame series as analyze() — flux, centroid, flatness,
    band_energies, frame_times — but NOT `magnitude`, which is the entire point.
    A 60-minute 192 kHz recording analysed at native rate produces 2.7 M frames;
    keeping every FFT bin costs ~11 GB, while the per-frame series cost ~170 MB.
    Detection only ever needed the flux.

    Per-event work that genuinely needs FFT bins — acoustic indices, within-band
    features — is done afterwards on the extracted clip, where the window is a
    minute rather than an hour. See pipeline.process_single_file.
    """
    config = config or SpectralConfig()
    info = sf.info(path)
    src_sr = info.samplerate
    target = config.target_sr
    resampling = bool(target) and src_sr > target
    out_sr = target if resampling else src_sr

    up = down = 1
    if resampling:
        g = gcd(src_sr, out_sr)
        up, down = out_sr // g, src_sr // g

    N, H = config.frame_size, config.hop_size
    freqs = compute_freq_axis(N, out_sr)
    nyquist = out_sr / 2.0
    band_masks = {
        name: ((freqs >= lo) & (freqs < min(hi, nyquist))) if lo < nyquist
        else np.zeros(len(freqs), dtype=bool)
        for name, (lo, hi) in config.bands.items()
    }

    # Block sizing in OUTPUT samples, converted back to input samples to read.
    out_block = block_frames * H + (N - H)
    in_block = int(round(out_block * down / up))
    in_overlap = int(round((N - H) * down / up))
    # Extra input padding on each side so polyphase edge transients are trimmed
    pad_in = 4 * down if resampling else 0

    flux_parts, cen_parts, flat_parts = [], [], []
    band_parts: dict[str, list] = {name: [] for name in config.bands}
    prev_mag_row: np.ndarray | None = None
    n_blocks = 0

    for block in sf.blocks(path, blocksize=in_block + 2 * pad_in,
                           overlap=in_overlap + 2 * pad_in,
                           dtype="float64", always_2d=True):
        chunk = block.mean(axis=1)
        if resampling:
            chunk = resample_poly(chunk, up, down)
            trim = int(round(pad_in * up / down))
            if trim:
                chunk = chunk[trim:len(chunk) - trim] if len(chunk) > 2 * trim else chunk
        if len(chunk) < N:
            continue

        S = stft(chunk, N, H, config.window)
        mag = np.abs(S)

        # Flux needs the previous block's last frame to avoid a seam
        if prev_mag_row is not None:
            diff = np.maximum(np.diff(np.vstack([prev_mag_row, mag]), axis=0), 0)
        else:
            diff = np.maximum(np.diff(mag, axis=0), 0)
        block_flux = np.sqrt(np.sum(diff ** 2, axis=1))
        if prev_mag_row is None:
            block_flux = np.concatenate([[0.0], block_flux])
        prev_mag_row = mag[-1:].copy()

        flux_parts.append(block_flux)
        cen_parts.append(spectral_centroid(mag, freqs))
        flat_parts.append(spectral_flatness(mag))
        for name, mask in band_masks.items():
            band_parts[name].append(np.sum(mag[:, mask] ** 2, axis=1)
                                    if mask.any() else np.zeros(mag.shape[0]))

        n_blocks += 1
        if progress and n_blocks % 20 == 0:
            done = n_blocks * out_block / out_sr
            print(f"    scanned {done / 60:.1f} min", end="\r", flush=True)

    if progress:
        print(" " * 40, end="\r")

    if not flux_parts:
        raise RuntimeError(f"No analysable audio in {path}")

    flux = np.concatenate(flux_parts)
    n = len(flux)
    return {
        "flux": flux,
        "centroid": np.concatenate(cen_parts)[:n],
        "flatness": np.concatenate(flat_parts)[:n],
        "band_energies": {k: np.concatenate(v)[:n] for k, v in band_parts.items()},
        "freqs": freqs,
        "sr": out_sr,
        "hop_size": H,
        "frame_times": np.arange(n) * H / out_sr,
        "streamed": True,
    }


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
