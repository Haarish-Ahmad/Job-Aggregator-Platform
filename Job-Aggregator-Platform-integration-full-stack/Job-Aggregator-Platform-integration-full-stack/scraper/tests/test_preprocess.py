from scraper.preprocess import clean_markdown, content_hash, truncate


def test_clean_markdown_drops_json_blobs_and_long_lines():
    md = "Title\n\n`{\"themeOptions\": 1}`\n\n" + "x" * 5000 + "\n\nReal text here"
    out = clean_markdown(md)
    assert "themeOptions" not in out
    assert "xxxx" not in out
    assert out == "Title\n\nReal text here"


def test_clean_markdown_on_real_firecrawl_output():
    from pathlib import Path

    raw = (Path(__file__).parent.parent / "fixtures" / "detail_wait5000.md").read_text()
    out = clean_markdown(raw)
    assert len(raw) > 400_000
    assert len(out) < 10_000
    assert "Responsibilities" in out


def test_truncate_cuts_on_line_boundary():
    assert truncate("aaa\nbbb\nccc", 9) == "aaa\nbbb"
    assert truncate("short", 100) == "short"


def test_content_hash_is_stable_sha256():
    assert content_hash("a") == content_hash("a")
    assert content_hash("a") != content_hash("b")
    assert len(content_hash("a")) == 64
