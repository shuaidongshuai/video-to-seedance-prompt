#!/usr/bin/env python3
"""Detect candidate hard cuts with FFmpeg scene scores and emit a shot manifest."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


PTS_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def duration_of(ffprobe: str, video: Path) -> float:
    command = [ffprobe, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(video)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        fail(result.stderr.strip() or "ffprobe failed", result.returncode)
    try:
        return float(result.stdout.strip())
    except ValueError:
        fail("could not read video duration")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--threshold", type=float, default=0.32,
                        help="scene score threshold, usually 0.20-0.50")
    parser.add_argument("--min-shot", type=float, default=0.15,
                        help="merge candidate cuts closer than this many seconds")
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        fail("ffmpeg and ffprobe must be available on PATH")
    if not args.video.is_file():
        fail(f"video does not exist: {args.video}")
    if not 0 < args.threshold < 1:
        fail("--threshold must be between 0 and 1")
    if args.min_shot < 0:
        fail("--min-shot must be non-negative")

    duration = duration_of(ffprobe, args.video)
    filter_expr = f"select='gt(scene,{args.threshold})',showinfo"
    command = [ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(args.video),
               "-an", "-sn", "-vf", filter_expr, "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        fail(result.stderr.strip() or "ffmpeg scene detection failed", result.returncode)

    candidates = sorted({float(match) for match in PTS_RE.findall(result.stderr) if 0 < float(match) < duration})
    cuts: list[float] = []
    for value in candidates:
        if not cuts or value - cuts[-1] >= args.min_shot:
            cuts.append(value)
    boundaries = [0.0, *cuts, duration]
    shots = [
        {"id": index + 1, "start": round(start, 6), "end": round(end, 6),
         "duration": round(end - start, 6)}
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]))
        if end > start
    ]
    payload = {
        "source": str(args.video.resolve()),
        "detector": "ffmpeg scene score",
        "threshold": args.threshold,
        "min_shot": args.min_shot,
        "note": "Candidate hard cuts; manually review flashes, occlusions, whip pans and motion blur.",
        "cuts": [round(value, 6) for value in cuts],
        "shots": shots,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
