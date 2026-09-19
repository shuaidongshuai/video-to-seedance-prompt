#!/usr/bin/env python3
"""Probe a source video without modifying it and emit normalized JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


def fail(message: str, code: int = 2) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def ratio(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        return round(float(Fraction(value)), 6)
    except (ValueError, ZeroDivisionError):
        return None


def number(value: Any) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        fail("ffprobe is not available on PATH")
    command = [
        executable,
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        fail(result.stderr.strip() or "ffprobe failed", result.returncode)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"invalid ffprobe JSON: {exc}")


def normalize(path: Path, raw: dict[str, Any], include_hash: bool) -> dict[str, Any]:
    streams = raw.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    primary = videos[0] if videos else {}
    width = primary.get("width")
    height = primary.get("height")
    display_aspect = primary.get("display_aspect_ratio")
    if not display_aspect and width and height:
        display_aspect = f"{width}:{height}"
    tags = primary.get("tags") or {}
    side_data = primary.get("side_data_list") or []
    rotation = tags.get("rotate")
    if rotation is None:
        for item in side_data:
            if "rotation" in item:
                rotation = item["rotation"]
                break

    duration = number((raw.get("format") or {}).get("duration"))
    if duration is None:
        durations = [number(stream.get("duration")) for stream in streams]
        duration = max((item for item in durations if item is not None), default=None)

    output: dict[str, Any] = {
        "source": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "duration_seconds": duration,
        "video_present": bool(videos),
        "audio_present": bool(audios),
        "width": width,
        "height": height,
        "display_aspect_ratio": display_aspect,
        "fps": ratio(primary.get("avg_frame_rate") or primary.get("r_frame_rate")),
        "frame_count": int(primary["nb_frames"]) if str(primary.get("nb_frames", "")).isdigit() else None,
        "video_codec": primary.get("codec_name"),
        "pixel_format": primary.get("pix_fmt"),
        "color_space": primary.get("color_space"),
        "color_transfer": primary.get("color_transfer"),
        "rotation_degrees": number(rotation),
        "audio_streams": [
            {
                "index": stream.get("index"),
                "codec": stream.get("codec_name"),
                "sample_rate": int(stream["sample_rate"]) if str(stream.get("sample_rate", "")).isdigit() else None,
                "channels": stream.get("channels"),
                "channel_layout": stream.get("channel_layout"),
            }
            for stream in audios
        ],
    }
    if include_hash:
        output["sha256"] = sha256(path)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="source video path")
    parser.add_argument("--no-hash", action="store_true", help="skip SHA-256 for faster probing")
    parser.add_argument("--compact", action="store_true", help="print compact JSON")
    args = parser.parse_args()
    if not args.video.is_file():
        fail(f"video does not exist: {args.video}")
    payload = normalize(args.video, run_ffprobe(args.video), not args.no_hash)
    indent = None if args.compact else 2
    print(json.dumps(payload, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
