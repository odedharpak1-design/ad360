"""Split the transcript into short caption lines and write them as ASS/SRT."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .hebrew import word_syllables
from .transcript import Word

_SENTENCE_END = re.compile(r"[.!?…]$")
_CLAUSE_END = re.compile(r"[,;:–—-]$")
_STRIP_TRAILING = re.compile(r"[.,;:]+$")


@dataclass
class CaptionSettings:
    max_words: int = 6
    max_syllables: int = 20
    max_gap: float = 0.7          # a silence longer than this always starts a new line
    min_duration: float = 0.6     # minimum on-screen time of a line
    linger: float = 0.4           # keep a line up to this long after its last word
    strip_punctuation: bool = True
    font: str = "Heebo"
    font_size: int = 0            # 0 => automatic (relative to video height)
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline: float = 0            # 0 => automatic
    shadow: float = 0
    bold: bool = True
    box: bool = False             # opaque box behind the text instead of an outline
    box_color: str = "#000000A0"
    position: str = "bottom"      # bottom | middle | top
    margin: int = 0               # vertical margin in pixels, 0 => automatic
    enabled: bool = True


@dataclass
class CaptionLine:
    words: list[Word]
    start: float
    end: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _syl(words: list[Word]) -> int:
    return sum(word_syllables(w.text) for w in words)


def group_lines(words: list[Word], s: CaptionSettings) -> list[list[Word]]:
    """Greedy grouping that never exceeds max_words / max_syllables and
    prefers breaking at punctuation and natural pauses."""
    lines: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            gap = w.start - cur[-1].end
            too_long = len(cur) + 1 > s.max_words or _syl(cur) + word_syllables(w.text) > s.max_syllables
            sentence_break = bool(_SENTENCE_END.search(cur[-1].text))
            if too_long:
                # Prefer to break after a comma inside the current line if it
                # leaves at least two words on each side.
                cut = None
                for i in range(len(cur) - 2, 1, -1):
                    if _CLAUSE_END.search(cur[i - 1].text) or _SENTENCE_END.search(cur[i - 1].text):
                        cut = i
                        break
                if cut is not None:
                    lines.append(cur[:cut])
                    cur = cur[cut:]
                    if len(cur) + 1 <= s.max_words and _syl(cur) + word_syllables(w.text) <= s.max_syllables:
                        cur.append(w)
                        continue
                lines.append(cur)
                cur = [w]
                continue
            if sentence_break or gap > s.max_gap:
                lines.append(cur)
                cur = [w]
                continue
        cur.append(w)
    if cur:
        lines.append(cur)
    return _rebalance_orphans(lines, s)


def _rebalance_orphans(lines: list[list[Word]], s: CaptionSettings) -> list[list[Word]]:
    """Avoid a lone trailing word: move one word from the previous line when
    both lines are part of the same sentence and limits still hold."""
    for i in range(1, len(lines)):
        prev, cur = lines[i - 1], lines[i]
        if len(cur) == 1 and len(prev) >= 3 and not _SENTENCE_END.search(prev[-1].text):
            if cur[0].start - prev[-1].end <= s.max_gap:
                moved = prev[-1]
                if len(cur) + 1 <= s.max_words and _syl(cur) + word_syllables(moved.text) <= s.max_syllables:
                    lines[i - 1] = prev[:-1]
                    lines[i] = [moved] + cur
    return [ln for ln in lines if ln]


def build_lines(words: list[Word], s: CaptionSettings, duration: float | None = None) -> list[CaptionLine]:
    groups = group_lines(words, s)
    lines: list[CaptionLine] = []
    for idx, g in enumerate(groups):
        start = g[0].start
        end = g[-1].end + s.linger
        nxt = groups[idx + 1][0].start if idx + 1 < len(groups) else None
        end = max(end, start + s.min_duration)
        if nxt is not None:
            # Never overlap the next line; close tiny gaps so text doesn't flicker.
            if nxt - end < 0.25:
                end = nxt
            end = min(end, nxt)
        elif duration is not None:
            end = min(end, duration)
        lines.append(CaptionLine(g, start, max(end, start + 0.05)))
    return lines


def display_text(line: CaptionLine, s: CaptionSettings) -> str:
    text = line.text
    if s.strip_punctuation:
        text = " ".join(_STRIP_TRAILING.sub("", w) or w for w in text.split())
    return text


# ---------------------------------------------------------------- formats

def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{sec:02},{ms:03}"


def to_srt(lines: list[CaptionLine], s: CaptionSettings) -> str:
    out = []
    for i, ln in enumerate(lines, 1):
        out.append(f"{i}\n{_ts_srt(ln.start)} --> {_ts_srt(ln.end)}\n‫{display_text(ln, s)}‬\n")
    return "\n".join(out)
