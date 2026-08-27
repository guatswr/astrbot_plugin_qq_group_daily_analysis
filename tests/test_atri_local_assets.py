from __future__ import annotations

import re
from urllib.parse import quote

from src.infrastructure.reporting.local_assets import (
    ATRI_ASSET_DIR,
    inline_atri_assets,
)

ATRI_TEMPLATE_DIR = ATRI_ASSET_DIR.parent
REMOTE_FILENAME_PATTERN = re.compile(
    r"/file/(?P<filename>[^\"'()<>\s]+\.(?:gif|webp|woff2))"
)


def _referenced_asset_names() -> set[str]:
    names: set[str] = set()
    for template_path in ATRI_TEMPLATE_DIR.glob("*.html"):
        template = template_path.read_text(encoding="utf-8")
        names.update(
            match.group("filename")
            for match in REMOTE_FILENAME_PATTERN.finditer(template)
        )
    return names


def test_all_atri_remote_assets_are_packaged() -> None:
    referenced = _referenced_asset_names()
    packaged = {
        path.name
        for path in ATRI_ASSET_DIR.iterdir()
        if path.is_file() and path.name != "README.md"
    }

    assert len(referenced) == 33
    assert referenced == packaged


def test_packaged_atri_assets_have_expected_file_signatures() -> None:
    for asset_path in ATRI_ASSET_DIR.iterdir():
        if not asset_path.is_file() or asset_path.name == "README.md":
            continue
        header = asset_path.read_bytes()[:12]
        if asset_path.suffix == ".woff2":
            assert header.startswith(b"wOF2"), asset_path.name
        elif asset_path.suffix == ".gif":
            assert header.startswith((b"GIF87a", b"GIF89a")), asset_path.name
        elif asset_path.suffix == ".webp":
            assert header.startswith(b"RIFF") and header[8:12] == b"WEBP", (
                asset_path.name
            )


def test_inline_atri_assets_replaces_local_files_and_reports_missing() -> None:
    mirror = "https://assets.example.test"
    webp_name = "1775130588385_1774881257527_bg1.webp"
    gif_name = "1775132804506_1774881263342_观察.gif"
    html = (
        f'<style>body{{background:url("{mirror}/file/{webp_name}")}}</style>'
        f'<img src="{mirror}/file/{quote(gif_name)}">'
        f'<img src="{mirror}/file/not-packaged.webp">'
    )

    result = inline_atri_assets(html, mirror)

    assert "data:image/webp;base64,UklGR" in result.html
    assert "data:image/gif;base64,R0lGOD" in result.html
    assert f"{mirror}/file/{webp_name}" not in result.html
    assert f"{mirror}/file/{quote(gif_name)}" not in result.html
    assert f"{mirror}/file/not-packaged.webp" in result.html
    assert result.replacements == 2
    assert result.unique_assets == 2
    assert result.missing_assets == ("not-packaged.webp",)


def test_inline_atri_assets_does_not_allow_path_traversal() -> None:
    mirror = "https://assets.example.test"
    html = f'<img src="{mirror}/file/%2E%2E%2Fmetadata.yaml">'

    result = inline_atri_assets(html, mirror)

    assert result.html == html
    assert result.replacements == 0
    assert result.missing_assets == ("../metadata.yaml",)


def test_inline_atri_assets_accepts_trailing_slash_in_mirror_setting() -> None:
    mirror = "https://assets.example.test/"
    filename = "1775130588385_1774881257527_bg1.webp"
    html = f'<img src="{mirror}/file/{filename}">'

    result = inline_atri_assets(html, mirror)

    assert result.replacements == 1
    assert result.html.startswith('<img src="data:image/webp;base64,')
