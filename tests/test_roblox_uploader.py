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

class TestFileSizeLimits:
    def test_place_max_bytes_value(self) -> None:
        assert PLACE_MAX_BYTES == 100 * 1024 * 1024

    def test_asset_max_bytes_value(self) -> None:
        assert ASSET_MAX_BYTES == 20 * 1024 * 1024
