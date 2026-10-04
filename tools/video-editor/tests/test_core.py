from ad360_video.captions import CaptionSettings, build_lines, group_lines
from ad360_video.cuts import CutSettings, Timeline, snap_to_frames, speech_segments_from_words
from ad360_video.hebrew import is_filler, normalize, word_syllables
from ad360_video.overlays import InstructionError, find_phrase, resolve_timing
from ad360_video.transcript import Word

import pytest


def words_from(text, start=0.0, step=0.4):
    return [Word(t, start + i * step, start + i * step + step * 0.8) for i, t in enumerate(text.split())]


def test_syllables():
    assert word_syllables("שלום") == 2
    assert word_syllables("בעברית") == 3
    assert word_syllables("שָׁלוֹם") == 2  # with niqqud
    assert word_syllables("2026") == 8
    assert word_syllables("AD360") >= 1


def test_normalize_and_fillers():
    assert normalize("שָׁלוֹם,") == normalize("שלום")
    assert normalize("כך") == normalize("ככ")
    assert is_filler("אממ") and is_filler("אהה") and not is_filler("אמא")


def test_lines_respect_limits():
    text = ("אנחנו רוצים לפתח כלי שיאפשר לחבר קטעי סרטונים מוקלטים לסרטון רציף אחד "
            "ולמחוק השהיות ועצירות בדיבור ולהוסיף תמלול בעברית בקצב הדיבור")
    s = CaptionSettings()
    for line in group_lines(words_from(text), s):
        assert len(line) <= 6
        assert sum(word_syllables(w.text) for w in line) <= 20


def test_syllable_limit_breaks_before_six_words():
    s = CaptionSettings(max_words=6, max_syllables=8)
    lines = group_lines(words_from("בגירושין בגירושין בגירושין"), s)
    assert [len(l) for l in lines] == [2, 1]


def test_sentence_end_breaks_line():
    lines = group_lines(words_from("שלום לכולם. היום נדבר"), CaptionSettings())
    assert [w.text for w in lines[0]] == ["שלום", "לכולם."]


def test_lines_do_not_overlap():
    lines = build_lines(words_from("א ב ג ד ה ו ז ח ט י כ ל מ נ", step=0.2), CaptionSettings())
    for a, b in zip(lines, lines[1:]):
        assert a.end <= b.start + 1e-9


def test_pause_removal_and_mapping():
    w = words_from("אחת שתיים", 0.0, 0.5) + words_from("שלוש ארבע", 5.0, 0.5)
    segs = speech_segments_from_words(w, 8.0, CutSettings())
    assert len(segs) == 2
    tl = Timeline(snap_to_frames(segs, 30, 8.0))
    assert tl.duration < 2.5
    mapped = tl.map_words(w, drop_fillers=True)
    assert [m.text for m in mapped] == ["אחת", "שתיים", "שלוש", "ארבע"]
    assert mapped[2].start - mapped[1].end < 0.5  # long gap collapsed
    assert all(b.start >= a.end - 1e-6 for a, b in zip(mapped, mapped[1:]))


def test_fillers_removed():
    w = words_from("שלום אממ לכולם", 0, 0.5)
    segs = speech_segments_from_words(w, 2.0, CutSettings())
    mapped = Timeline(segs).map_words(w, drop_fillers=True)
    assert [m.text for m in mapped] == ["שלום", "לכולם"]


def test_find_phrase_fuzzy_and_occurrence():
    w = words_from("המשרד שלנו מלווה אתכם. המשרד שלנו כאן בשבילכם")
    assert find_phrase(w, "המשרד שלנו") == (0, 1)
    assert find_phrase(w, "המשרד שלנו", occurrence=2) == (4, 5)
    assert find_phrase(w, "משרד שלנו מלווה") == (0, 2)  # missing ה prefix
    with pytest.raises(InstructionError):
        find_phrase(w, "עורך דין")


def test_resolve_timing_variants():
    w = words_from("שלום לכולם היום נדבר על חלוקת רכוש")
    clips = [(0.0, 1.0), (1.0, 3.0)]
    r = resolve_timing({"words": "חלוקת רכוש"}, w, clips, 3.0)
    assert r.start == w[5].start and r.end == w[6].end
    r = resolve_timing({"from": "היום", "to": "רכוש"}, w, clips, 3.0)
    assert (r.start, r.end) == (w[2].start, w[6].end)
    r = resolve_timing({"from": "היום", "duration": 1}, w, clips, 3.0)
    assert r.end == pytest.approx(w[2].start + 1)
    r = resolve_timing({"clip": 2}, w, clips, 3.0)
    assert (r.start, r.end) == (1.0, 3.0)
