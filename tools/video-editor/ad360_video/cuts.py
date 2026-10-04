"""Decide which parts of the joined video to keep (removing pauses) and
map timestamps from the joined timeline to the final, cut timeline."""

from __future__ import annotations

import re
import subprocess
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from .hebrew import is_filler
from .transcript import Word

Segment = tuple[float, float]


@dataclass
class CutSettings:
    max_pause: float = 0.30      # gaps between words longer than this are shortened
    keep_pause: float = 0.12     # pause length kept inside a long gap (natural breathing)
    padding: float = 0.08        # audio kept before the first / after the last word of a phrase
    remove_fillers: bool = True  # drop "אממ", "אה" ...
    min_segment: float = 0.20    # drop kept segments shorter than this (clicks/noise)
    mode: str = "words"          # "words" (transcript based) or "silence" (ffmpeg silencedetect)
    silence_db: float = -35.0
    enabled: bool = True


def _merge(segments: list[Segment], join_gap: float = 0.0) -> list[Segment]:
    out: list[Segment] = []
    for a, b in sorted(segments):
        if out and a <= out[-1][1] + join_gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def speech_segments_from_words(words: list[Word], duration: float, s: CutSettings) -> list[Segment]:
    spoken = [w for w in words if not (s.remove_fillers and is_filler(w.text))]
    if not spoken:
        return [(0.0, duration)]
    # Group words separated by short gaps into phrases.
    raw: list[Segment] = []
    for w in spoken:
        if raw and w.start - raw[-1][1] <= s.max_pause:
            raw[-1] = (raw[-1][0], max(raw[-1][1], w.end))
        else:
            raw.append((w.start, w.end))
    # Pad every phrase; half of keep_pause is added on each side so that a
    # long gap collapses to roughly `keep_pause + 2*padding`.
    pad = s.padding + s.keep_pause / 2
    padded = [(max(0.0, a - pad), min(duration, b + pad)) for a, b in raw]
    return [seg for seg in _merge(padded) if seg[1] - seg[0] >= s.min_segment]


def speech_segments_from_silence(media: str | Path, duration: float, s: CutSettings) -> list[Segment]:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(media), "-vn",
            "-af", f"silencedetect=noise={s.silence_db}dB:d={s.max_pause}", "-f", "null", "-",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    silences = list(zip(starts, ends + [duration] * (len(starts) - len(ends))))
    keep: list[Segment] = []
    cursor = 0.0
    for a, b in silences:
        if a > cursor:
            keep.append((cursor, a))
        cursor = b
    if cursor < duration:
        keep.append((cursor, duration))
    pad = s.padding + s.keep_pause / 2
    padded = [(max(0.0, a - pad), min(duration, b + pad)) for a, b in keep]
    return [seg for seg in _merge(padded) if seg[1] - seg[0] >= s.min_segment] or [(0.0, duration)]


def snap_to_frames(segments: list[Segment], fps: float, duration: float) -> list[Segment]:
    """Round boundaries to whole frames so the cut video and the remapped
    timestamps never drift apart, no matter how many cuts there are."""
    out: list[Segment] = []
    max_frame = int(duration * fps + 1e-6)
    for a, b in segments:
        fa = max(0, round(a * fps))
        fb = min(max_frame, round(b * fps))
        if fb > fa:
            out.append((fa / fps, fb / fps))
    return _merge(out)


class Timeline:
    """Maps times in the joined video to times in the cut video."""

    def __init__(self, segments: list[Segment]):
        self.segments = segments
        self._starts = [a for a, _ in segments]
        self._offsets: list[float] = []
        acc = 0.0
        for a, b in segments:
            self._offsets.append(acc)
            acc += b - a
        self.duration = acc

    def map(self, t: float) -> float:
        """Map a time; times inside a removed gap snap to the next kept segment."""
        i = bisect_right(self._starts, t) - 1
        if i < 0:
            return 0.0
        a, b = self.segments[i]
        if t <= b:
            return self._offsets[i] + (t - a)
        return self._offsets[i + 1] if i + 1 < len(self.segments) else self.duration

    def contains(self, t: float) -> bool:
        i = bisect_right(self._starts, t) - 1
        return i >= 0 and t <= self.segments[i][1]

    def map_words(self, words: list[Word], drop_fillers: bool) -> list[Word]:
        out: list[Word] = []
        for w in words:
            if drop_fillers and is_filler(w.text):
                continue
            mid = (w.start + w.end) / 2
            if not (self.contains(w.start) or self.contains(w.end) or self.contains(mid)):
                continue
            start, end = self.map(w.start), self.map(w.end)
            if end <= start:
                end = start + 0.05
            out.append(w.shifted(start, end))
        return out

    def map_range(self, start: float, end: float) -> Segment:
        return self.map(start), self.map(end)


def identity_timeline(duration: float) -> Timeline:
    return Timeline([(0.0, duration)])
