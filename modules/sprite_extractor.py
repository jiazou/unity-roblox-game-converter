"""
sprite_extractor.py — Extract individual sprites from Unity spritesheets.

Unity UI Image components reference sprites by GUID.  When the texture is a
spritesheet (atlas), the .meta file contains per-sprite rects that define
which sub-rectangle of the texture each sprite occupies.

This module:
  1. Parses TextureImporter metadata from .meta files to find sprite rects.
  2. Slices individual sprites from the source texture using Pillow.
  3. Writes them to an output directory for upload.

No other module is imported here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpriteRect:
    """A single sprite within a spritesheet."""
    name: str
    x: float
    y: float          # Unity coords: bottom-left origin
    width: float
    height: float
    pivot_x: float = 0.5
    pivot_y: float = 0.5


@dataclass
class SpriteSheetInfo:
    """Parsed spritesheet metadata from a .meta file."""
    texture_guid: str
    texture_path: Path
    sprite_mode: int          # 0=None, 1=Single, 2=Multiple
    sprites: list[SpriteRect] = field(default_factory=list)


@dataclass
class SpriteExtractionResult:
    """Result of extracting sprites from a Unity project."""
    extracted: list[tuple[str, Path]]       # (sprite_name, output_path)
    sprite_guid_to_file: dict[str, Path]    # guid → extracted PNG path
    warnings: list[str] = field(default_factory=list)
    total_spritesheets: int = 0
    total_sprites_extracted: int = 0


# ---------------------------------------------------------------------------
# .meta file sprite parsing
# ---------------------------------------------------------------------------

# Regex to capture the spriteMode value
_RE_SPRITE_MODE = re.compile(r"^\s*spriteMode:\s*(\d+)", re.MULTILINE)

# Regex for individual sprite entries in the spriteSheet section.
# Unity .meta format nests sprites under:
#   spriteSheet:
#     sprites:
#     - name: SpriteName
#       rect:
#         serializedVersion: 2
#         x: 0
#         y: 128
#         width: 64
#         height: 64
#       ...
_RE_SPRITE_NAME = re.compile(r"^\s*-\s*name:\s*(.+)$", re.MULTILINE)


def _parse_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def parse_spritesheet_meta(meta_path: Path) -> SpriteSheetInfo | None:
    """
    Parse a texture's .meta file for spritesheet data.

    Returns SpriteSheetInfo if the texture has sprite mode > 0 and sprites
    are defined, otherwise None.
    """
    try:
        text = meta_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Extract GUID
    guid_m = re.search(r"^guid:\s*([0-9a-fA-F]{32})\s*$", text, re.MULTILINE)
    if not guid_m:
        return None
    guid = guid_m.group(1)

    # Check sprite mode
    mode_m = _RE_SPRITE_MODE.search(text)
    sprite_mode = int(mode_m.group(1)) if mode_m else 0
    if sprite_mode == 0:
        return None

    texture_path = meta_path.with_suffix("")  # strip .meta

    info = SpriteSheetInfo(
        texture_guid=guid,
        texture_path=texture_path,
        sprite_mode=sprite_mode,
    )

    # For single-sprite textures (mode 1), the entire image is the sprite
    if sprite_mode == 1:
        info.sprites.append(SpriteRect(
            name=texture_path.stem,
            x=0, y=0, width=0, height=0,  # 0,0 means full image
        ))
        return info

    # For multiple sprites (mode 2), parse the spriteSheet section
    sprites = _parse_sprite_entries(text)
    info.sprites = sprites
    return info if sprites else None


def _parse_sprite_entries(meta_text: str) -> list[SpriteRect]:
    """Parse individual sprite rect entries from meta file text."""
    sprites: list[SpriteRect] = []

    # Find the spriteSheet: section
    sheet_match = re.search(r"^\s*spriteSheet:", meta_text, re.MULTILINE)
    if not sheet_match:
        return sprites

    sheet_section = meta_text[sheet_match.start():]

    # Find sprites: list within spriteSheet
    sprites_match = re.search(r"^\s*sprites:", sheet_section, re.MULTILINE)
    if not sprites_match:
        return sprites

    sprites_text = sheet_section[sprites_match.end():]

    # Split into individual sprite entries (each starts with "    - ")
    # Stop at the next top-level key (non-indented or less-indented line)
    entries: list[str] = []
    current: list[str] = []
    for line in sprites_text.splitlines():
        # Stop at next top-level section
        stripped = line.lstrip()
        if stripped and not line[0].isspace() and not stripped.startswith("-"):
            break
        if re.match(r"^\s+-\s+", line) or re.match(r"^\s+-$", line):
            if current:
                entries.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        entries.append("\n".join(current))

    for entry in entries:
        sprite = _parse_single_sprite(entry)
        if sprite:
            sprites.append(sprite)

    return sprites


def _parse_single_sprite(entry_text: str) -> SpriteRect | None:
    """Parse a single sprite entry from YAML-like text."""
    # Extract name
    name_m = re.search(r"name:\s*(.+?)$", entry_text, re.MULTILINE)
    if not name_m:
        return None
    name = name_m.group(1).strip()

    # Extract rect values
    rect_section = re.search(
        r"rect:.*?x:\s*([\d.e+-]+).*?y:\s*([\d.e+-]+).*?"
        r"width:\s*([\d.e+-]+).*?height:\s*([\d.e+-]+)",
        entry_text, re.DOTALL,
    )
    if not rect_section:
        return None

    x = _parse_float(rect_section.group(1))
    y = _parse_float(rect_section.group(2))
    w = _parse_float(rect_section.group(3))
    h = _parse_float(rect_section.group(4))

    # Extract pivot (optional)
    pivot_x, pivot_y = 0.5, 0.5
    pivot_m = re.search(
        r"pivot:\s*\{?\s*x:\s*([\d.e+-]+)\s*,?\s*y:\s*([\d.e+-]+)",
        entry_text,
    )
    if pivot_m:
        pivot_x = _parse_float(pivot_m.group(1))
        pivot_y = _parse_float(pivot_m.group(2))

    return SpriteRect(name=name, x=x, y=y, width=w, height=h,
                      pivot_x=pivot_x, pivot_y=pivot_y)


# ---------------------------------------------------------------------------
# Sprite slicing
# ---------------------------------------------------------------------------

def _slice_sprite(img: Any, sprite: SpriteRect) -> Any:
    """
    Crop a single sprite from a spritesheet image.

    Unity uses bottom-left origin for sprite rects.
    Pillow uses top-left origin. We need to flip Y.
    """
    img_w, img_h = img.size

    # Full-image sprite (single mode)
    if sprite.width == 0 and sprite.height == 0:
        return img.copy()

    # Convert from Unity bottom-left to Pillow top-left
    left = int(sprite.x)
    bottom_unity = int(sprite.y)
    w = int(sprite.width)
    h = int(sprite.height)

    # Pillow box: (left, upper, right, lower)
    upper = img_h - bottom_unity - h
    box = (left, upper, left + w, upper + h)

    # Clamp to image bounds
    box = (
        max(0, box[0]),
        max(0, box[1]),
        min(img_w, box[2]),
        min(img_h, box[3]),
    )

    return img.crop(box)


def extract_sprites(
    guid_index: Any,
    output_dir: Path,
) -> SpriteExtractionResult:
    """
    Scan all texture assets for spritesheets and extract individual sprites.

    Args:
        guid_index: A GuidIndex with resolved .meta files.
        output_dir: Directory to write extracted sprite PNGs.

    Returns:
        SpriteExtractionResult with extracted files and GUID mapping.
    """
    if Image is None:
        return SpriteExtractionResult(
            extracted=[],
            sprite_guid_to_file={},
            warnings=["Pillow not installed — sprite extraction skipped"],
        )

    result = SpriteExtractionResult(extracted=[], sprite_guid_to_file={})
    sprites_dir = output_dir / "sprites"

    # Scan all texture GUIDs for spritesheet metadata
    texture_entries = guid_index.filter_by_kind("texture")

    for guid, entry in texture_entries.items():
        meta_path = Path(str(entry.asset_path) + ".meta")
        if not meta_path.exists():
            continue

        sheet_info = parse_spritesheet_meta(meta_path)
        if not sheet_info or not sheet_info.sprites:
            continue

        if not sheet_info.texture_path.exists():
            result.warnings.append(
                f"Texture file missing for spritesheet: {sheet_info.texture_path}"
            )
            continue

        result.total_spritesheets += 1

        try:
            img = Image.open(sheet_info.texture_path)
        except Exception as exc:
            result.warnings.append(
                f"Failed to open texture {sheet_info.texture_path.name}: {exc}"
            )
            continue

        for sprite_rect in sheet_info.sprites:
            try:
                cropped = _slice_sprite(img, sprite_rect)
            except Exception as exc:
                result.warnings.append(
                    f"Failed to slice sprite '{sprite_rect.name}' "
                    f"from {sheet_info.texture_path.name}: {exc}"
                )
                continue

            # Sanitise filename
            safe_name = re.sub(r'[^\w\-.]', '_', sprite_rect.name)
            out_path = sprites_dir / f"{safe_name}.png"

            sprites_dir.mkdir(parents=True, exist_ok=True)
            cropped.save(out_path, "PNG")

            result.extracted.append((sprite_rect.name, out_path))
            result.total_sprites_extracted += 1

            # Map the sprite's source GUID to the extracted file.
            # The GUID identifies the texture; for single-sprite textures
            # this is a 1:1 mapping.  For spritesheets we use
            # "guid:spritename" as the compound key.
            if sheet_info.sprite_mode == 1:
                result.sprite_guid_to_file[guid] = out_path
            else:
                result.sprite_guid_to_file[f"{guid}:{sprite_rect.name}"] = out_path

        img.close()

    if result.total_sprites_extracted:
        logger.info(
            "Extracted %d sprites from %d spritesheets",
            result.total_sprites_extracted,
            result.total_spritesheets,
        )

    return result
