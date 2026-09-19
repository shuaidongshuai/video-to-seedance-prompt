#!/usr/bin/env python3
"""Extract analysis-friendly PCM WAV audio from a video with FFmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path, help="output .wav path")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, choices=(1, 2), default=1)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, help="exclusive end time")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        fail("ffmpeg is not available on PATH")
    if not args.video.is_file():
        fail(f"video does not exist: {args.video}")
    if args.output.suffix.lower() != ".wav":
        fail("output must use the .wav extension")
    if args.sample_rate <= 0:
        fail("--sample-rate must be positive")
    if args.start < 0 or (args.end is not None and args.end <= args.start):
        fail("invalid --start/--end range")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error",
               "-y" if args.overwrite else "-n", "-ss", f"{args.start:.6f}",
               "-i", str(args.video)]
    if args.end is not None:
        command += ["-t", f"{args.end - args.start:.6f}"]
    command += ["-vn", "-ac", str(args.channels), "-ar", str(args.sample_rate),
                "-c:a", "pcm_s16le", str(args.output)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        fail(result.stderr.strip() or "ffmpeg audio extraction failed", result.returncode)
    print(json.dumps({
        "source": str(args.video.resolve()),
        "output": str(args.output.resolve()),
        "sample_rate": args.sample_rate,
        "channels": args.channels,
        "start": args.start,
        "end": args.end,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
