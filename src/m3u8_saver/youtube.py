from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


LOGGER = logging.getLogger(__name__)
YOUTUBE_HOST_PATTERN = re.compile(r"(^|\.)youtube\.com$|(^|\.)youtu\.be$", re.IGNORECASE)


class YouTubeError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeQuality:
    id: str
    label: str
    max_height: int | None
    format_selector: str


@dataclass(frozen=True)
class YouTubeVideo:
    title: str
    webpage_url: str
    max_height: int
    qualities: list[YouTubeQuality]


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return bool(YOUTUBE_HOST_PATTERN.search(host))


def _format_heights(info: dict) -> set[int]:
    heights: set[int] = set()
    for fmt in info.get("formats") or []:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if isinstance(height, int) and height > 0 and vcodec and vcodec != "none":
            heights.add(height)
    return heights


def _quality_options(max_height: int, heights: set[int]) -> list[YouTubeQuality]:
    options: list[YouTubeQuality] = []
    if max_height > 720:
        options.append(
            YouTubeQuality(
                id="best",
                label=f"Best ({max_height}p)",
                max_height=None,
                format_selector="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            )
        )

    if max_height >= 720 and any(height >= 720 for height in heights):
        options.append(
            YouTubeQuality(
                id="medium",
                label="Medium (720p)",
                max_height=720,
                format_selector=(
                    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                ),
            )
        )

    options.append(
        YouTubeQuality(
            id="low",
            label="Low (480p)",
            max_height=480,
            format_selector=(
                "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo[height<=480]+bestaudio/best[height<=480]/worstvideo+bestaudio/worst"
            ),
        )
    )
    return options


def _base_opts(cookie: str = "") -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if cookie:
        opts["http_headers"] = {"Cookie": cookie}
    return opts


def _inspect_sync(url: str, cookie: str) -> YouTubeVideo:
    try:
        with YoutubeDL(_base_opts(cookie)) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise YouTubeError(f"YouTube could not be inspected: {exc}") from exc

    if not info:
        raise YouTubeError("YouTube did not return video information.")

    heights = _format_heights(info)
    max_height = max(heights, default=0)
    if max_height <= 0:
        raise YouTubeError("No downloadable video formats were found.")

    return YouTubeVideo(
        title=info.get("title") or "YouTube video",
        webpage_url=info.get("webpage_url") or url,
        max_height=max_height,
        qualities=_quality_options(max_height, heights),
    )


async def inspect_youtube(url: str, cookie: str = "") -> YouTubeVideo:
    return await asyncio.to_thread(_inspect_sync, url, cookie)


def _download_sync(
    url: str,
    output_dir: Path,
    quality: YouTubeQuality,
    cookie: str,
    max_video_bytes: int,
) -> Path:
    output_template = str(output_dir / "youtube.%(ext)s")
    opts = {
        **_base_opts(cookie),
        "format": quality.format_selector,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = Path(ydl.prepare_filename(info))
    except DownloadError as exc:
        raise YouTubeError(f"YouTube download failed: {exc}") from exc

    output_path = prepared.with_suffix(".mp4")
    if not output_path.exists():
        matches = sorted(output_dir.glob("youtube.*"), key=lambda path: path.stat().st_mtime, reverse=True)
        output_path = matches[0] if matches else output_path

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise YouTubeError("YouTube download did not create an output file.")

    size = output_path.stat().st_size
    if size > max_video_bytes:
        output_path.unlink(missing_ok=True)
        raise YouTubeError(f"video is too large: {size} bytes")

    return output_path


async def download_youtube(
    url: str,
    output_dir: Path,
    quality: YouTubeQuality,
    cookie: str,
    max_video_bytes: int,
) -> Path:
    LOGGER.info("youtube download start quality=%s url=%s", quality.id, url)
    return await asyncio.to_thread(_download_sync, url, output_dir, quality, cookie, max_video_bytes)
