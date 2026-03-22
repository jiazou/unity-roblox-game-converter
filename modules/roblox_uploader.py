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
    meshes_uploaded: int = 0
    sprites_uploaded: int = 0
    audio_uploaded: int = 0
    rbxl_patched: bool = False  # True when .rbxl was rewritten with rbxassetid:// URLs
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False  # True when upload was not attempted (no API key)
    error_type: str | None = None  # Structured error classification
    suggestion: str | None = None  # Actionable suggestion for the caller


def resolve_roblox_username(username: str) -> int | None:
    """Resolve a Roblox username to numeric user ID. Returns None on failure."""
    import urllib.request
    import urllib.error

    url = "https://users.roblox.com/v1/usernames/users"
    payload = json.dumps({"usernames": [username]}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        users = data.get("data", [])
        if users:
            return users[0].get("id")
    except Exception:  # noqa: BLE001
        logger.warning("Failed to resolve Roblox username %r", username)

    return None


def _validate_api_key(api_key: str) -> bool:
    """Check that the API key is present and not a placeholder."""
    if not api_key:
        return False
    placeholders = {"", "PLACEHOLDER", "your-api-key-here", "ROBLOX_API_KEY"}
    return api_key.strip() not in placeholders


def _describe_upload_error(exc: Exception) -> str:
    """Return a human-readable message that preserves HTTP status details."""
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        hint = {
            401: "Invalid or expired API key",
            403: "API key lacks required permissions for this resource",
            429: "Rate limited — wait and retry",
            400: "Bad request (check asset format/size)",
            404: "Resource not found (check universe/place IDs)",
            500: "Roblox server error",
        }.get(code, "")
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        parts = [f"HTTP {code}"]
        if hint:
            parts.append(hint)
        if body:
            parts.append(body)
        return " — ".join(parts)

    if isinstance(exc, urllib.error.URLError):
        return f"Network error: {exc.reason}"

    return str(exc)


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


def _poll_operation(api_key: str, operation_id: str, max_wait: float = 30.0) -> dict[str, Any]:
    """Poll a Roblox async operation until done, returning the response payload."""
    import urllib.request

    url = f"https://apis.roblox.com/assets/v1/operations/{operation_id}"
    deadline = time.time() + max_wait
    interval = 1.0

    while time.time() < deadline:
        time.sleep(interval)
        req = urllib.request.Request(url, headers={"x-api-key": api_key})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("done"):
            return data.get("response", data)
        interval = min(interval * 1.5, 5.0)

    raise TimeoutError(f"Operation {operation_id} did not complete within {max_wait}s")


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


_CONTENT_TYPE_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".fbx": "application/octet-stream",
    ".obj": "model/obj",
}


def _upload_asset(
    file_path: Path,
    api_key: str,
    asset_type: str,
    display_name: str,
    description: str = "Uploaded by unity-roblox-game-converter",
    creator_id: int | None = None,
    creator_type: str = "User",
) -> dict[str, Any]:
    """
    Upload a file to Roblox via Open Cloud Assets API (POST /v1/assets).

    Works for images (Decal), audio (Audio), and meshes (Model).
    """
    import urllib.request

    file_bytes = file_path.read_bytes()
    if len(file_bytes) > ASSET_MAX_BYTES:
        raise ValueError(
            f"File too large for Roblox Open Cloud: "
            f"{len(file_bytes) / 1_048_576:.1f} MB (limit: {ASSET_MAX_BYTES // 1_048_576} MB)"
        )

    if creator_type == "User" and creator_id:
        creator = {"userId": str(creator_id)}
    elif creator_type == "Group" and creator_id:
        creator = {"groupId": str(creator_id)}
    else:
        creator = {}

    boundary = f"----UnityRobloxConverter{int(time.time() * 1000)}"
    request_body = json.dumps({
        "assetType": asset_type,
        "displayName": display_name,
        "description": description,
        "creationContext": {"creator": creator, "expectedPrice": 0},
    })

    content_type = _CONTENT_TYPE_MAP.get(file_path.suffix.lower(), "application/octet-stream")
    body_prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="request"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{request_body}\r\n"
    ).encode("utf-8")
    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileContent"; filename="{file_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    file_footer = f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "https://apis.roblox.com/assets/v1/assets",
        data=body_prefix + file_header + file_bytes + file_footer,
        method="POST",
        headers={
            "x-api-key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    resp = urllib.request.urlopen(req, timeout=120)
    _check_rate_limit_headers(resp)
    data = json.loads(resp.read().decode("utf-8"))

    op_id = data.get("operationId")
    if op_id and not data.get("done", True):
        data = _poll_operation(api_key, op_id)

    return data


def _build_mesh_material_map(unity_project_path: Path | None) -> dict[str, str]:
    """Build a mapping of mesh filename stem → material texture filename.

    Parses Unity YAML (.prefab/.unity) by splitting on document markers
    (``---``) and grouping components that share the same ``m_GameObject``
    fileID.  For each GameObject that has both a MeshFilter and a
    MeshRenderer, resolves the mesh GUID → mesh filename and the first
    material GUID → material name → ``<MatName>_color.png``.

    Returns e.g. ``{"road01": "Plaster_color.png"}``.
    """
    import re as _re

    if not unity_project_path or not unity_project_path.is_dir():
        return {}

    assets_dir = unity_project_path / "Assets"
    if not assets_dir.is_dir():
        return {}

    # ── Step 1: GUID → asset path from .meta files ─────────────────
    guid_to_path: dict[str, Path] = {}
    for meta in assets_dir.rglob("*.meta"):
        try:
            text = meta.read_text(encoding="utf-8", errors="replace")
            m = _re.search(r"guid:\s*([0-9a-f]{32})", text)
            if m:
                guid_to_path[m.group(1)] = meta.with_suffix("")
        except OSError:
            continue

    # ── Step 2: material GUID → texture filename ───────────────────
    # A .mat file references its _MainTex via a GUID.  We map the
    # material's own GUID → "<MaterialName>_color.png" (matching the
    # texture filenames produced by the material_mapper).
    mat_guid_to_texture: dict[str, str] = {}
    for guid, path in guid_to_path.items():
        if path.suffix.lower() != ".mat":
            continue
        mat_guid_to_texture[guid] = f"{path.stem}_color.png"

    # ── Step 3: parse prefabs/scenes for mesh↔material pairs ───────
    # Unity YAML uses multi-document format.  Each document starts with
    # ``--- !u!<classID> &<fileID>``.  We split on these markers, then
    # group components by their ``m_GameObject: {fileID: ...}`` value.
    _DOC_SEP = _re.compile(r"^--- !u!\d+ &(\d+)\s*$", _re.MULTILINE)
    _GUID_RE = _re.compile(r"guid:\s*([0-9a-f]{32})")

    mesh_to_texture: dict[str, str] = {}

    for ext in ("*.prefab", "*.unity"):
        for scene_file in assets_dir.rglob(ext):
            try:
                text = scene_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Split into documents.  Each doc is (fileID, body).
            parts = _DOC_SEP.split(text)
            # parts = [preamble, fileID1, body1, fileID2, body2, ...]
            docs: dict[str, str] = {}
            for i in range(1, len(parts) - 1, 2):
                docs[parts[i]] = parts[i + 1]

            # For each doc, extract the component type and m_GameObject fileID.
            go_mesh_guids: dict[str, str] = {}  # gameObject_fileID → mesh_guid
            go_mat_guids: dict[str, list[str]] = {}  # gameObject_fileID → [mat_guids]

            for _file_id, body in docs.items():
                # Determine component type from first non-blank line.
                first_line = ""
                for line in body.strip().splitlines():
                    stripped = line.strip()
                    if stripped:
                        first_line = stripped
                        break

                # Extract m_GameObject fileID.
                go_match = _re.search(
                    r"m_GameObject:\s*\{fileID:\s*(\d+)", body,
                )
                if not go_match:
                    continue
                go_fid = go_match.group(1)

                if first_line.startswith("MeshFilter:"):
                    mesh_m = _re.search(
                        r"m_Mesh:\s*\{[^}]*guid:\s*([0-9a-f]{32})", body,
                    )
                    if mesh_m:
                        go_mesh_guids[go_fid] = mesh_m.group(1)

                elif first_line.startswith("MeshRenderer:") or first_line.startswith("SkinnedMeshRenderer:"):
                    mat_section = _re.search(r"m_Materials:(.*?)(?:\n\S|\Z)", body, _re.DOTALL)
                    if mat_section:
                        mat_guids = _GUID_RE.findall(mat_section.group(1))
                        if mat_guids:
                            go_mat_guids[go_fid] = mat_guids

            # Pair mesh GUIDs with material GUIDs via shared GameObject.
            for go_fid, mesh_guid in go_mesh_guids.items():
                mat_guids = go_mat_guids.get(go_fid)
                if not mat_guids:
                    continue
                mesh_path = guid_to_path.get(mesh_guid)
                if not mesh_path:
                    continue
                # Use first material.
                tex_fn = mat_guid_to_texture.get(mat_guids[0])
                if tex_fn:
                    mesh_to_texture[mesh_path.stem.lower()] = tex_fn

    return mesh_to_texture


def _upload_mesh_asset(
    mesh_path: Path,
    api_key: str,
    display_name: str,
    description: str = "Uploaded by unity-roblox-game-converter",
    creator_id: int | None = None,
    creator_type: str = "User",
) -> dict[str, Any]:
    """Upload a mesh file as a Roblox Model asset via Open Cloud Assets API.

    Roblox accepts .fbx and .obj files for ``assetType: "Model"``.
    Uses the same multipart POST as image/audio uploads.
    """
    import urllib.request

    url = "https://apis.roblox.com/assets/v1/assets"
    boundary = f"----UnityRobloxConverter{int(time.time() * 1000)}"

    request_body = json.dumps({
        "assetType": "Model",
        "displayName": display_name[:50],
        "description": description,
        "creationContext": {
            "creator": {
                "userId": str(creator_id),
            } if creator_type == "User" and creator_id else (
                {
                    "groupId": str(creator_id),
                } if creator_type == "Group" and creator_id else {}
            ),
            "expectedPrice": 0,
        },
    })

    mesh_bytes = mesh_path.read_bytes()
    if len(mesh_bytes) > ASSET_MAX_BYTES:
        raise ValueError(
            f"Mesh file too large: {len(mesh_bytes) / 1_048_576:.1f} MB "
            f"(limit: {ASSET_MAX_BYTES // 1_048_576} MB)"
        )

    # Roblox requires specific content types for 3D files.
    _mesh_content_types = {
        ".fbx": "model/fbx",
        ".obj": "model/obj",
        ".gltf": "model/gltf+json",
        ".glb": "model/gltf-binary",
    }
    content_type = _mesh_content_types.get(
        mesh_path.suffix.lower(), "application/octet-stream",
    )

    body_prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="request"\r\n'
        f"Content-Type: application/json\r\n\r\n"
        f"{request_body}\r\n"
    ).encode("utf-8")

    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileContent"; filename="{mesh_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    file_footer = f"\r\n--{boundary}--\r\n".encode("utf-8")

    full_body = body_prefix + file_header + mesh_bytes + file_footer

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
    data = json.loads(resp.read().decode("utf-8"))

    op_id = data.get("operationId")
    if op_id and not data.get("done", True):
        data = _poll_operation(api_key, op_id)

    return data


def _patch_rbxl_asset_ids(
    rbxl_path: Path,
    asset_ids: dict[str, int],
    mesh_texture_map: dict[str, str] | None = None,
    unity_project_path: Path | None = None,
) -> bool:
    """
    Rewrite a .rbxl XML file, replacing local placeholder references with
    rbxassetid:// URLs.

    Handles three kinds of references:
    1. ``rbxassetid://filename`` or ``rbxassetid://stem`` placeholders
    2. ``-- TODO: upload ...filename`` comments in SoundId properties
    3. Local filesystem paths in Content elements (MeshId, SoundId, etc.)
       matched by filename or stem against uploaded asset names

    Also injects SurfaceAppearance children on MeshPart items when a
    matching ``<stem>_color.png`` texture was uploaded but no
    SurfaceAppearance exists yet.

    Returns True if any changes were made.
    """
    import re
    import xml.etree.ElementTree as ET

    content = rbxl_path.read_text(encoding="utf-8")

    try:
        tree = ET.parse(rbxl_path)  # noqa: S314 — trusted local file
    except ET.ParseError:
        return _patch_rbxl_asset_ids_text(content, rbxl_path, asset_ids)

    root = tree.getroot()
    changed = False

    # ── Build lookup indices from uploaded asset names ───────────────
    # Map stem (no extension) → rbxassetid URL for fast matching.
    stem_to_url: dict[str, str] = {}
    name_to_url: dict[str, str] = {}
    for local_name, asset_id in asset_ids.items():
        url = f"rbxassetid://{asset_id}"
        name_to_url[local_name.lower()] = url
        stem_to_url[Path(local_name).stem.lower()] = url

    # Separate texture assets (images) from other assets (audio).
    texture_stem_to_url: dict[str, str] = {}
    for local_name, asset_id in asset_ids.items():
        if Path(local_name).suffix.lower() in {".png", ".jpg", ".jpeg"}:
            texture_stem_to_url[Path(local_name).stem.lower()] = f"rbxassetid://{asset_id}"

    # Build Unity mesh→material map if project path is available.
    _unity_mesh_material_map = _build_mesh_material_map(unity_project_path) if unity_project_path else {}

    ASSET_TAGS = {"Content", "url"}

    # ── Pass 1: patch existing Content/url elements ─────────────────
    for elem in root.iter():
        if elem.tag not in ASSET_TAGS:
            continue
        if elem.text is None:
            continue

        text = elem.text
        original_text = text

        # (a) Replace rbxassetid:// placeholders.
        for local_name, asset_id in asset_ids.items():
            rbx_url = f"rbxassetid://{asset_id}"
            stem = Path(local_name).stem
            text = text.replace(f"rbxassetid://{local_name}", rbx_url)
            text = text.replace(f"rbxassetid://{stem}", rbx_url)

        # (b) Replace "-- TODO: upload ..." patterns.
        for local_name, asset_id in asset_ids.items():
            pattern = re.compile(
                r"-- TODO: upload [^\n]*?" + re.escape(local_name),
                re.IGNORECASE,
            )
            text = pattern.sub(f"rbxassetid://{asset_id}", text)

        # (c) Replace local filesystem paths by matching the filename.
        #     e.g. "/Users/.../MenuTheme.ogg" → rbxassetid://12345
        if text.startswith("/") or text.startswith("\\"):
            fname = Path(text).name.lower()
            fstem = Path(text).stem.lower()
            if fname in name_to_url:
                text = name_to_url[fname]
            elif fstem in stem_to_url:
                text = stem_to_url[fstem]

        # (d) Replace bare filenames that match uploaded assets.
        #     e.g. "BrickWall_color.png" → rbxassetid://12345
        if "rbxassetid" not in text:
            text_lower = text.strip().lower()
            if text_lower in name_to_url:
                text = name_to_url[text_lower]
            elif text_lower in stem_to_url:
                text = stem_to_url[text_lower]

        if text != original_text:
            elem.text = text
            changed = True

    # ── Pass 2: inject SurfaceAppearance on MeshParts ───────────────
    # Uses mesh_texture_map (mesh_id → texture filename) built during assembly,
    # plus a fallback name-matching strategy.
    for item in list(root.iter("Item")):
        if item.get("class") != "MeshPart":
            continue

        # Skip if SurfaceAppearance already exists.
        has_sa = any(
            child.get("class") == "SurfaceAppearance"
            for child in item.findall("Item")
        )
        if has_sa:
            continue

        props = item.find("Properties")
        if props is None:
            continue

        part_name = ""
        mesh_id = ""
        for p in props:
            if p.get("name") == "Name":
                part_name = p.text or ""
            elif p.get("name") == "MeshId":
                mesh_id = p.text or ""

        matched_url = None

        # Clean part name: strip Unity instance suffixes like " (2)", " (13)"
        import re as _re
        clean_name = _re.sub(r"\s*\(\d+\)$", "", part_name).strip().lower()

        # Strategy 1: mesh_texture_map from assembly (mesh_id → texture filename).
        if mesh_texture_map and mesh_id:
            tex_filename = mesh_texture_map.get(mesh_id)
            if tex_filename:
                tex_lower = tex_filename.lower()
                stem_lower = Path(tex_filename).stem.lower()
                if tex_lower in name_to_url:
                    matched_url = name_to_url[tex_lower]
                elif stem_lower in stem_to_url:
                    matched_url = stem_to_url[stem_lower]

        # Strategy 2: Unity project mesh→material mapping.
        # Try multiple name candidates since MeshId may be rbxassetid://
        # (not a filename) after patching.
        if not matched_url and _unity_mesh_material_map:
            # Try: clean part name, raw part name, mesh filename stem
            name_candidates = [clean_name]
            if mesh_id and not mesh_id.startswith("rbxassetid"):
                name_candidates.append(Path(mesh_id).stem.lower())

            for candidate in name_candidates:
                tex_fn = _unity_mesh_material_map.get(candidate)
                if tex_fn:
                    tex_lower = tex_fn.lower()
                    stem_lower = Path(tex_fn).stem.lower()
                    if tex_lower in name_to_url:
                        matched_url = name_to_url[tex_lower]
                    elif stem_lower in stem_to_url:
                        matched_url = stem_to_url[stem_lower]
                    if matched_url:
                        break

        # Strategy 3: name-based fallback.
        if not matched_url:
            candidates = [
                f"{clean_name}_color",
                f"{part_name.lower()}_color",
                clean_name,
            ]
            if mesh_id and not mesh_id.startswith("rbxassetid"):
                candidates.append(f"{Path(mesh_id).stem.lower()}_color")
            for candidate in candidates:
                if candidate and candidate in texture_stem_to_url:
                    matched_url = texture_stem_to_url[candidate]
                    break

        if matched_url:
            sa_item = ET.SubElement(item, "Item")
            sa_item.set("class", "SurfaceAppearance")
            sa_props = ET.SubElement(sa_item, "Properties")
            sa_name = ET.SubElement(sa_props, "string")
            sa_name.set("name", "Name")
            sa_name.text = "SurfaceAppearance"
            sa_cmap = ET.SubElement(sa_props, "Content")
            sa_cmap.set("name", "ColorMap")
            sa_cmap.text = matched_url
            changed = True

    if changed:
        tree.write(rbxl_path, encoding="unicode", xml_declaration=True)
    return changed


def _patch_rbxl_asset_ids_text(
    content: str,
    rbxl_path: Path,
    asset_ids: dict[str, int],
) -> bool:
    """Text-based fallback for _patch_rbxl_asset_ids when XML parsing fails."""
    import re

    original = content

    for local_name, asset_id in asset_ids.items():
        rbx_url = f"rbxassetid://{asset_id}"
        stem = Path(local_name).stem

        content = content.replace(f"rbxassetid://{local_name}", rbx_url)
        content = content.replace(f"rbxassetid://{stem}", rbx_url)

        pattern = re.compile(
            r"-- TODO: upload [^\n]*?" + re.escape(local_name),
            re.IGNORECASE,
        )
        content = pattern.sub(rbx_url, content)

    if content != original:
        rbxl_path.write_text(content, encoding="utf-8")
        return True
    return False


def _inject_mesh_loader(rbxl_path: Path, asset_ids: dict[str, int]) -> None:
    """Inject a loader Script into the .rbxl that replaces MeshParts at runtime.

    For each MeshPart whose MeshId is ``rbxassetid://<model_id>`` (a Model
    asset, not a mesh content ID), we:
      1. Add a ``ModelAssetId`` string attribute with the Model asset ID
      2. Clear the MeshId (so Roblox doesn't try to load it as mesh content)
      3. Inject a ServerScript that iterates all tagged MeshParts, calls
         ``InsertService:LoadAsset()``, and swaps in the real geometry.
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(rbxl_path)
    root = tree.getroot()

    # Build set of Model asset IDs (meshes uploaded via Open Cloud)
    mesh_asset_ids = set()
    for name, aid in asset_ids.items():
        if name.lower().endswith((".fbx", ".obj")):
            mesh_asset_ids.add(str(aid))

    if not mesh_asset_ids:
        return

    # Tag MeshParts and collect unique Model IDs that need loading
    model_ids_needed: set[str] = set()
    tagged = 0

    for item in root.iter("Item"):
        if item.get("class") != "MeshPart":
            continue
        props = item.find("Properties")
        if props is None:
            continue

        mesh_id_elem = None
        for p in props:
            if p.get("name") == "MeshId":
                mesh_id_elem = p
                break
        if mesh_id_elem is None or not mesh_id_elem.text:
            continue

        val = mesh_id_elem.text.strip()
        if not val.startswith("rbxassetid://"):
            continue

        aid = val.replace("rbxassetid://", "")
        if aid not in mesh_asset_ids:
            continue

        # Add ModelAssetId attribute
        model_ids_needed.add(aid)
        attr = ET.SubElement(props, "string")
        attr.set("name", "ModelAssetId")
        attr.text = aid

        # Clear MeshId so Roblox doesn't try to load it as mesh content
        mesh_id_elem.text = ""
        tagged += 1

    if not model_ids_needed:
        return

    # Generate the loader script source
    loader_source = '''\
-- MeshLoader.lua (auto-generated)
-- Loads uploaded FBX Model assets via InsertService and replaces
-- placeholder MeshParts with real mesh geometry.

local InsertService = game:GetService("InsertService")
local ServerStorage = game:GetService("ServerStorage")

-- Cache loaded models to avoid re-downloading
local meshCache = {}

local function loadMeshModel(assetId)
    if meshCache[assetId] then
        return meshCache[assetId]
    end
    local ok, model = pcall(function()
        return InsertService:LoadAsset(tonumber(assetId))
    end)
    if ok and model then
        meshCache[assetId] = model
        return model
    else
        warn("[MeshLoader] Failed to load asset " .. tostring(assetId))
        return nil
    end
end

local function replaceMeshPart(placeholder)
    local assetId = placeholder:GetAttribute("ModelAssetId")
    if not assetId then return end

    local model = loadMeshModel(assetId)
    if not model then return end

    -- Find the MeshPart inside the loaded Model
    local sourceMesh = nil
    for _, desc in ipairs(model:GetDescendants()) do
        if desc:IsA("MeshPart") then
            sourceMesh = desc
            break
        end
    end

    if not sourceMesh then
        warn("[MeshLoader] No MeshPart found in asset " .. tostring(assetId))
        return
    end

    -- Clone and configure
    local newMesh = sourceMesh:Clone()
    newMesh.Name = placeholder.Name
    newMesh.CFrame = placeholder.CFrame
    newMesh.Size = placeholder.Size
    newMesh.Anchored = placeholder.Anchored
    newMesh.Parent = placeholder.Parent

    -- Copy children (SurfaceAppearance, scripts, etc.)
    for _, child in ipairs(placeholder:GetChildren()) do
        child.Parent = newMesh
    end

    -- Copy custom attributes
    for name, value in pairs(placeholder:GetAttributes()) do
        if name ~= "ModelAssetId" then
            newMesh:SetAttribute(name, value)
        end
    end

    placeholder:Destroy()
end

-- Process all MeshParts in Workspace and ServerStorage
local function processContainer(container)
    for _, desc in ipairs(container:GetDescendants()) do
        if desc:IsA("MeshPart") and desc:GetAttribute("ModelAssetId") then
            task.spawn(replaceMeshPart, desc)
        end
    end
end

processContainer(game:GetService("Workspace"))
processContainer(ServerStorage)

print("[MeshLoader] Loaded " .. tostring(#meshCache) .. " unique mesh assets")
'''

    # Inject the loader script into ServerScriptService
    sss = None
    for item in root.findall("Item"):
        if item.get("class") == "ServerScriptService":
            sss = item
            break

    if sss is None:
        sss = ET.SubElement(root, "Item")
        sss.set("class", "ServerScriptService")
        sss_props = ET.SubElement(sss, "Properties")
        name_el = ET.SubElement(sss_props, "string")
        name_el.set("name", "Name")
        name_el.text = "ServerScriptService"

    script_item = ET.SubElement(sss, "Item")
    script_item.set("class", "Script")
    script_props = ET.SubElement(script_item, "Properties")
    sn = ET.SubElement(script_props, "string")
    sn.set("name", "Name")
    sn.text = "MeshLoader"
    ss = ET.SubElement(script_props, "ProtectedString")
    ss.set("name", "Source")
    ss.text = loader_source

    tree.write(str(rbxl_path), encoding="unicode", xml_declaration=True)
    logger.info("Injected MeshLoader script: %d MeshParts tagged, %d unique models",
                tagged, len(model_ids_needed))


def upload_to_roblox(
    rbxl_path: Path,
    textures_dir: Path | None,
    api_key: str,
    universe_id: int | None = None,
    place_id: int | None = None,
    sprites_dir: Path | None = None,
    audio_dir: Path | None = None,
    meshes_dir: Path | None = None,
    creator_id: int | None = None,
    creator_type: str = "User",
    mesh_texture_map: dict[str, str] | None = None,
    unity_project_path: Path | None = None,
) -> UploadResult:
    """
    Upload a converted .rbxl place file (and optionally textures, sprites,
    audio, meshes) to Roblox.

    Upload order:
      1. Meshes (3D model files)
      2. Textures (material images)
      3. Sprites (UI images)
      4. Audio files
      5. Patch the .rbxl with rbxassetid:// URLs from steps 1-4
      6. Upload the patched .rbxl place file

    A valid Roblox Open Cloud API key is **required**. If the key is missing
    or invalid, the upload is skipped with a descriptive message.

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

    # ── Upload meshes ─────────────────────────────────────────────────
    if meshes_dir and meshes_dir.is_dir():
        mesh_exts = {".fbx", ".obj", ".dae"}
        for mesh_path in sorted(meshes_dir.iterdir()):
            if mesh_path.suffix.lower() not in mesh_exts:
                continue
            try:
                resp = _upload_asset(
                    mesh_path, api_key, asset_type="Model",
                    display_name=mesh_path.stem,
                    creator_id=creator_id,
                    creator_type=creator_type,
                )
                asset_id = resp.get("assetId") or resp.get("id")
                if asset_id:
                    result.asset_ids[mesh_path.name] = int(asset_id)
                    result.meshes_uploaded += 1
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(
                    f"Mesh upload failed ({mesh_path.name}): "
                    f"{_describe_upload_error(exc)}"
                )

    # ── Upload textures ────────────────────────────────────────────────
    if textures_dir and textures_dir.is_dir():
        image_exts = {".png", ".jpg", ".jpeg"}
        for img_path in sorted(textures_dir.iterdir()):
            if img_path.suffix.lower() not in image_exts:
                continue
            try:
                resp = _upload_asset(
                    img_path, api_key, asset_type="Decal",
                    display_name=img_path.stem,
                    creator_id=creator_id,
                    creator_type=creator_type,
                )
                asset_id = resp.get("assetId") or resp.get("id")
                if asset_id:
                    result.asset_ids[img_path.name] = int(asset_id)
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(
                    f"Texture upload failed ({img_path.name}): "
                    f"{_describe_upload_error(exc)}"
                )

    # ── Upload sprites ─────────────────────────────────────────────────
    if sprites_dir and sprites_dir.is_dir():
        image_exts = {".png", ".jpg", ".jpeg"}
        for img_path in sorted(sprites_dir.iterdir()):
            if img_path.suffix.lower() not in image_exts:
                continue
            try:
                resp = _upload_asset(
                    img_path, api_key, asset_type="Decal",
                    display_name=img_path.stem,
                    creator_id=creator_id,
                    creator_type=creator_type,
                )
                asset_id = resp.get("assetId") or resp.get("id")
                if asset_id:
                    result.asset_ids[img_path.name] = int(asset_id)
                    result.sprites_uploaded += 1
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(
                    f"Sprite upload failed ({img_path.name}): "
                    f"{_describe_upload_error(exc)}"
                )

    # ── Upload audio ───────────────────────────────────────────────────
    if audio_dir and audio_dir.is_dir():
        audio_exts = {".ogg", ".mp3", ".wav"}
        for audio_path in sorted(audio_dir.iterdir()):
            if audio_path.suffix.lower() not in audio_exts:
                continue
            try:
                resp = _upload_asset(
                    audio_path, api_key, asset_type="Audio",
                    display_name=audio_path.stem,
                    creator_id=creator_id,
                    creator_type=creator_type,
                )
                asset_id = resp.get("assetId") or resp.get("id")
                if asset_id:
                    result.asset_ids[audio_path.name] = int(asset_id)
                    result.audio_uploaded += 1
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(
                    f"Audio upload failed ({audio_path.name}): "
                    f"{_describe_upload_error(exc)}"
                )

    # ── Upload meshes ───────────────────────────────────────────────────
    if meshes_dir and meshes_dir.is_dir():
        mesh_exts = {".fbx", ".obj"}
        for mesh_path in sorted(meshes_dir.iterdir()):
            if mesh_path.suffix.lower() not in mesh_exts:
                continue
            if mesh_path.stat().st_size < 200:
                continue  # skip stub/empty files
            try:
                resp = _upload_mesh_asset(
                    mesh_path, api_key,
                    display_name=mesh_path.stem,
                    creator_id=creator_id,
                    creator_type=creator_type,
                )
                asset_id = resp.get("assetId") or resp.get("id")
                if asset_id:
                    # Key by full path so the patcher can match MeshId references
                    result.asset_ids[str(mesh_path)] = int(asset_id)
                    # Also key by filename for fallback matching
                    result.asset_ids[mesh_path.name] = int(asset_id)
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(
                    f"Mesh upload failed ({mesh_path.name}): "
                    f"{_describe_upload_error(exc)}"
                )

    # ── Patch .rbxl with uploaded asset IDs ────────────────────────────
    if result.asset_ids:
        try:
            result.rbxl_patched = _patch_rbxl_asset_ids(
                rbxl_path, result.asset_ids, mesh_texture_map, unity_project_path,
            )
            if result.rbxl_patched:
                logger.info("Patched .rbxl with %d asset ID(s)", len(result.asset_ids))
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Failed to patch .rbxl with asset IDs: {exc}")

    # ── Convert XML to binary format (required by Roblox Open Cloud) ──
    upload_path = rbxl_path
    if rbxl_path.exists():
        try:
            raw = rbxl_path.read_bytes()
            if raw.lstrip().startswith(b"<?xml"):
                from modules.rbxl_binary_writer import xml_to_binary
                binary_path = rbxl_path.with_name(rbxl_path.stem + "_binary.rbxl")
                xml_to_binary(rbxl_path, binary_path)
                upload_path = binary_path
                logger.info("Converted XML .rbxl to binary format for upload")
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Binary conversion failed, uploading XML: {exc}")

    # ── Upload place file (after patching) ─────────────────────────────
    if universe_id and place_id:
        try:
            resp = _upload_place(upload_path, api_key, universe_id, place_id)
            result.place_id = place_id
            result.universe_id = universe_id
            result.version_number = resp.get("versionNumber")
            result.success = True
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Place upload failed: {_describe_upload_error(exc)}")
            # M9: classify HTTP 409 as place-not-published
            import urllib.error
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 409:
                result.error_type = "place_not_published"
                result.suggestion = (
                    "Open the place in Roblox Studio and publish an initial version first"
                )
    else:
        result.warnings.append(
            "Place upload skipped: --universe-id and --place-id are required "
            "to upload to an existing Roblox experience."
        )

    return result
