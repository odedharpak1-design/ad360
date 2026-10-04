"""High level steps: join clips -> transcribe -> cut pauses -> captions/overlays -> render."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from . import ffmpeg_utils as ff
from .ass import build_ass
from .captions import CaptionSettings, build_lines, to_srt
from .cuts import (
    CutSettings,
    Timeline,
    identity_timeline,
    snap_to_frames,
    speech_segments_from_silence,
    speech_segments_from_words,
)
from .overlays import ImageOverlay, anchor, parse_overlays, px
from .transcript import DEFAULT_MODEL, Transcript, transcribe

JOINED = "joined.mkv"  # lossless-ish intermediate (PCM audio)
AUDIO = "audio.wav"
TRANSCRIPT = "transcript.json"


@dataclass
class VideoSettings:
    width: int = 0            # 0 => size of the first clip
    height: int = 0
    fps: float = 0            # 0 => frame rate of the first clip (rounded)
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "192k"
    fonts_dir: str = ""       # folder with .ttf/.otf files (e.g. Heebo) used by captions


def _apply(obj: Any, values: dict | None) -> Any:
    if not values:
        return obj
    known = {f.name for f in fields(obj)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown setting(s) for {type(obj).__name__}: {', '.join(sorted(unknown))}")
    for k, v in values.items():
        setattr(obj, k, v)
    return obj


def settings_from(instructions: dict) -> tuple[VideoSettings, CutSettings, CaptionSettings]:
    return (
        _apply(VideoSettings(), instructions.get("video")),
        _apply(CutSettings(), instructions.get("cuts")),
        _apply(CaptionSettings(), instructions.get("captions")),
    )


# ------------------------------------------------------------------ step 1

def join_clips(inputs: list[Path], workdir: Path, video: VideoSettings, verbose: bool = False) -> list[tuple[float, float]]:
    """Normalise every clip to the same size/fps/audio format and concatenate.
    Returns the (start, end) of every clip inside the joined video."""
    infos = [ff.probe(p) for p in inputs]
    w0, h0 = infos[0].display_size
    width = video.width or w0
    height = video.height or h0
    width, height = width - width % 2, height - height % 2
    fps = video.fps or round(infos[0].fps) or 30

    cmd = ["ffmpeg", "-y", "-hide_banner"]
    for p in inputs:
        cmd += ["-i", str(p)]
    parts, labels, clips = [], [], []
    t = 0.0
    for i, info in enumerate(infos):
        d = info.duration
        parts.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p,"
            f"trim=duration={d:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        if info.has_audio:
            parts.append(
                f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS,apad,atrim=duration={d:.3f}[a{i}]"
            )
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
        clips.append((t, t + d))
        t += d
    parts.append(f"{''.join(labels)}concat=n={len(inputs)}:v=1:a=1[v][a]")
    script = workdir / "join.filter"
    script.write_text(";\n".join(parts), encoding="utf-8")
    cmd += [
        "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-ar", "48000",
        str(workdir / JOINED),
    ]
    ff.run(cmd, verbose)
    return clips


def joined_path(workdir: Path) -> Path:
    return workdir / JOINED


def extract_audio(workdir: Path, verbose: bool = False) -> Path:
    out = workdir / AUDIO
    ff.run(["ffmpeg", "-y", "-hide_banner", "-i", str(joined_path(workdir)), "-vn", "-ac", "1", "-ar", "16000", str(out)], verbose)
    return out


def prepare(
    inputs: list[Path],
    workdir: Path,
    video: VideoSettings,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    compute_type: str = "default",
    prompt: str | None = None,
    verbose: bool = False,
) -> Transcript:
    ff.require_ffmpeg()
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"[1/2] Joining {len(inputs)} clip(s)…")
    clips = join_clips(inputs, workdir, video, verbose)
    audio = extract_audio(workdir, verbose)
    print(f"[2/2] Transcribing (Hebrew, model: {model})… this can take a while")
    words = transcribe(audio, model, "he", device, compute_type, prompt, verbose)
    tr = Transcript(words=words, source=",".join(str(p) for p in inputs), clips=clips)
    tr.save(workdir / TRANSCRIPT)
    (workdir / "transcript.txt").write_text(tr.plain_text() + "\n", encoding="utf-8")
    print(f"      {len(words)} words -> {workdir / TRANSCRIPT}")
    return tr


# ------------------------------------------------------------------ step 2

@dataclass
class Plan:
    timeline: Timeline
    words: list  # words in the final timeline
    clips: list[tuple[float, float]]
    width: int
    height: int
    fps: float


def plan(workdir: Path, cuts: CutSettings) -> Plan:
    info = ff.probe(joined_path(workdir))
    tr = Transcript.load(workdir / TRANSCRIPT)
    duration = info.duration
    if cuts.enabled:
        if cuts.mode == "silence":
            segs = speech_segments_from_silence(joined_path(workdir), duration, cuts)
        else:
            segs = speech_segments_from_words(tr.words, duration, cuts)
        timeline = Timeline(snap_to_frames(segs, info.fps, duration))
    else:
        timeline = identity_timeline(duration)
    words = timeline.map_words(tr.words, drop_fillers=cuts.enabled and cuts.remove_fillers)
    clips = [timeline.map_range(a, b) for a, b in (tr.clips or [(0.0, duration)])]
    return Plan(timeline, words, clips, info.width, info.height, info.fps)


def _image_filters(images: list[ImageOverlay], first_input: int, width: int, height: int, fps: float) -> tuple[list[str], list[str], str]:
    """Return (input args, filter parts, output label) for image overlays chained onto [base]."""
    args, parts = [], []
    cur = "base"
    short = min(width, height)
    for k, img in enumerate(images):
        idx = first_input + k
        dur = img.when.end - img.when.start
        args += ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{dur:.3f}", "-i", str(img.file)]
        w = round(px(img.width, width)) if img.width else -2
        h = round(px(img.height, height)) if img.height else -2
        if w == -2 and h == -2:
            w = round(width * 0.3)
        w = w - w % 2 if w > 0 else w
        h = h - h % 2 if h > 0 else h
        fade = min(img.fade, dur / 2)
        chain = f"[{idx}:v]scale={w}:{h},format=rgba"
        if img.opacity < 1:
            chain += f",colorchannelmixer=aa={img.opacity:.3f}"
        if fade > 0:
            chain += f",fade=t=in:st=0:d={fade:.3f}:alpha=1,fade=t=out:st={dur - fade:.3f}:d={fade:.3f}:alpha=1"
        chain += f",setpts=PTS-STARTPTS+{img.when.start:.3f}/TB[img{k}]"
        parts.append(chain)
        ax, ay, use_margin = anchor(img.position)
        if use_margin:
            m = round(px(img.margin, short))
            x = f"{m}+{ax}*(W-w-{2 * m})"
            y = f"{m}+{ay}*(H-h-{2 * m})"
        else:
            x, y = f"{ax}*W-w/2", f"{ay}*H-h/2"
        out = f"ov{k}"
        parts.append(
            f"[{cur}][img{k}]overlay=x='{x}':y='{y}':eof_action=pass:"
            f"enable='between(t,{img.when.start:.3f},{img.when.end:.3f})'[{out}]"
        )
        cur = out
    return args, parts, cur


def render(
    workdir: Path,
    instructions: dict,
    output: Path,
    base_dir: Path,
    verbose: bool = False,
) -> Path:
    ff.require_ffmpeg()
    video, cuts, caps = settings_from(instructions)
    p = plan(workdir, cuts)
    duration = p.timeline.duration
    images, texts = parse_overlays(instructions, base_dir, p.words, p.clips, duration)
    lines = build_lines(p.words, caps, duration)
    output.parent.mkdir(parents=True, exist_ok=True)

    ass_path = workdir / "captions.ass"
    ass_path.write_text(build_ass(p.width, p.height, lines, caps, texts), encoding="utf-8")
    srt_path = output.with_suffix(".srt")
    srt_path.write_text(to_srt(lines, caps), encoding="utf-8")

    segs = p.timeline.segments
    n = len(segs)
    parts: list[str] = []
    if n == 1:
        a, b = segs[0]
        parts.append(f"[0:v]trim=start={a:.4f}:end={b:.4f},setpts=PTS-STARTPTS[base]")
        parts.append(f"[0:a]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS[aout]")
    else:
        parts.append(f"[0:v]split={n}" + "".join(f"[vs{i}]" for i in range(n)))
        parts.append(f"[0:a]asplit={n}" + "".join(f"[as{i}]" for i in range(n)))
        for i, (a, b) in enumerate(segs):
            d = b - a
            f = min(0.012, d / 4)
            parts.append(f"[vs{i}]trim=start={a:.4f}:end={b:.4f},setpts=PTS-STARTPTS[vc{i}]")
            parts.append(
                f"[as{i}]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={f:.3f},afade=t=out:st={d - f:.4f}:d={f:.3f}[ac{i}]"
            )
        parts.append("".join(f"[vc{i}][ac{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[base][aout]")

    img_args, img_parts, cur = _image_filters(images, 1, p.width, p.height, p.fps)
    parts += img_parts
    sub = f"ass=filename='{ff.filter_escape(str(ass_path.resolve()))}'"
    if video.fonts_dir:
        sub += f":fontsdir='{ff.filter_escape(str((base_dir / video.fonts_dir).resolve()))}'"
    parts.append(f"[{cur}]{sub},format=yuv420p[vout]")

    script = workdir / "render.filter"
    script.write_text(";\n".join(parts), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(joined_path(workdir))] + img_args + [
        "-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", video.preset, "-crf", str(video.crf), "-pix_fmt", "yuv420p",
        "-r", f"{p.fps:g}", "-c:a", "aac", "-b:a", video.audio_bitrate, "-movflags", "+faststart",
        str(output),
    ]
    original = ff.probe(joined_path(workdir)).duration
    print(f"Rendering: {original:.1f}s -> {duration:.1f}s ({n} kept segments), "
          f"{len(lines)} caption lines, {len(images)} image(s), {len(texts)} text overlay(s)")
    ff.run(cmd, verbose)
    print(f"Done: {output}\nCaptions: {srt_path}")
    return output
