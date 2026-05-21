from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AccelChoice:
    name: str
    ffmpeg_args: list[str]
    video_codec_args: list[str]


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout + result.stderr


def _ffmpeg_encoders() -> str:
    if not shutil.which("ffmpeg"):
        return ""
    return _run(["ffmpeg", "-hide_banner", "-encoders"])


def _has_command(command: str) -> bool:
    return shutil.which(command) is not None


def detect_acceleration(preferred: str = "auto") -> AccelChoice | None:
    encoders = _ffmpeg_encoders()
    if not encoders:
        return None

    preferred = preferred.lower()
    choices: list[AccelChoice] = []

    if "h264_nvenc" in encoders and (_has_command("nvidia-smi") or preferred == "nvidia"):
        choices.append(
            AccelChoice(
                name="nvidia-nvenc",
                ffmpeg_args=["-hwaccel", "cuda"],
                video_codec_args=["-c:v", "h264_nvenc", "-preset", "p4"],
            )
        )

    if "h264_qsv" in encoders and preferred in {"auto", "intel", "qsv"}:
        choices.append(
            AccelChoice(
                name="intel-qsv",
                ffmpeg_args=["-hwaccel", "qsv"],
                video_codec_args=["-c:v", "h264_qsv", "-preset", "veryfast"],
            )
        )

    if "h264_vaapi" in encoders and preferred in {"auto", "intel", "amd", "vaapi"}:
        choices.append(
            AccelChoice(
                name="vaapi",
                ffmpeg_args=["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"],
                video_codec_args=[
                    "-vf",
                    "format=nv12,hwupload",
                    "-c:v",
                    "h264_vaapi",
                    "-qp",
                    "23",
                ],
            )
        )

    if "h264_amf" in encoders and preferred in {"auto", "amd", "amf"}:
        choices.append(
            AccelChoice(
                name="amd-amf",
                ffmpeg_args=[],
                video_codec_args=["-c:v", "h264_amf", "-quality", "balanced"],
            )
        )

    if preferred != "auto":
        for choice in choices:
            if preferred in choice.name:
                return choice
    return choices[0] if choices else None
