"""Tests for modules/roblox_uploader.py.

Covers API key validation, upload skip logic, file size validation,
and mocked HTTP upload scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from modules.roblox_uploader import (
    UploadResult,
    _validate_api_key,
    _patch_rbxl_asset_ids,
    upload_to_roblox,
    ASSET_MAX_BYTES,
    PLACE_MAX_BYTES,
)


# ---------------------------------------------------------------------------
# _validate_api_key
# ---------------------------------------------------------------------------

class TestValidateApiKey:
    def test_empty_string(self) -> None:
        assert _validate_api_key("") is False

    def test_whitespace_only(self) -> None:
        assert _validate_api_key("   ") is False

    def test_placeholder_values(self) -> None:
        assert _validate_api_key("PLACEHOLDER") is False
        assert _validate_api_key("your-api-key-here") is False
        assert _validate_api_key("ROBLOX_API_KEY") is False

    def test_valid_key(self) -> None:
        assert _validate_api_key("rbx-abc123def456") is True

    def test_realistic_key(self) -> None:
        assert _validate_api_key("OC_abc123XYZ789-longkey") is True


# ---------------------------------------------------------------------------
# upload_to_roblox — skip scenarios (no HTTP)
# ---------------------------------------------------------------------------

class TestUploadSkipScenarios:
    def test_no_api_key(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        result = upload_to_roblox(rbxl, None, "", None, None)
        assert result.skipped is True
        assert result.success is False
        assert len(result.warnings) == 1
        assert "no valid api key" in result.warnings[0].lower()

    def test_placeholder_api_key(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        result = upload_to_roblox(rbxl, None, "PLACEHOLDER", None, None)
        assert result.skipped is True

    def test_missing_rbxl_file(self, tmp_path: Path) -> None:
        rbxl = tmp_path / "nonexistent.rbxl"
        result = upload_to_roblox(rbxl, None, "real-api-key-123", 123, 456)
        assert result.success is False
        assert len(result.errors) == 1
        assert "not found" in result.errors[0].lower()

    def test_no_universe_and_place_id(self, tmp_path: Path) -> None:
        """Valid key but no universe/place IDs → place upload skipped with warning."""
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        result = upload_to_roblox(rbxl, None, "real-api-key-123", None, None)
        assert result.skipped is False  # not fully skipped — key was valid
        assert result.success is False
        assert any("universe-id" in w.lower() or "place-id" in w.lower()
                    for w in result.warnings)


# ---------------------------------------------------------------------------
# upload_to_roblox — mocked HTTP
# ---------------------------------------------------------------------------

class TestUploadWithMockedHTTP:
    @patch("modules.roblox_uploader._upload_place")
    def test_successful_place_upload(self, mock_upload: MagicMock, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        mock_upload.return_value = {"versionNumber": 42}

        result = upload_to_roblox(rbxl, None, "real-key", 111, 222)
        assert result.success is True
        assert result.place_id == 222
        assert result.universe_id == 111
        assert result.version_number == 42
        mock_upload.assert_called_once_with(rbxl, "real-key", 111, 222)

    @patch("modules.roblox_uploader._upload_place")
    def test_place_upload_failure(self, mock_upload: MagicMock, tmp_path: Path) -> None:
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        mock_upload.side_effect = Exception("403 Forbidden")

        result = upload_to_roblox(rbxl, None, "real-key", 111, 222)
        assert result.success is False
        assert len(result.errors) == 1
        assert "403 Forbidden" in result.errors[0]

    @patch("modules.roblox_uploader._upload_image_asset")
    @patch("modules.roblox_uploader._upload_place")
    def test_texture_upload(
        self, mock_place: MagicMock, mock_img: MagicMock, tmp_path: Path
    ) -> None:
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        mock_place.return_value = {"versionNumber": 1}

        tex_dir = tmp_path / "textures"
        tex_dir.mkdir()
        (tex_dir / "albedo.png").write_bytes(b"\x89PNG" + b"\x00" * 10)
        (tex_dir / "normal.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 10)
        (tex_dir / "readme.txt").write_text("not an image")

        mock_img.return_value = {"assetId": 999}

        result = upload_to_roblox(rbxl, tex_dir, "real-key", 111, 222)
        assert result.success is True
        # Only .png and .jpg should be uploaded (not .txt)
        assert mock_img.call_count == 2
        assert len(result.asset_ids) == 2

    @patch("modules.roblox_uploader._upload_image_asset")
    @patch("modules.roblox_uploader._upload_place")
    def test_texture_upload_failure_doesnt_crash(
        self, mock_place: MagicMock, mock_img: MagicMock, tmp_path: Path
    ) -> None:
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text("<roblox/>")
        mock_place.return_value = {"versionNumber": 1}

        tex_dir = tmp_path / "textures"
        tex_dir.mkdir()
        (tex_dir / "bad.png").write_bytes(b"\x89PNG" + b"\x00" * 10)
        mock_img.side_effect = Exception("Upload failed")

        result = upload_to_roblox(rbxl, tex_dir, "real-key", 111, 222)
        assert result.success is True  # place upload succeeded
        assert len(result.warnings) >= 1
        assert "bad.png" in result.warnings[0]


# ---------------------------------------------------------------------------
# File size limits
# ---------------------------------------------------------------------------

class TestPatchRbxlAssetIds:
    """Tests for XML-aware _patch_rbxl_asset_ids."""

    def test_patches_content_element(self, tmp_path: Path) -> None:
        """Asset references in <Content> elements should be patched."""
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<roblox>\n"
            '  <Item class="Decal">\n'
            "    <Properties>\n"
            '      <Content name="Texture">rbxassetid://hero.png</Content>\n'
            "    </Properties>\n"
            "  </Item>\n"
            "</roblox>\n"
        )
        result = _patch_rbxl_asset_ids(rbxl, {"hero.png": 12345})
        assert result is True
        content = rbxl.read_text()
        assert "rbxassetid://12345" in content
        assert "rbxassetid://hero.png" not in content

    def test_does_not_patch_protected_string(self, tmp_path: Path) -> None:
        """Luau source in <ProtectedString> must NOT be patched."""
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<roblox>\n"
            '  <Item class="Script">\n'
            "    <Properties>\n"
            '      <ProtectedString name="Source">\n'
            'local url = "rbxassetid://hero.png"\n'
            "      </ProtectedString>\n"
            "    </Properties>\n"
            "  </Item>\n"
            '  <Item class="Decal">\n'
            "    <Properties>\n"
            '      <Content name="Texture">rbxassetid://hero.png</Content>\n'
            "    </Properties>\n"
            "  </Item>\n"
            "</roblox>\n"
        )
        _patch_rbxl_asset_ids(rbxl, {"hero.png": 12345})
        content = rbxl.read_text()
        # The Content element should be patched
        assert "rbxassetid://12345" in content
        # The ProtectedString should still have the original placeholder
        assert "hero.png" in content

    def test_patches_url_element(self, tmp_path: Path) -> None:
        """Asset references in <url> elements should be patched."""
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<roblox>\n"
            '  <Item class="Sound">\n'
            "    <Properties>\n"
            '      <url name="SoundId">rbxassetid://bgm</url>\n'
            "    </Properties>\n"
            "  </Item>\n"
            "</roblox>\n"
        )
        result = _patch_rbxl_asset_ids(rbxl, {"bgm.ogg": 99999})
        assert result is True
        content = rbxl.read_text()
        assert "rbxassetid://99999" in content

    def test_no_changes_returns_false(self, tmp_path: Path) -> None:
        """When no placeholders match, should return False."""
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<roblox>\n"
            '  <Item class="Decal">\n'
            "    <Properties>\n"
            '      <Content name="Texture">rbxassetid://other.png</Content>\n'
            "    </Properties>\n"
            "  </Item>\n"
            "</roblox>\n"
        )
        result = _patch_rbxl_asset_ids(rbxl, {"hero.png": 12345})
        assert result is False

    def test_malformed_xml_falls_back_to_text(self, tmp_path: Path) -> None:
        """Malformed XML should fall back to text-based replacement."""
        rbxl = tmp_path / "test.rbxl"
        rbxl.write_text(
            "NOT VALID XML\nrbxassetid://hero.png\n<unclosed"
        )
        result = _patch_rbxl_asset_ids(rbxl, {"hero.png": 12345})
        assert result is True
        content = rbxl.read_text()
        assert "rbxassetid://12345" in content


class TestFileSizeLimits:
    def test_place_max_bytes_value(self) -> None:
        assert PLACE_MAX_BYTES == 100 * 1024 * 1024

    def test_asset_max_bytes_value(self) -> None:
        assert ASSET_MAX_BYTES == 20 * 1024 * 1024
