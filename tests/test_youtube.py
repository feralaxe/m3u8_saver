from m3u8_saver.youtube import _quality_options, is_youtube_url


def test_youtube_url_detection() -> None:
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube_url("https://youtu.be/abc")
    assert not is_youtube_url("https://example.com/watch?v=abc")


def test_quality_options_for_1080p_source() -> None:
    options = _quality_options(1080, {1080, 720, 480, 360})

    assert [option.id for option in options] == ["best", "medium", "low"]


def test_quality_options_for_720p_source_has_no_best() -> None:
    options = _quality_options(720, {720, 480, 360})

    assert [option.id for option in options] == ["medium", "low"]


def test_quality_options_for_480p_source_has_only_low() -> None:
    options = _quality_options(480, {480, 360})

    assert [option.id for option in options] == ["low"]
