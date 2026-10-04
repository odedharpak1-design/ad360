"""Hebrew text helpers: normalisation for matching and syllable estimation."""

from __future__ import annotations

import math
import re
import unicodedata

HEBREW_LETTERS = "אבגדהוזחטיכךלמםנןסעפףצץקרשת"
_FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
# Niqqud vowel points (each marks one vowel => one syllable). Shva (U+05B0) is
# excluded because it is usually silent; holam/shuruk dots are handled below.
_VOWEL_POINTS = set("ֱֲֳִֵֶַָׇֻ")
_HOLAM = "ֹ"
_SHURUK_DAGESH = "ּ"
_NIQQUD_RE = re.compile("[֑-ׇ]")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_LATIN_VOWELS_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)

# Common Hebrew hesitation sounds produced by speech recognisers.
FILLER_WORDS = {"אה", "אהה", "אההה", "אמ", "אממ", "אמממ", "ממ", "מממ", "הממ", "אהם", "אם-", "אה-", "uh", "um", "umm", "hmm"}

_DIGIT_SYLLABLES = 2  # rough average of spoken Hebrew numbers per digit


def strip_niqqud(text: str) -> str:
    return _NIQQUD_RE.sub("", text)


def normalize(text: str) -> str:
    """Normalise a word/phrase for fuzzy matching against the transcript."""
    text = unicodedata.normalize("NFC", text)
    text = strip_niqqud(text)
    text = text.replace("״", "").replace("׳", "").replace('"', "").replace("'", "")
    text = _PUNCT_RE.sub(" ", text)
    text = text.translate(_FINALS).lower()
    return " ".join(text.split())


def tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t]


def is_filler(word: str) -> bool:
    n = normalize(word)
    return bool(n) and (n in FILLER_WORDS or re.fullmatch(r"(אה+|א?מ{2,}|ה?מ{2,})", n) is not None)


def _syllables_pointed(word: str) -> int:
    count = 0
    chars = list(word)
    for i, ch in enumerate(chars):
        if ch in _VOWEL_POINTS or ch == _HOLAM:
            count += 1
        elif ch == _SHURUK_DAGESH and i > 0 and chars[i - 1] == "ו":
            # shuruk: vav with dagesh not followed by its own vowel
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt not in _VOWEL_POINTS and nxt != _HOLAM:
                count += 1
    # Patah gnuva at the end (e.g. רוּחַ) is still a vowel – already counted.
    return max(1, count)


def word_syllables(word: str) -> int:
    """Estimate the number of syllables in a single word.

    * With niqqud the count is exact-ish (one per vowel point).
    * Unpointed Hebrew is ambiguous, so we use ceil(letters / 2), which is
      within ±1 syllable for the vast majority of everyday words.
    * Digits and Latin text get simple heuristics.
    """
    word = unicodedata.normalize("NFC", word)
    if _NIQQUD_RE.search(word) and any(c in _VOWEL_POINTS or c in (_HOLAM, _SHURUK_DAGESH) for c in word):
        return _syllables_pointed(word)
    hebrew = sum(1 for c in word if c in HEBREW_LETTERS)
    digits = sum(1 for c in word if c.isdigit())
    latin = "".join(c for c in word if "a" <= c.lower() <= "z")
    total = 0
    if hebrew:
        total += max(1, math.ceil(hebrew / 2))
    if digits:
        total += digits * _DIGIT_SYLLABLES
    if latin:
        total += max(1, len(_LATIN_VOWELS_RE.findall(latin)))
    return total


def text_syllables(text: str) -> int:
    return sum(word_syllables(w) for w in text.split())
