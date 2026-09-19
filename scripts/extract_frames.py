#!/usr/bin/env python3
"""Extract regular or explicit-timestamp evidence frames with a JSON manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROFILE_INTERVALS = {"slow": 0.75, "normal": 0.4, "action": 0.2}


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        fail(result.stderr.strip() or "ffmpeg failed", result.returncode)


def parse_timestamps(raw: str) -> list[float]:
    values: list[float] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            fail(f"invalid timestamp: {token}")
        if value < 0:
            fail("timestamps must be non-negative")
        values.append(value)
    return sorted(set(values))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--profile", choices=PROFILE_INTERVALS, default="normal")
    parser.add_argument("--interval", type=float, help="seconds between frames; overrides --profile")
    parser.add_argument("--timestamps", help="comma-separated exact timestamps in seconds")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, help="exclusive end time")
    parser.add_argument("--scale-width", type=int, default=1280, help="0 keeps source width")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    executable = shutil.which("ffmpeg")
    if not executable:
        fail("ffmpeg is not available on PATH")
    if not args.video.is_file():
        fail(f"video does not exist: {args.video}")
    if args.start < 0 or (args.end is not None and args.end <= args.start):
        fail("invalid --start/--end range")
    if args.interval is not None and args.interval <= 0:
        fail("--interval must be greater than zero")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    overwrite = "-y" if args.overwrite else "-n"
    scale = [] if args.scale_width == 0 else ["-vf", f"scale={args.scale_width}:-2"]

    if args.timestamps:
        timestamps = parse_timestamps(args.timestamps)
        for index, timestamp in enumerate(timestamps, 1):
            output = args.output_dir / f"frame_{index:04d}_{timestamp:010.3f}s.jpg"
            command = [executable, "-hide_banner", "-loglevel", "error", overwrite,
                       "-ss", f"{timestamp:.6f}", "-i", str(args.video), "-frames:v", "1",
                       *scale, "-q:v", "2", str(output)]
            run(command)
            manifest.append({"index": index, "timestamp": timestamp, "path": str(output.resolve())})
        mode = {"type": "timestamps", "timestamps": timestamps}
    else:
        interval = args.interval or PROFILE_INTERVALS[args.profile]
        pattern = args.output_dir / "frame_%06d.jpg"
        filters = [f"fps=1/{interval}"]
        if args.scale_width:
            filters.append(f"scale={args.scale_width}:-2")
        command = [executable, "-hide_banner", "-loglevel", "error", overwrite,
                   "-ss", f"{args.start:.6f}", "-i", str(args.video)]
        if args.end is not None:
            command += ["-t", f"{args.end - args.start:.6f}"]
        command += ["-vf", ",".join(filters), "-q:v", "2", str(pattern)]
        run(command)
        frames = sorted(args.output_dir.glob("frame_*.jpg"))
        for index, output in enumerate(frames, 1):
            timestamp = args.start + (index - 1) * interval
            manifest.append({"index": index, "timestamp": round(timestamp, 6), "path": str(output.resolve())})
        mode = {"type": "regular", "profile": args.profile, "interval": interval,
                "start": args.start, "end": args.end}

    payload = {"source": str(args.video.resolve()), "mode": mode, "frames": manifest}
    manifest_path = args.output_dir / "frames_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path.resolve()), "frame_count": len(manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
