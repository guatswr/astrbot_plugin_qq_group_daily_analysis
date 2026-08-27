"""Local asset helpers for self-contained report HTML."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ATRI_ASSET_DIR = Path(__file__).resolve().parent / "templates" / "ATRI" / "assets"
ATRI_DEFAULT_MIRROR = "https://tc.ciallo.ccwu.cc"

_MIME_TYPES = {
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}


@dataclass(frozen=True)
class AssetInliningResult:
    """Summary of one local-asset inlining pass."""

    html: str
    replacements: int
    unique_assets: int
    missing_assets: tuple[str, ...]


def inline_atri_assets(
    html: str,
    mirror_url: str,
    *,
    asset_dir: Path = ATRI_ASSET_DIR,
) -> AssetInliningResult:
    """Replace ATRI mirror URLs with data URIs loaded from packaged assets.

    AstrBot's custom HTML renderer may run on a remote T2I service, where a
    local ``file://`` path from the bot container is unavailable. Embedding the
    packaged files as data URIs keeps the generated HTML fully self-contained
    while still sourcing every asset from the local plugin installation.
    """

    if not html or not mirror_url:
        return AssetInliningResult(html, 0, 0, ())

    mirror_base = mirror_url.rstrip("/")
    pattern = re.compile(
        rf"{re.escape(mirror_base)}/+file/(?P<filename>[^\"'()<>\s?#]+)"
    )
    data_uri_cache: dict[str, str] = {}
    missing_assets: set[str] = set()
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements

        filename = unquote(match.group("filename"))
        # Remote template references must be flat filenames. Reject separators
        # so a malformed/custom template cannot read arbitrary local files.
        if filename != Path(filename).name or "/" in filename or "\\" in filename:
            missing_assets.add(filename)
            return match.group(0)

        data_uri = data_uri_cache.get(filename)
        if data_uri is None:
            asset_path = asset_dir / filename
            mime_type = _MIME_TYPES.get(asset_path.suffix.lower())
            if mime_type is None or not asset_path.is_file():
                missing_assets.add(filename)
                return match.group(0)

            encoded = base64.b64encode(asset_path.read_bytes()).decode("ascii")
            data_uri = f"data:{mime_type};base64,{encoded}"
            data_uri_cache[filename] = data_uri

        replacements += 1
        return data_uri

    inlined_html = pattern.sub(replace, html)
    return AssetInliningResult(
        html=inlined_html,
        replacements=replacements,
        unique_assets=len(data_uri_cache),
        missing_assets=tuple(sorted(missing_assets)),
    )
