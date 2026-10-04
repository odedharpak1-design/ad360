"""Thin wrappers around the ffmpeg / ffprobe command line tools."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegError(f"'{tool}' was not found on PATH. Install ffmpeg first.")


def run(cmd: list[str], verbose: bool = False) -> None:
    if verbose:
        print("$", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise FFmpegError(f"Command failed ({proc.returncode}): {cmd[0]}\n{tail}")


@dataclass
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    rotation: int = 0

    @property
    def display_size(self) -> tuple[int, int]:
        if self.rotation % 180 == 90:
            return self.height, self.width
        return self.width, self.height


def _parse_rate(rate: str) -> float:
    if not rate or rate == "0/0":
        return 0.0
    if "/" in rate:
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 0.0
    return float(rate)


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError(f"No video stream in {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    duration = float(data["format"].get("duration") or video.get("duration") or 0)
    fps = _parse_rate(video.get("avg_frame_rate", "")) or _parse_rate(video.get("r_frame_rate", "")) or 30.0
    rotation = 0
    for side in video.get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = abs(int(float(side["rotation"])))
    if not rotation and "rotate" in (video.get("tags") or {}):
        rotation = abs(int(video["tags"]["rotate"]))
    return MediaInfo(
        path=path,
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        has_audio=has_audio,
        rotation=rotation,
    )


def filter_escape(value: str) -> str:
    """Escape a path/value for use inside an ffmpeg filter argument."""
    return value.replace("\\", "/").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
