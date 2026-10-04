"""Word-level transcript model, persistence and speech recognition."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0

    def shifted(self, start: float, end: float) -> "Word":
        return Word(self.text, start, end, self.prob)


@dataclass
class Transcript:
    words: list[Word]
    language: str = "he"
    source: str = ""
    # (start, end) of each original input clip inside the joined video.
    clips: list[tuple[float, float]] = field(default_factory=list)

    def save(self, path: str | Path) -> None:
        data = {
            "language": self.language,
            "source": self.source,
            "clips": [list(c) for c in self.clips],
            "words": [asdict(w) for w in self.words],
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Transcript":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        words = [Word(w["text"].strip(), float(w["start"]), float(w["end"]), float(w.get("prob", 1.0))) for w in data["words"]]
        words = [w for w in words if w.text]
        return cls(
            words=words,
            language=data.get("language", "he"),
            source=data.get("source", ""),
            clips=[(float(a), float(b)) for a, b in data.get("clips", [])],
        )

    def plain_text(self) -> str:
        return " ".join(w.text for w in self.words)


DEFAULT_MODEL = "ivrit-ai/whisper-large-v3-turbo-ct2"


def transcribe(
    audio_path: str | Path,
    model_name: str = DEFAULT_MODEL,
    language: str = "he",
    device: str = "auto",
    compute_type: str = "default",
    initial_prompt: str | None = None,
    verbose: bool = False,
) -> list[Word]:
    """Run faster-whisper with word timestamps and return the words."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise SystemExit("faster-whisper is not installed. Run: pip install -r requirements.txt") from exc

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        beam_size=5,
        condition_on_previous_text=False,
        initial_prompt=initial_prompt,
    )
    words: list[Word] = []
    for seg in segments:
        if verbose:
            print(f"  [{seg.start:7.2f}-{seg.end:7.2f}] {seg.text.strip()}")
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text, float(w.start), float(w.end), float(w.probability)))
    return words
