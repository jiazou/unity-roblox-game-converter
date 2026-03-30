"""Tests for modules/sprite_extractor.py."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest

from modules.sprite_extractor import (
    SpriteRect,
    SpriteSheetInfo,
    SpriteExtractionResult,
    parse_spritesheet_meta,
    _parse_sprite_entries,
    _parse_single_sprite,
    _slice_sprite,
    extract_sprites,
)

# Try importing Pillow — skip image tests if not available
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


# ---------------------------------------------------------------------------
# Fixtures: sample .meta file contents
# ---------------------------------------------------------------------------

SINGLE_SPRITE_META = """\
fileFormatVersion: 2
guid: aaaa1111bbbb2222cccc3333dddd4444
TextureImporter:
  spriteMode: 1
  spriteBorder: {x: 0, y: 0, z: 0, w: 0}
  spritePixelsToUnits: 100
"""

MULTI_SPRITE_META = """\
fileFormatVersion: 2
guid: 1234567890abcdef1234567890abcdef
TextureImporter:
  spriteMode: 2
  spriteSheet:
    serializedVersion: 2
    sprites:
    - serializedVersion: 2
      name: Icon_Sword
      rect:
        serializedVersion: 2
        x: 0
        y: 64
        width: 32
        height: 32
      alignment: 0
      pivot: {x: 0.5, y: 0.5}
      border: {x: 0, y: 0, z: 0, w: 0}
    - serializedVersion: 2
      name: Icon_Shield
      rect:
        serializedVersion: 2
        x: 32
        y: 64
        width: 32
        height: 32
      alignment: 0
      pivot: {x: 0.25, y: 0.75}
      border: {x: 0, y: 0, z: 0, w: 0}
  spritePackingTag: icons
"""

NO_SPRITE_META = """\
fileFormatVersion: 2
guid: eeee5555ffff6666aaaa7777bbbb8888
TextureImporter:
  spriteMode: 0
  mipmaps:
    mipMapMode: 0
"""


# ---------------------------------------------------------------------------
# parse_spritesheet_meta
# ---------------------------------------------------------------------------

class TestParseSpritesheetMeta:
    def test_single_sprite_mode(self, tmp_path: Path) -> None:
        tex = tmp_path / "player.png"
        tex.write_bytes(b"fake")
        meta = tmp_path / "player.png.meta"
        meta.write_text(SINGLE_SPRITE_META)

        result = parse_spritesheet_meta(meta)
        assert result is not None
        assert result.texture_guid == "aaaa1111bbbb2222cccc3333dddd4444"
        assert result.sprite_mode == 1
        assert len(result.sprites) == 1
        assert result.sprites[0].name == "player"
        assert result.texture_path == tex

    def test_multiple_sprite_mode(self, tmp_path: Path) -> None:
        meta = tmp_path / "icons.png.meta"
        meta.write_text(MULTI_SPRITE_META)

        result = parse_spritesheet_meta(meta)
        assert result is not None
        assert result.sprite_mode == 2
        assert len(result.sprites) == 2
        assert result.sprites[0].name == "Icon_Sword"
        assert result.sprites[0].x == 0
        assert result.sprites[0].y == 64
        assert result.sprites[0].width == 32
        assert result.sprites[0].height == 32
        assert result.sprites[1].name == "Icon_Shield"
        assert result.sprites[1].pivot_x == pytest.approx(0.25)
        assert result.sprites[1].pivot_y == pytest.approx(0.75)

    def test_no_sprite_mode_returns_none(self, tmp_path: Path) -> None:
        meta = tmp_path / "ground.png.meta"
        meta.write_text(NO_SPRITE_META)

        result = parse_spritesheet_meta(meta)
        assert result is None

    def test_missing_file_returns_none(self) -> None:
        result = parse_spritesheet_meta(Path("/nonexistent/tex.png.meta"))
        assert result is None

    def test_no_guid_returns_none(self, tmp_path: Path) -> None:
        meta = tmp_path / "bad.png.meta"
        meta.write_text("fileFormatVersion: 2\nspriteMode: 1\n")
        assert parse_spritesheet_meta(meta) is None


# ---------------------------------------------------------------------------
# _parse_sprite_entries
# ---------------------------------------------------------------------------

class TestParseSpriteEntries:
    def test_two_sprites(self) -> None:
        sprites = _parse_sprite_entries(MULTI_SPRITE_META)
        assert len(sprites) == 2
        assert sprites[0].name == "Icon_Sword"
        assert sprites[1].name == "Icon_Shield"

    def test_no_spritesheet_section(self) -> None:
        assert _parse_sprite_entries("spriteMode: 1\n") == []

    def test_empty_sprites_list(self) -> None:
        text = "  spriteSheet:\n    sprites:\nfoo: bar\n"
        assert _parse_sprite_entries(text) == []


# ---------------------------------------------------------------------------
# _parse_single_sprite
# ---------------------------------------------------------------------------

class TestParseSingleSprite:
    def test_full_entry(self) -> None:
        entry = """\
    - serializedVersion: 2
      name: Coin
      rect:
        serializedVersion: 2
        x: 100
        y: 200
        width: 50
        height: 50
      pivot: {x: 0.5, y: 0.5}"""
        sprite = _parse_single_sprite(entry)
        assert sprite is not None
        assert sprite.name == "Coin"
        assert sprite.x == 100
        assert sprite.y == 200
        assert sprite.width == 50
        assert sprite.height == 50

    def test_no_name_returns_none(self) -> None:
        entry = "    rect:\n      x: 0\n      y: 0\n      width: 10\n      height: 10\n"
        assert _parse_single_sprite(entry) is None

    def test_no_rect_returns_none(self) -> None:
        entry = "    name: NoRect\n    pivot: {x: 0.5, y: 0.5}\n"
        assert _parse_single_sprite(entry) is None


# ---------------------------------------------------------------------------
# _slice_sprite (image cropping)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
class TestSliceSprite:
    def test_full_image_sprite(self) -> None:
        img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        sprite = SpriteRect(name="Full", x=0, y=0, width=0, height=0)
        result = _slice_sprite(img, sprite)
        assert result.size == (64, 64)

    def test_crop_bottom_left(self) -> None:
        """Unity Y=0 is bottom. A 16x16 sprite at y=0 should crop from bottom."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
        # Paint bottom-left 16x16 red (Pillow coords: y=48..64)
        for y in range(48, 64):
            for x in range(16):
                img.putpixel((x, y), (255, 0, 0, 255))

        sprite = SpriteRect(name="BL", x=0, y=0, width=16, height=16)
        result = _slice_sprite(img, sprite)
        assert result.size == (16, 16)
        # All pixels should be red
        assert result.getpixel((0, 0)) == (255, 0, 0, 255)

    def test_crop_top_right(self) -> None:
        """Sprite at Unity top-right: x=48, y=48 (Unity), 16x16."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
        # Paint top-right 16x16 green (Pillow coords: y=0..16, x=48..64)
        for y in range(16):
            for x in range(48, 64):
                img.putpixel((x, y), (0, 255, 0, 255))

        sprite = SpriteRect(name="TR", x=48, y=48, width=16, height=16)
        result = _slice_sprite(img, sprite)
        assert result.size == (16, 16)
        assert result.getpixel((0, 0)) == (0, 255, 0, 255)

    def test_clamps_to_bounds(self) -> None:
        """Sprite extending past image edge gets clamped."""
        img = Image.new("RGBA", (32, 32), (128, 128, 128, 255))
        sprite = SpriteRect(name="OOB", x=20, y=0, width=100, height=100)
        result = _slice_sprite(img, sprite)
        # Should be clamped to available area
        assert result.size[0] <= 32
        assert result.size[1] <= 32


# ---------------------------------------------------------------------------
# extract_sprites (integration)
# ---------------------------------------------------------------------------

# Minimal GuidIndex stub
@dataclass
class _FakeGuidEntry:
    guid: str
    asset_path: Path
    relative_path: Path
    kind: str
    is_directory: bool = False


@dataclass
class _FakeGuidIndex:
    project_root: Path
    _textures: dict[str, _FakeGuidEntry] = field(default_factory=dict)

    def filter_by_kind(self, kind: str) -> dict[str, _FakeGuidEntry]:
        if kind == "texture":
            return self._textures
        return {}


@pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed")
class TestExtractSprites:
    def test_single_sprite_extracted(self, tmp_path: Path) -> None:
        """Single-sprite texture creates one output PNG."""
        # Create a real 4x4 PNG
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        tex_path = tmp_path / "Assets" / "icon.png"
        tex_path.parent.mkdir(parents=True)
        img.save(tex_path)

        # Write .meta
        meta_path = tmp_path / "Assets" / "icon.png.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: abcdef12345678900987654321fedcba\n"
            "TextureImporter:\n"
            "  spriteMode: 1\n"
        )

        guid_index = _FakeGuidIndex(
            project_root=tmp_path,
            _textures={
                "abcdef12345678900987654321fedcba": _FakeGuidEntry(
                    guid="abcdef12345678900987654321fedcba",
                    asset_path=tex_path,
                    relative_path=Path("Assets/icon.png"),
                    kind="texture",
                ),
            },
        )

        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = extract_sprites(guid_index, out_dir)

        assert result.total_spritesheets == 1
        assert result.total_sprites_extracted == 1
        assert (out_dir / "sprites" / "icon.png").exists()
        # Single-sprite: GUID maps directly
        assert "abcdef12345678900987654321fedcba" in result.sprite_guid_to_file

    def test_multi_sprite_extracted(self, tmp_path: Path) -> None:
        """Multi-sprite spritesheet creates one PNG per sprite."""
        img = Image.new("RGBA", (64, 128), (0, 0, 255, 255))
        tex_path = tmp_path / "Assets" / "icons.png"
        tex_path.parent.mkdir(parents=True)
        img.save(tex_path)

        meta_path = tmp_path / "Assets" / "icons.png.meta"
        meta_path.write_text(MULTI_SPRITE_META)

        guid_index = _FakeGuidIndex(
            project_root=tmp_path,
            _textures={
                "1234567890abcdef1234567890abcdef": _FakeGuidEntry(
                    guid="1234567890abcdef1234567890abcdef",
                    asset_path=tex_path,
                    relative_path=Path("Assets/icons.png"),
                    kind="texture",
                ),
            },
        )

        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = extract_sprites(guid_index, out_dir)

        assert result.total_spritesheets == 1
        assert result.total_sprites_extracted == 2
        assert (out_dir / "sprites" / "Icon_Sword.png").exists()
        assert (out_dir / "sprites" / "Icon_Shield.png").exists()
        # Multi-sprite: compound keys
        assert "1234567890abcdef1234567890abcdef:Icon_Sword" in result.sprite_guid_to_file

    def test_no_textures(self, tmp_path: Path) -> None:
        guid_index = _FakeGuidIndex(project_root=tmp_path)
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = extract_sprites(guid_index, out_dir)
        assert result.total_sprites_extracted == 0
        assert not (out_dir / "sprites").exists()

    def test_missing_texture_file_warns(self, tmp_path: Path) -> None:
        """If texture file doesn't exist, a warning is produced."""
        tex_path = tmp_path / "Assets" / "gone.png"
        tex_path.parent.mkdir(parents=True)
        # Don't create the texture file, but create the .meta
        meta_path = tmp_path / "Assets" / "gone.png.meta"
        meta_path.write_text(
            "fileFormatVersion: 2\n"
            "guid: 00001111222233334444555566667777\n"
            "TextureImporter:\n"
            "  spriteMode: 1\n"
        )

        guid_index = _FakeGuidIndex(
            project_root=tmp_path,
            _textures={
                "00001111222233334444555566667777": _FakeGuidEntry(
                    guid="00001111222233334444555566667777",
                    asset_path=tex_path,
                    relative_path=Path("Assets/gone.png"),
                    kind="texture",
                ),
            },
        )

        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = extract_sprites(guid_index, out_dir)
        assert result.total_sprites_extracted == 0
        assert any("missing" in w.lower() for w in result.warnings)

    def test_non_sprite_texture_skipped(self, tmp_path: Path) -> None:
        """Textures with spriteMode 0 are not extracted."""
        tex_path = tmp_path / "Assets" / "ground.png"
        tex_path.parent.mkdir(parents=True)
        if HAS_PILLOW:
            Image.new("RGBA", (4, 4)).save(tex_path)

        meta_path = tmp_path / "Assets" / "ground.png.meta"
        meta_path.write_text(NO_SPRITE_META)

        guid_index = _FakeGuidIndex(
            project_root=tmp_path,
            _textures={
                "eeee5555ffff6666aaaa7777bbbb8888": _FakeGuidEntry(
                    guid="eeee5555ffff6666aaaa7777bbbb8888",
                    asset_path=tex_path,
                    relative_path=Path("Assets/ground.png"),
                    kind="texture",
                ),
            },
        )

        out_dir = tmp_path / "output"
        out_dir.mkdir()
        result = extract_sprites(guid_index, out_dir)
        assert result.total_sprites_extracted == 0
