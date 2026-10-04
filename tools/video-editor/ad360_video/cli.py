"""Command line interface.

  python -m ad360_video prepare clip1.mp4 clip2.mp4 -w work/
  python -m ad360_video words   -w work/ [-i instructions.yaml]
  python -m ad360_video render  -w work/ -i instructions.yaml -o final.mp4
  python -m ad360_video run     clip1.mp4 clip2.mp4 -i instructions.yaml -o final.mp4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .captions import build_lines
from .ffmpeg_utils import FFmpegError
from .overlays import InstructionError
from .pipeline import plan, prepare, render, settings_from
from .transcript import DEFAULT_MODEL


def load_instructions(path: str | None) -> tuple[dict, Path]:
    if not path:
        return {}, Path.cwd()
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise InstructionError(f"{p} must contain a mapping at the top level")
    return data, p.parent.resolve()


def _fmt(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m):02}:{s:05.2f}"


def cmd_prepare(args) -> None:
    instr, _ = load_instructions(args.instructions)
    video, _, _ = settings_from(instr)
    prepare([Path(x) for x in args.inputs], Path(args.workdir), video, args.model, args.device,
            args.compute_type, args.prompt, args.verbose)
    print("\nNext: review/correct work/transcript.json, then run `render`.")


def cmd_words(args) -> None:
    instr, _ = load_instructions(args.instructions)
    _, cuts, caps = settings_from(instr)
    p = plan(Path(args.workdir), cuts)
    print(f"Final duration: {_fmt(p.timeline.duration)}  ({len(p.timeline.segments)} kept segments)\n")
    for i, (a, b) in enumerate(p.clips, 1):
        print(f"clip {i}: {_fmt(a)} - {_fmt(b)}")
    print("\nCaption lines (time in the FINAL video):")
    for ln in build_lines(p.words, caps, p.timeline.duration):
        print(f"  {_fmt(ln.start)} - {_fmt(ln.end)}  {ln.text}")


def cmd_render(args) -> None:
    instr, base = load_instructions(args.instructions)
    render(Path(args.workdir), instr, Path(args.output), base, args.verbose)


def cmd_run(args) -> None:
    instr, base = load_instructions(args.instructions)
    video, _, _ = settings_from(instr)
    workdir = Path(args.workdir)
    prepare([Path(x) for x in args.inputs], workdir, video, args.model, args.device,
            args.compute_type, args.prompt, args.verbose)
    render(workdir, instr, Path(args.output), base, args.verbose)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ad360_video", description="Join clips, cut pauses, add Hebrew captions and overlays.")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, inputs=False, output=False):
        if inputs:
            p.add_argument("inputs", nargs="+", help="video clips, in order")
            p.add_argument("--model", default=DEFAULT_MODEL, help=f"Whisper model (default: {DEFAULT_MODEL})")
            p.add_argument("--device", default="auto", help="auto | cpu | cuda")
            p.add_argument("--compute-type", default="default", help="e.g. int8 for faster CPU runs")
            p.add_argument("--prompt", help="text hint for the recogniser (names, terms)")
        p.add_argument("-w", "--workdir", default="work", help="working folder (default: work)")
        p.add_argument("-i", "--instructions", help="YAML/JSON instructions file")
        if output:
            p.add_argument("-o", "--output", required=True, help="output .mp4")
        p.add_argument("-v", "--verbose", action="store_true")

    common(sub.add_parser("prepare", help="join clips + transcribe"), inputs=True)
    common(sub.add_parser("words", help="show caption lines and timings after cuts"))
    common(sub.add_parser("render", help="cut pauses, burn captions and overlays"), output=True)
    common(sub.add_parser("run", help="prepare + render in one go"), inputs=True, output=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = {"prepare": cmd_prepare, "words": cmd_words, "render": cmd_render, "run": cmd_run}[args.command]
    try:
        handler(args)
    except (InstructionError, FFmpegError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
