"""Tests for sable.shared.download — URL detection, missing file error, yt-dlp caching."""
import sys
import types
import pytest


def test_is_url_identifies_http_and_https():
    from sable.shared.download import _is_url

    assert _is_url("http://example.com/video") is True
    assert _is_url("https://youtu.be/abc123") is True
    assert _is_url("/local/path/video.mp4") is False
    assert _is_url("relative/path.mp4") is False
    assert _is_url("ftp://example.com/video") is False


def test_maybe_download_raises_for_missing_local_file():
    from sable.shared.download import maybe_download

    missing = "/nonexistent/path/video.mp4"
    with pytest.raises(FileNotFoundError) as exc_info:
        maybe_download(missing)

    assert missing in str(exc_info.value)


def test_maybe_download_uses_url_hash_for_cache_key(tmp_path, monkeypatch):
    """Same URL → same download dir; yt-dlp called once, second call hits cache."""
    download_count = [0]

    def fake_ydl_constructor(ydl_opts):
        class FakeDL:
            def __enter__(self): return self
            def __exit__(self, *a): return False

            def download(self, urls):
                import hashlib
                from sable.shared.paths import downloads_dir
                url_hash = hashlib.sha256(urls[0].encode()).hexdigest()[:12]
                dest = downloads_dir() / url_hash / "video.mp4"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"fake video data")
                download_count[0] += 1

        return FakeDL()

    fake_yt_dlp = types.ModuleType("yt_dlp")
    fake_yt_dlp.YoutubeDL = fake_ydl_constructor
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_yt_dlp)

    from sable.shared.download import maybe_download

    url = "https://www.youtube.com/watch?v=test123"
    p1 = maybe_download(url)
    p2 = maybe_download(url)

    assert p1 == p2
    assert download_count[0] == 1, f"Expected yt-dlp called once, got {download_count[0]}"
    assert p2.exists()
