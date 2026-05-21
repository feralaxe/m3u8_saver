from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup


M3U8_PATTERN = re.compile(
    r"""(?P<url>(?:https?:)?//[^\s"'<>\\]+?\.m3u8(?:\?[^\s"'<>\\]*)?|[^\s"'<>\\]+?\.m3u8(?:\?[^\s"'<>\\]*)?)""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VideoCandidate:
    title: str
    playlist_url: str
    source_url: str


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url
    if parsed.scheme == "":
        return "https://" + url
    return url


def _clean_candidate(raw: str, base_url: str) -> str | None:
    value = html.unescape(unquote(raw.strip().strip("\"'")))
    if not value or ".m3u8" not in value.lower():
        return None
    absolute = urljoin(base_url, value)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    query = "&".join(f"{k}={v}" for k, v in parse_qsl(parsed.query, keep_blank_values=True))
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


def _title_for(url: str, index: int) -> str:
    parsed = urlparse(url)
    filename = parsed.path.rstrip("/").split("/")[-1] or "playlist.m3u8"
    return f"{index}. {filename}"


def extract_m3u8_urls(page_text: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    searchable_text = page_text.replace("\\/", "/")

    if "<" in page_text and ">" in page_text:
        soup = BeautifulSoup(page_text, "html.parser")
        for tag in soup.find_all(["source", "video", "a"]):
            for attr in ("src", "href"):
                value = tag.get(attr)
                if value and ".m3u8" in value.lower():
                    cleaned = _clean_candidate(value, base_url)
                    if cleaned:
                        candidates.append(cleaned)

    for match in M3U8_PATTERN.finditer(searchable_text):
        cleaned = _clean_candidate(match.group("url"), base_url)
        if cleaned:
            candidates.append(cleaned)

    return list(dict.fromkeys(candidates))


async def discover_videos(url: str, timeout: float, user_agent: str) -> list[VideoCandidate]:
    source_url = normalize_url(url)
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,*/*"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(source_url)
        response.raise_for_status()
        final_url = str(response.url)
        content_type = response.headers.get("content-type", "")
        text = response.text

    if ".m3u8" in final_url.lower() or "mpegurl" in content_type.lower():
        urls = [final_url]
    else:
        urls = extract_m3u8_urls(text, final_url)

    return [
        VideoCandidate(title=_title_for(playlist_url, index), playlist_url=playlist_url, source_url=source_url)
        for index, playlist_url in enumerate(urls, start=1)
    ]
