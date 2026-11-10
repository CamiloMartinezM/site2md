"""Tests for find_html_files with a missing input directory."""

from pathlib import Path

from site2md.finder import find_html_files


def test_missing_directory_returns_empty_list(tmp_path: Path) -> None:
    assert find_html_files(tmp_path / "does-not-exist") == []


def test_existing_directory_lists_html_files(tmp_path: Path) -> None:
    (tmp_path / "b.html").write_text("<p>b</p>", encoding="utf-8")
    (tmp_path / "index.html").write_text("<p>home</p>", encoding="utf-8")
    found = find_html_files(tmp_path)
    assert [p.name for p in found] == ["index.html", "b.html"]
