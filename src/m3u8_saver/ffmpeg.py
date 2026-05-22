from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from .hardware import AccelChoice, detect_acceleration


class FfmpegError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise FfmpegError("ffmpeg is not installed or is not in PATH")


def build_ffmpeg_command(
    playlist_url: str,
    output_path: Path,
    user_agent: str,
    accept_language: str,
    cookie: str,
    referer: str,
    transcode: bool,
    preferred_accel: str,
) -> tuple[list[str], str]:
    ensure_ffmpeg()
    header_lines = [
        f"User-Agent: {user_agent}",
        f"Accept-Language: {accept_language}",
    ]
    if referer:
        header_lines.append(f"Referer: {referer}")
    if cookie:
        header_lines.append(f"Cookie: {cookie}")
    headers = "\r\n".join(header_lines) + "\r\n"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-headers",
        headers,
    ]

    accel_name = "stream-copy"
    accel: AccelChoice | None = None
    if transcode:
        accel = detect_acceleration(preferred_accel)
        if accel:
            command.extend(accel.ffmpeg_args)
            accel_name = accel.name
        else:
            accel_name = "software-transcode"

    command.extend(["-i", playlist_url, "-map", "0:v?", "-map", "0:a?"])

    if transcode:
        if accel:
            command.extend(accel.video_codec_args)
        else:
            command.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])
        command.extend(["-c:a", "aac", "-b:a", "160k"])
    else:
        command.extend(["-c", "copy", "-bsf:a", "aac_adtstoasc"])

    command.extend(["-movflags", "+faststart", str(output_path)])
    return command, accel_name


async def download_playlist(
    playlist_url: str,
    output_path: Path,
    user_agent: str,
    accept_language: str,
    cookie: str,
    referer: str,
    timeout_seconds: int,
    max_video_bytes: int,
    transcode: bool,
    preferred_accel: str,
) -> str:
    command, accel_name = build_ffmpeg_command(
        playlist_url=playlist_url,
        output_path=output_path,
        user_agent=user_agent,
        accept_language=accept_language,
        cookie=cookie,
        referer=referer,
        transcode=transcode,
        preferred_accel=preferred_accel,
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise FfmpegError("ffmpeg timed out") from exc

    if process.returncode != 0:
        message = stderr.decode(errors="replace")[-3000:]
        raise FfmpegError(f"ffmpeg failed with code {process.returncode}: {message}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise FfmpegError("ffmpeg did not create an output file")

    size = output_path.stat().st_size
    if size > max_video_bytes:
        try:
            os.remove(output_path)
        finally:
            raise FfmpegError(f"video is too large: {size} bytes")

    return accel_name
