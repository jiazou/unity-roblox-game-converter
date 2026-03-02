"""
roblox_uploader.py — Uploads converted assets to Roblox via the Open Cloud API.

Requires a Roblox Open Cloud API key with appropriate permissions.
Without a valid API key, upload is skipped and the user is directed to
open the .rbxl file manually in Roblox Studio.

No other module is imported here.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Roblox Open Cloud payload size limits (bytes)
# ---------------------------------------------------------------------------

ASSET_MAX_BYTES: int = 20 * 1024 * 1024      # 20 MB for assets (decals, meshes, audio)
PLACE_MAX_BYTES: int = 100 * 1024 * 1024     # 100 MB for place files


@dataclass
class UploadResult:
    """Outcome of a Roblox portal upload attempt."""
    success: bool = False
    place_id: int | None = None
    universe_id: int | None = None
    version_number: int | None = None
    asset_ids: dict[str, int] = field(default_factory=dict)  # local_name → rbx asset id
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False  # True when upload was not attempted (no API key)


def _validate_api_key(api_key: str) -> bool:
    """Check that the API key is present and not a placeholder."""
    if not api_key:
        return False
    placeholders = {"", "PLACEHOLDER", "your-api-key-here", "ROBLOX_API_KEY"}
    return api_key.strip() not in placeholders


def _check_rate_limit_headers(resp: Any) -> None:
    """
    Inspect Roblox rate-limit response headers and sleep proactively
    when approaching the limit.

    Roblox Open Cloud returns:
      x-ratelimit-remaining: number of requests left in the current window
      x-ratelimit-reset: seconds until the rate-limit window resets
    """
    remaining = resp.headers.get("x-ratelimit-remaining")
    reset = resp.headers.get("x-ratelimit-reset")

    if remaining is not None:
        try:
            remaining_int = int(remaining)
        except (ValueError, TypeError):
            return
        if remaining_int <= 1 and reset is not None:
            try:
                sleep_seconds = min(float(reset), 60.0)  # cap at 60s
            except (ValueError, TypeError):
                sleep_seconds = 5.0
            logger.info(
                "Rate limit nearly exhausted (remaining=%d), sleeping %.1fs",
                remaining_int, sleep_seconds,
            )
            time.sleep(sleep_seconds)


def _upload_place(
    rbxl_path: Path,
    api_key: str,
    universe_id: int,
    place_id: int,
) -> dict[str, Any]:
    """
    Upload a .rbxl file to an existing Roblox place via Open Cloud.

    Uses POST /v2/universes/{universeId}/places/{placeId}/versions
    """
    import urllib.request
    import urllib.error

    # Validate file size before upload
    file_size = rbxl_path.stat().st_size
    if file_size > PLACE_MAX_BYTES:
        raise ValueError(
            f"Place file too large for Roblox Open Cloud: "
            f"{file_size / 1_048_576:.1f} MB (limit: {PLACE_MAX_BYTES // 1_048_576} MB)"
        )

    url = (
        f"https://apis.roblox.com/universes/v1/"
        f"{universe_id}/places/{place_id}/versions"
        f"?versionType=Published"
    )

    rbxl_bytes = rbxl_path.read_bytes()

    req = urllib.request.Request(
        url,
        data=rbxl_bytes,
        method="POST",
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/octet-stream",
        },
    )

    resp = urllib.request.urlopen(req, timeout=120)
    _check_rate_limit_headers(resp)
    return json.loads(resp.read().decode("utf-8"))


def _upload_image_asset(
    image_path: Path,
    api_key: str,
    display_name: str,
    description: str = "Uploaded by unity-roblox-game-converter",
    creator_id: int | None = None,
    creator_type: str = "User",
) -> dict[str, Any]:
    """
    Upload a single image (texture) as a Roblox asset via Open Cloud Assets API.

    Uses POST /v1/assets with multipart form data.
    """
    import urllib.request
    import urllib.error

    url = "https://apis.roblox.com/assets/v1/assets"

    boundary = f"----UnityRobloxConverter{int(time.time() * 1000)}"

    request_body = json.dumps({
        "assetType": "Decal",
        "displayName": display_name,
        "description": description,
        "creationContext": {
            "creator": {
                "userId": str(creator_id),
            } if creator_type == "User" and creator_id else {},
            "expectedPrice": 0,
        },
    })

    image_bytes = image_path.read_bytes()

    # Validate file size before upload
    if len(image_bytes) > ASSET_MAX_BYTES:
        raise ValueError(
            f"Asset file too large for Roblox Open Cloud: "
            f"{len(image_bytes) / 1_048_576:.1f} MB (limit: {ASSET_MAX_BYTES // 1_048_576} MB)"
        )

    content_type = "image/png" if image_path.suffix.lower() == ".png" else "application/octet-stream"

    body_parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="request"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{request_body}\r\n",
    ]
    body_prefix = "".join(body_parts).encode("utf-8")

    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileContent"; filename="{image_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    file_footer = f"\r\n--{boundary}--\r\n".encode("utf-8")

    full_body = body_prefix + file_header + image_bytes + file_footer

    req = urllib.request.Request(
        url,
        data=full_body,
        method="POST",
        headers={
            "x-api-key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    resp = urllib.request.urlopen(req, timeout=120)
    _check_rate_limit_headers(resp)
    return json.loads(resp.read().decode("utf-8"))


def upload_to_roblox(
    rbxl_path: Path,
    textures_dir: Path | None,
    api_key: str,
    universe_id: int | None = None,
    place_id: int | None = None,
) -> UploadResult:
    """
    Upload a converted .rbxl place file (and optionally textures) to Roblox.

    A valid Roblox Open Cloud API key is **required**. If the key is missing
    or invalid, the upload is skipped with a descriptive message.

    Args:
        rbxl_path: Path to the .rbxl file to upload.
        textures_dir: Optional directory containing texture images to upload.
        api_key: Roblox Open Cloud API key (required).
        universe_id: Target Roblox universe (experience) ID.
        place_id: Target Roblox place ID within the universe.

    Returns:
        UploadResult describing what was uploaded (or why it was skipped).
    """
    result = UploadResult()

    # ── Gate: require a valid API key ──────────────────────────────────
    if not _validate_api_key(api_key):
        result.skipped = True
        result.warnings.append(
            "Roblox upload skipped: no valid API key provided. "
            "Set --roblox-api-key or ROBLOX_API_KEY env var. "
            "You can open the .rbxl file manually in Roblox Studio."
        )
        return result

    if not rbxl_path.exists():
        result.errors.append(f"rbxl file not found: {rbxl_path}")
        return result

    # ── Upload place file ──────────────────────────────────────────────
    if universe_id and place_id:
        try:
            resp = _upload_place(rbxl_path, api_key, universe_id, place_id)
            result.place_id = place_id
            result.universe_id = universe_id
            result.version_number = resp.get("versionNumber")
            result.success = True
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Place upload failed: {exc}")
    else:
        result.warnings.append(
            "Place upload skipped: --universe-id and --place-id are required "
            "to upload to an existing Roblox experience."
        )

    # ── Upload textures ────────────────────────────────────────────────
    if textures_dir and textures_dir.is_dir():
        image_exts = {".png", ".jpg", ".jpeg"}
        for img_path in sorted(textures_dir.iterdir()):
            if img_path.suffix.lower() not in image_exts:
                continue
            try:
                resp = _upload_image_asset(
                    img_path,
                    api_key,
                    display_name=img_path.stem,
                )
                asset_id = resp.get("assetId") or resp.get("id")
                if asset_id:
                    result.asset_ids[img_path.name] = int(asset_id)
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(f"Texture upload failed ({img_path.name}): {exc}")

    return result
