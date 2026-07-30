"""
Shared ffmpeg plumbing plus the generic video utilities that used to live in
standalone shell scripts.

Absorbed here:
  - split-video.sh  -> split_video()
  - vid2gif.sh      -> video_to_gif()   (pure ffmpeg; no mplayer/ImageMagick/gifsicle)

Everything goes through subprocess argument lists, so filenames with spaces,
commas and accents (e.g. "Lagunas, lagos y ciénagas naturales") are safe.
"""

import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# macOS / Linux fonts that ffmpeg's drawtext can load without fontconfig
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)


class FFmpegMissing(RuntimeError):
    """Raised when a render is requested but ffmpeg is not installed."""


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def have_ffmpeg() -> bool:
    return ffmpeg_path() is not None


def require_ffmpeg() -> str:
    exe = ffmpeg_path()
    if exe is None:
        raise FFmpegMissing(
            "ffmpeg not found on PATH. Install it (macOS: brew install ffmpeg) "
            "or run with videos disabled (--no-video)."
        )
    return exe


def find_font() -> str:
    """First readable font from the candidate list, or "" if none."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return ""


def run_ffmpeg(args: list[str], quiet: bool = True) -> tuple[bool, str]:
    """
    Run ffmpeg with the given arguments (no shell involved).

    Returns (success, stderr_tail).
    """
    exe = require_ffmpeg()
    cmd = [exe, "-hide_banner"]
    if quiet:
        cmd += ["-loglevel", "error"]
    cmd += args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
    return proc.returncode == 0, tail


def probe(path: str, *args: str) -> str:
    """Run ffprobe and return stripped stdout ("" when ffprobe is missing/fails)."""
    exe = ffprobe_path()
    if exe is None:
        return ""
    proc = subprocess.run(
        [exe, "-v", "quiet", *args, str(path)],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def probe_duration(path: str) -> float:
    """Media duration in seconds (0.0 if unknown)."""
    out = probe(path, "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1")
    try:
        return float(out.replace(",", "."))
    except ValueError:
        return 0.0


def probe_dimensions(path: str) -> tuple[int, int]:
    """Video width/height (0, 0 if unknown)."""
    out = probe(path, "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0")
    try:
        w, h = out.split("x")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


def probe_audio_bitrate(path: str, default: int = 128_000) -> int:
    """Audio bitrate in bits/s, falling back to `default`."""
    out = probe(path, "-select_streams", "a:0",
                "-show_entries", "stream=bit_rate",
                "-of", "default=noprint_wrappers=1:nokey=1")
    try:
        return int(out)
    except ValueError:
        return default


# --- drawtext helpers -------------------------------------------------------

@dataclass
class TextOverlay:
    """A single drawtext layer. Text is passed via file to avoid escaping bugs."""
    text: str
    x: str
    y: str
    font_size: int = 20
    color: str = "white"
    box_color: str = "black@0.5"
    box_border: int = 2


class OverlayTexts:
    """
    Writes overlay strings to a scratch directory and builds drawtext filters.

    ffmpeg's `text=` value has to survive both filtergraph and drawtext escaping;
    habitat names with commas and colons break it. `textfile=` sidesteps that,
    and the scratch dir is a plain ASCII temp path.
    """

    def __init__(self, font_file: str = ""):
        self._dir = Path(tempfile.mkdtemp(prefix="bioac_txt_"))
        self._n = 0
        self.font_file = font_file or find_font()

    def filter_for(self, overlay: TextOverlay) -> str:
        self._n += 1
        path = self._dir / f"t{self._n}.txt"
        path.write_text(overlay.text, encoding="utf-8")
        parts = [
            f"drawtext=textfile={path}",
            "reload=0",
            f"x={overlay.x}",
            f"y={overlay.y}",
            f"fontsize={overlay.font_size}",
            f"fontcolor={overlay.color}",
            "box=1",
            f"boxcolor={overlay.box_color}",
            f"boxborderw={overlay.box_border}",
        ]
        if self.font_file:
            parts.insert(1, f"fontfile={self.font_file}")
        return ":".join(parts)

    def cleanup(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def __enter__(self) -> "OverlayTexts":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


# --- generic video utilities (ex-shell scripts) -----------------------------

_SIZE_UNITS = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}


def parse_size(size: str) -> int:
    """Parse '60M' / '1G' / '500K' / '1048576' into bytes."""
    s = str(size).strip()
    if not s:
        raise ValueError("empty size")
    unit = s[-1].upper()
    if unit in _SIZE_UNITS:
        return int(float(s[:-1]) * _SIZE_UNITS[unit])
    return int(float(s))


def split_video(path: str, size_limit: str, scale: str = "scale=1080:-1",
                overhead: float = 0.8) -> list[str]:
    """
    Split a video into parts that each stay under `size_limit`.

    Port of split-video.sh: computes a target video bitrate from the size
    budget and re-encodes fixed-duration chunks. Returns the parts written.
    """
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(path)

    limit_bytes = parse_size(size_limit)
    duration = probe_duration(str(src))
    if duration <= 0:
        raise RuntimeError(f"Could not read duration of {src.name}")

    audio_bitrate = probe_audio_bitrate(str(src))
    video_bitrate = int((limit_bytes * 8 * overhead) / duration - audio_bitrate)
    if video_bitrate < 100_000:
        video_bitrate = 100_000
    chunk_s = (limit_bytes * 8) / (video_bitrate + audio_bitrate)
    n_parts = max(1, math.ceil(duration / chunk_s))

    print(f"  Source: {duration:.1f}s, target {video_bitrate // 1000} kbps video")
    print(f"  Chunk length: {chunk_s:.1f}s -> {n_parts} part(s)")

    outputs = []
    for part in range(n_parts):
        start = part * chunk_s
        out_path = src.with_name(f"{src.stem}-{part + 1}.mp4")
        ok, err = run_ffmpeg([
            "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{chunk_s:.3f}",
            "-c:v", "libx264", "-b:v", str(video_bitrate),
            "-maxrate", str(video_bitrate), "-bufsize", str(video_bitrate * 2),
            "-vf", scale, "-c:a", "aac", "-b:a", f"{audio_bitrate // 1000}k",
            "-movflags", "+faststart", "-y", str(out_path),
        ])
        if not ok:
            print(f"  Failed on part {part + 1}: {err}")
            break
        size_mb = out_path.stat().st_size / 1024 ** 2
        print(f"  Wrote {out_path.name} ({size_mb:.1f} MB)")
        outputs.append(str(out_path))

    return outputs


def video_to_gif(path: str, output_path: str = "",
                 width: int = 480, fps: int = 12) -> str:
    """
    Convert a video to an optimized looping GIF.

    Replaces vid2gif.sh's mplayer + ImageMagick + gifsicle chain with ffmpeg's
    two-pass palettegen/paletteuse, which needs no extra tooling and keeps the
    same "shrink the long edge, optimize the palette" behaviour.
    """
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(path)

    out = Path(output_path) if output_path else src.with_suffix(".gif")
    palette = Path(tempfile.gettempdir()) / f"{src.stem}_palette.png"

    src_w, src_h = probe_dimensions(str(src))
    if src_w and src_h and max(src_w, src_h) <= width:
        scale = f"scale={src_w // 2 * 2}:{src_h // 2 * 2}:flags=lanczos"
    elif src_w and src_h and src_h > src_w:
        scale = f"scale=-2:{width}:flags=lanczos"
    else:
        scale = f"scale={width}:-2:flags=lanczos"

    chain = f"fps={fps},{scale}"

    ok, err = run_ffmpeg([
        "-i", str(src), "-vf", f"{chain},palettegen=stats_mode=diff",
        "-y", str(palette),
    ])
    if not ok:
        palette.unlink(missing_ok=True)
        raise RuntimeError(f"palettegen failed: {err}")

    ok, err = run_ffmpeg([
        "-i", str(src), "-i", str(palette),
        "-lavfi", f"{chain}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
        "-loop", "0", "-y", str(out),
    ])
    palette.unlink(missing_ok=True)
    if not ok:
        raise RuntimeError(f"paletteuse failed: {err}")

    return str(out)


def concat_videos(paths: list[str], output_path: str) -> str:
    """
    Concatenate videos that share codec and geometry (our event clips do).

    Uses the concat demuxer with stream copy; falls back to re-encoding if the
    copy path fails.
    """
    clips = [p for p in paths if p and Path(p).is_file()]
    if not clips:
        return ""

    list_dir = Path(tempfile.mkdtemp(prefix="bioac_concat_"))
    list_file = list_dir / "clips.txt"
    list_file.write_text(
        "".join(f"file '{Path(p).resolve()}'\n" for p in clips),
        encoding="utf-8",
    )

    try:
        ok, _ = run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", "-y", output_path,
        ])
        if not ok:
            ok, err = run_ffmpeg([
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", "-y", output_path,
            ])
            if not ok:
                print(f"  Reel concat failed: {err}")
                return ""
    finally:
        shutil.rmtree(list_dir, ignore_errors=True)

    return output_path
