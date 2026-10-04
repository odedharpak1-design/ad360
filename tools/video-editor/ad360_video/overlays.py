"""Image / text overlays whose timing is defined by words in the transcript."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .hebrew import normalize, tokens
from .transcript import Word


class InstructionError(ValueError):
    pass


# ----------------------------------------------------------- phrase search

def _token_score(a: str, b: str) -> float:
    if a == b:
        return 1.0
    # Hebrew attaches prefixes (ו, ה, ב, ל, מ, ש, כ) – tolerate one of them.
    if len(a) > 2 and len(b) > 2 and (a[1:] == b or b[1:] == a):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def find_phrase(
    words: list[Word],
    phrase: str,
    occurrence: int = 1,
    after: float = -1.0,
    threshold: float = 0.75,
) -> tuple[int, int]:
    """Return (first_index, last_index) of the n-th occurrence of `phrase`
    in `words` starting after time `after`. Matching is fuzzy so small speech
    recognition errors don't break the instructions."""
    target = tokens(phrase)
    if not target:
        raise InstructionError(f"Empty phrase: {phrase!r}")
    norm = [normalize(w.text) for w in words]
    n = len(target)
    hits: list[tuple[int, float]] = []
    i = 0
    while i <= len(words) - n:
        if words[i].start < after:
            i += 1
            continue
        window = norm[i : i + n]
        score = sum(_token_score(a, b) for a, b in zip(window, target)) / n
        if score >= threshold:
            # take the best-scoring start among overlapping candidates
            best_i, best = i, score
            for j in range(i + 1, min(i + n, len(words) - n + 1)):
                sc = sum(_token_score(a, b) for a, b in zip(norm[j : j + n], target)) / n
                if sc > best:
                    best_i, best = j, sc
            hits.append((best_i, best))
            i = best_i + n
            continue
        i += 1
    if len(hits) < occurrence:
        raise InstructionError(_not_found_message(words, phrase, occurrence, len(hits)))
    start = hits[occurrence - 1][0]
    return start, start + n - 1


def _not_found_message(words: list[Word], phrase: str, occurrence: int, found: int) -> str:
    target = tokens(phrase)
    norm = [normalize(w.text) for w in words]
    best = (0.0, 0)
    n = len(target)
    for i in range(0, max(1, len(words) - n + 1)):
        sc = sum(_token_score(a, b) for a, b in zip(norm[i : i + n], target)) / max(n, 1)
        best = max(best, (sc, i))
    near = " ".join(w.text for w in words[best[1] : best[1] + n + 2])
    return (
        f"Phrase {phrase!r} (occurrence {occurrence}) not found in transcript "
        f"(found {found}). Closest match: {near!r}"
    )


# ----------------------------------------------------------- data model

@dataclass
class TimeRange:
    start: float
    end: float


@dataclass
class ImageOverlay:
    file: Path
    when: TimeRange
    position: Any = "top-right"
    width: float = 0.3            # fraction of video width (or pixels if > 1)
    height: float | None = None
    margin: float = 0.04          # fraction of the short side (or pixels if > 1)
    fade: float = 0.25
    opacity: float = 1.0


@dataclass
class TextOverlay:
    text: str
    when: TimeRange
    position: Any = "top"
    font: str | None = None
    font_size: float = 0.06       # fraction of video height (or pixels if > 1)
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline: float = 3
    bold: bool = True
    box: bool = False
    box_color: str = "#000000A0"
    margin: float = 0.05
    fade: float = 0.25
    extra: dict = field(default_factory=dict)


# ----------------------------------------------------------- timing

def resolve_timing(
    spec: dict,
    words: list[Word],
    clips: list[tuple[float, float]],
    duration: float,
) -> TimeRange:
    """Work out (start, end) in the final video for an overlay spec.

    Supported keys (combine as needed):
      words:  "exact phrase"           -> from first to last word of the phrase
      from:   "phrase"                 -> start at the phrase's first word
      to:     "phrase"                 -> end at the phrase's last word (searched after `from`)
      from_end: true                   -> start at the END of the `from` phrase instead
      occurrence / to_occurrence: N    -> which occurrence of the phrase (1-based)
      clip:   N                        -> the whole N-th input clip (1-based)
      start / end: seconds             -> absolute times in the final video
      duration: seconds                -> length when no end is given
      lead / tail: seconds             -> show earlier / keep longer than the words
    """
    occ = int(spec.get("occurrence", 1))
    start = end = None

    if "clip" in spec:
        idx = int(spec["clip"]) - 1
        if not 0 <= idx < len(clips):
            raise InstructionError(f"clip {spec['clip']} does not exist (have {len(clips)} clips)")
        start, end = clips[idx]

    if "words" in spec:
        i, j = find_phrase(words, str(spec["words"]), occ)
        start, end = words[i].start, words[j].end

    if "from" in spec:
        i, j = find_phrase(words, str(spec["from"]), occ)
        start = words[j].end if spec.get("from_end") else words[i].start

    if "to" in spec:
        after = start if start is not None else -1.0
        i, j = find_phrase(words, str(spec["to"]), int(spec.get("to_occurrence", 1)), after=after - 1e-3)
        end = words[j].end

    if "start" in spec:
        start = float(spec["start"])
    if "end" in spec:
        end = float(spec["end"])

    if start is None:
        raise InstructionError(f"Overlay has no start (use words/from/clip/start): {spec}")
    if "duration" in spec and ("to" not in spec and "end" not in spec):
        end = start + float(spec["duration"])
    if end is None:
        end = start + 3.0

    start -= float(spec.get("lead", 0))
    end += float(spec.get("tail", 0))
    start = max(0.0, start)
    end = min(duration, end)
    if end <= start:
        raise InstructionError(f"Overlay ends before it starts ({start:.2f}s >= {end:.2f}s): {spec}")
    return TimeRange(start, end)


def parse_overlays(
    instructions: dict,
    base_dir: Path,
    words: list[Word],
    clips: list[tuple[float, float]],
    duration: float,
) -> tuple[list[ImageOverlay], list[TextOverlay]]:
    images: list[ImageOverlay] = []
    for spec in instructions.get("images", []) or []:
        f = Path(spec["file"])
        if not f.is_absolute():
            f = (base_dir / f).resolve()
        if not f.exists():
            raise InstructionError(f"Image not found: {f}")
        when = resolve_timing(spec, words, clips, duration)
        images.append(
            ImageOverlay(
                file=f,
                when=when,
                position=spec.get("position", "top-right"),
                width=float(spec.get("width", 0.3)),
                height=float(spec["height"]) if "height" in spec else None,
                margin=float(spec.get("margin", 0.04)),
                fade=float(spec.get("fade", 0.25)),
                opacity=float(spec.get("opacity", 1.0)),
            )
        )
    texts: list[TextOverlay] = []
    for spec in instructions.get("texts", []) or []:
        if "text" not in spec:
            raise InstructionError(f"Text overlay without 'text': {spec}")
        when = resolve_timing(spec, words, clips, duration)
        texts.append(
            TextOverlay(
                text=str(spec["text"]),
                when=when,
                position=spec.get("position", "top"),
                font=spec.get("font"),
                font_size=float(spec.get("font_size", 0.06)),
                color=str(spec.get("color", "#FFFFFF")),
                outline_color=str(spec.get("outline_color", "#000000")),
                outline=float(spec.get("outline", 3)),
                bold=bool(spec.get("bold", True)),
                box=bool(spec.get("box", False)),
                box_color=str(spec.get("box_color", "#000000A0")),
                margin=float(spec.get("margin", 0.05)),
                fade=float(spec.get("fade", 0.25)),
            )
        )
    return images, texts


# ----------------------------------------------------------- positions

_NAMED = {
    # name: (x anchor 0..1, y anchor 0..1)
    "top-left": (0.0, 0.0), "top": (0.5, 0.0), "top-center": (0.5, 0.0), "top-right": (1.0, 0.0),
    "left": (0.0, 0.5), "center": (0.5, 0.5), "middle": (0.5, 0.5), "right": (1.0, 0.5),
    "bottom-left": (0.0, 1.0), "bottom": (0.5, 1.0), "bottom-center": (0.5, 1.0), "bottom-right": (1.0, 1.0),
}

HEBREW_POSITIONS = {
    "למעלה משמאל": "top-left", "למעלה": "top", "למעלה מימין": "top-right",
    "משמאל": "left", "מרכז": "center", "באמצע": "center", "מימין": "right",
    "למטה משמאל": "bottom-left", "למטה": "bottom", "למטה מימין": "bottom-right",
}


def anchor(position: Any) -> tuple[float, float, bool]:
    """Return (x, y, use_margin). Named positions sit inside a safe margin;
    {x:, y:} dicts are exact relative coordinates of the element's centre."""
    if isinstance(position, dict):
        return float(position.get("x", 0.5)), float(position.get("y", 0.5)), False
    if isinstance(position, (list, tuple)) and len(position) == 2:
        return float(position[0]), float(position[1]), False
    name = str(position).strip().lower()
    name = HEBREW_POSITIONS.get(str(position).strip(), name)
    if name not in _NAMED:
        raise InstructionError(f"Unknown position {position!r}. Use one of: {', '.join(_NAMED)} or {{x:, y:}}")
    x, y = _NAMED[name]
    return x, y, True


def px(value: float, ref: float) -> float:
    """Values <= 1 are fractions of `ref`, larger values are pixels."""
    return value * ref if value <= 1 else value
