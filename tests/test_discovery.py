from m3u8_saver.discovery import extract_m3u8_urls, normalize_url


def test_extracts_absolute_and_relative_m3u8_urls() -> None:
    html = """
    <video><source src="/live/master.m3u8?token=abc"></video>
    <script>var x = "https://cdn.example.com/vod/index.m3u8";</script>
    """

    assert extract_m3u8_urls(html, "https://site.example/watch/1") == [
        "https://site.example/live/master.m3u8?token=abc",
        "https://cdn.example.com/vod/index.m3u8",
    ]


def test_normalize_url_adds_scheme() -> None:
    assert normalize_url("example.com/video") == "https://example.com/video"


def test_extracts_json_escaped_urls() -> None:
    html = r'{"file":"https:\/\/cdn.example.com\/video\/master.m3u8?x=1"}'

    assert extract_m3u8_urls(html, "https://site.example/watch/1") == [
        "https://cdn.example.com/video/master.m3u8?x=1",
    ]
