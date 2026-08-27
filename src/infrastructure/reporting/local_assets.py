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

_SCREENSHOT_UNUSED_FONTS = {
    "1775130738049_1774880717027_LXGWWenKaiMono-Regular.woff2",
    "1775130739223_1774880715380_LXGWWenKai-Medium.woff2",
}

_SCREENSHOT_GIF_TO_WEBP = {
    "1775132804506_1774881263342_观察.gif": "1775130585446_1774881263342_观察.webp",
    "1775132805081_1774881262835_疑惑.gif": "1775130581843_1774881262835_疑惑.webp",
    "1775132805485_1774881263748_可爱-3.gif": "1775130588642_1774881263748_可爱-3.webp",
    "1775132808652_1774881267385_得意-1.gif": "1775130599184_1774881267385_得意-1.webp",
    "1775132809943_1774881264350_睡觉.gif": "1775130591277_1774881264350_睡觉.webp",
    "1775132811492_1774881264336_不要.gif": "1775130591487_1774881264336_不要.webp",
    "1775132813334_1774881267181_得意.gif": "1775130598778_1774881267181_得意.webp",
    "1775132814629_1774881270686_爱心.gif": "1775130605165_1774881270686_爱心.webp",
    "1775132815504_1774881268554_可爱.gif": "1775130600453_1774881268554_可爱.webp",
    "1775132817115_1774881269400_可爱-1.gif": "1775130609119_1774881269400_可爱-1.webp",
}

_FONT_FACE_PATTERN = re.compile(r"@font-face\s*\{[^{}]*\}", re.DOTALL)


@dataclass(frozen=True)
class AssetInliningResult:
    """Summary of one local-asset inlining pass."""

    html: str
    replacements: int
    unique_assets: int
    missing_assets: tuple[str, ...]
    removed_font_faces: int = 0
    static_image_substitutions: int = 0


def _optimize_atri_screenshot_html(html: str) -> tuple[str, int, int]:
    """Reduce resources that unnecessarily delay a one-frame screenshot."""

    removed_font_faces = 0

    def filter_font_face(match: re.Match[str]) -> str:
        nonlocal removed_font_faces
        block = match.group(0)
        if any(filename in block for filename in _SCREENSHOT_UNUSED_FONTS):
            removed_font_faces += 1
            return ""
        return block

    optimized_html = _FONT_FACE_PATTERN.sub(filter_font_face, html)
    static_image_substitutions = 0
    for gif_name, webp_name in _SCREENSHOT_GIF_TO_WEBP.items():
        occurrences = optimized_html.count(gif_name)
        if occurrences:
            optimized_html = optimized_html.replace(gif_name, webp_name)
            static_image_substitutions += occurrences

    return optimized_html, removed_font_faces, static_image_substitutions


def inline_atri_assets(
    html: str,
    mirror_url: str,
    *,
    asset_dir: Path = ATRI_ASSET_DIR,
    optimize_for_screenshot: bool = False,
) -> AssetInliningResult:
    """Replace ATRI mirror URLs with data URIs loaded from packaged assets.

    AstrBot's custom HTML renderer may run on a remote T2I service, where a
    local ``file://`` path from the bot container is unavailable. Embedding the
    packaged files as data URIs keeps the generated HTML fully self-contained
    while still sourcing every asset from the local plugin installation.
    """

    if not html or not mirror_url:
        return AssetInliningResult(html, 0, 0, ())

    removed_font_faces = 0
    static_image_substitutions = 0
    if optimize_for_screenshot:
        html, removed_font_faces, static_image_substitutions = (
            _optimize_atri_screenshot_html(html)
        )

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
        removed_font_faces=removed_font_faces,
        static_image_substitutions=static_image_substitutions,
    )
