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


# ---------------------------------------------------------------------------
# Asset upload cache — persists asset IDs across runs to avoid re-uploading
# ---------------------------------------------------------------------------

def _load_asset_cache(cache_path: Path) -> dict[str, dict]:
    """Load cached asset IDs from a JSON file. Returns {name: {asset_id, type}}.

    Supports both stem-keyed (legacy: ``"Invincible"``) and filename-keyed
    (``"Invincible.ogg"``) formats. Both are checked during lookups.
    """
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read asset cache at %s, starting fresh", cache_path)
    return {}


def _is_cached(name: str, cache: dict[str, dict]) -> int | None:
    """Return cached asset_id for name (case-insensitive, matches stem or full name)."""
    name_lower = name.lower()
    stem_lower = Path(name).stem.lower()
    for key, entry in cache.items():
        k = key.lower()
        if k == name_lower or k == stem_lower or Path(key).stem.lower() == stem_lower:
            return entry["asset_id"]
    return None


def _save_asset_cache(cache_path: Path, cache: dict[str, dict]) -> None:
    """Persist the asset ID cache to disk."""
    cache_path.write_text(json.dumps(cache, indent=2))


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
    if not api_key or not api_key.strip():
        return False
    placeholders = {"PLACEHOLDER", "your-api-key-here", "ROBLOX_API_KEY"}
    return api_key.strip() not in placeholders


def _extract_owner_id(api_key: str) -> int | None:
    """Extract ownerId from the embedded JWT in a Roblox Open Cloud API key."""
    import base64
    decoded = base64.b64decode(api_key[20:] + "==").decode("utf-8", errors="ignore")
    # Find the JWT (three dot-separated base64 segments)
    parts = [p for p in decoded.split(".") if len(p) > 20]
    for part in parts:
        try:
            padded = part + "=" * (4 - len(part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            if "ownerId" in payload:
                return int(payload["ownerId"])
        except Exception:  # noqa: BLE001
            continue
    return None


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


def _convert_fbx_to_glb(
    fbx_path: Path,
    texture_path: Path | None,
    output_dir: Path,
) -> Path | None:
    """Convert an FBX file to GLB with an embedded texture.

    Uses assimp CLI to convert FBX → glTF (preserving sub-meshes and UVs),
    injects the texture PNG as a base64 data URI in the glTF material,
    then converts glTF → GLB.

    Returns the path to the GLB file, or None if conversion fails.
    """
    import base64
    import subprocess
    import tempfile

    stem = fbx_path.stem
    glb_output = output_dir / f"{stem}.glb"

    # Skip if GLB already exists and is newer
    if glb_output.exists() and glb_output.stat().st_mtime > fbx_path.stat().st_mtime:
        return glb_output

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        gltf_path = tmpdir / "model.gltf"

        # FBX → glTF (text format, preserves sub-meshes)
        result = subprocess.run(
            [_find_assimp_cli() or "assimp", "export", str(fbx_path), str(gltf_path)],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not gltf_path.exists():
            return None

        # Inject textures into glTF — one per material slot.
        # FBX material names (e.g. "Bin", "Plaster", "VCOL") map to
        # texture files named "<MaterialName>_color.png" in the textures dir.
        textures_dir_for_glb = output_dir.parent / "textures"
        try:
            gltf_data = json.loads(gltf_path.read_text())
            images_list = []
            textures_list = []

            for mat in gltf_data.get("materials", []):
                mat_name = mat.get("name", "")
                # Look for <MaterialName>_color.png
                tex_candidates = [
                    textures_dir_for_glb / f"{mat_name}_color.png",
                    texture_path if texture_path else None,
                ]
                found_tex = None
                for candidate in tex_candidates:
                    if candidate and candidate.exists():
                        found_tex = candidate
                        break

                if found_tex:
                    tex_b64 = base64.b64encode(found_tex.read_bytes()).decode()
                    mime = "image/png" if found_tex.suffix.lower() == ".png" else "image/jpeg"
                    img_idx = len(images_list)
                    images_list.append({
                        "uri": f"data:{mime};base64,{tex_b64}",
                        "mimeType": mime,
                    })
                    tex_idx = len(textures_list)
                    textures_list.append({"source": img_idx})

                    if "pbrMetallicRoughness" not in mat:
                        mat["pbrMetallicRoughness"] = {}
                    mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_idx}
                    mat["pbrMetallicRoughness"]["metallicFactor"] = 0.0
                    mat["pbrMetallicRoughness"]["roughnessFactor"] = 1.0

            if images_list:
                gltf_data["images"] = images_list
                gltf_data["textures"] = textures_list
                gltf_path.write_text(json.dumps(gltf_data))
        except Exception:
            pass  # Proceed without texture injection

        # glTF → GLB
        result2 = subprocess.run(
            [_find_assimp_cli() or "assimp", "export", str(gltf_path), str(glb_output)],
            capture_output=True, timeout=30,
        )
        if result2.returncode != 0 or not glb_output.exists():
            return None

    return glb_output


def _find_assimp_cli() -> str | None:
    """Find the assimp CLI tool."""
    import shutil
    return shutil.which("assimp")


_CONTENT_TYPE_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".fbx": "model/fbx",
    ".obj": "model/obj",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
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

    Works for images (Image for PBR textures, Decal for UI), audio (Audio),
    and meshes (Model).
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
            text_stem = Path(text_lower).stem
            if text_lower in name_to_url:
                text = name_to_url[text_lower]
            elif text_lower in stem_to_url:
                text = stem_to_url[text_lower]
            elif text_stem in stem_to_url:
                text = stem_to_url[text_stem]

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
            url_el = ET.SubElement(sa_cmap, "url")
            url_el.text = matched_url
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


def _inject_mesh_loader(rbxl_path: Path, mesh_asset_ids: dict[str, int]) -> None:
    """Inject a MeshLoader Script that uses InsertService:LoadAsset().

    MeshPart.MeshId set in XML is ignored by Roblox Studio. The only way
    to get proper textured meshes is InsertService:LoadAsset() at runtime.

    This function:
    1. Removes MeshPart items from the .rbxl (they'd render as grey boxes)
    2. Injects a Script that loads each Model asset via InsertService
       and parents the content into ReplicatedStorage/Templates
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(rbxl_path)
    root = tree.getroot()

    # Build asset list for the Luau script
    # De-duplicate: same mesh filename → same asset ID
    unique_assets: dict[str, int] = {}
    for name, aid in mesh_asset_ids.items():
        stem = Path(name).stem
        unique_assets[stem] = aid

    # Generate Luau source
    asset_lines = []
    for stem, aid in sorted(unique_assets.items()):
        asset_lines.append(f'    {{id = {aid}, name = "{stem}"}},')
    assets_table = "\n".join(asset_lines)

    loader_source = f'''\
-- MeshLoader.lua (auto-generated)
-- Loads uploaded mesh FBX assets via InsertService:LoadAsset(),
-- stores templates in ReplicatedStorage/Templates, and applies MeshIds to
-- matching MeshParts already placed in Workspace.

local InsertService = game:GetService("InsertService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

-- Ensure the Templates folder exists in ReplicatedStorage
local Templates = ReplicatedStorage:FindFirstChild("Templates")
if not Templates then
    Templates = Instance.new("Folder")
    Templates.Name = "Templates"
    Templates.Parent = ReplicatedStorage
end

local meshAssets = {{
{assets_table}
}}

local loaded = 0
local failed = 0

-- Strip trailing " (N)" pattern to get base mesh name for matching
local function baseName(name)
    return name:match("^(.-)%%s*%%(%d+%%)$") or name
end

-- Recursively find all MeshParts in a container
local function findMeshParts(container, results)
    results = results or {{}}
    for _, child in ipairs(container:GetChildren()) do
        if child:IsA("MeshPart") then
            table.insert(results, child)
        end
        findMeshParts(child, results)
    end
    return results
end

local function loadOneAsset(asset)
    local MAX_RETRIES = 3
    for attempt = 1, MAX_RETRIES do
        local ok, model = pcall(function()
            return InsertService:LoadAsset(asset.id)
        end)
        if ok and model then
            local sourceMeshPart = nil
            for _, desc in ipairs(model:GetDescendants()) do
                if desc:IsA("MeshPart") then
                    sourceMeshPart = desc
                    break
                end
            end

            if sourceMeshPart then
                local template = sourceMeshPart:Clone()
                template.Name = asset.name
                template.Parent = Templates

                -- Replace matching placeholder MeshParts everywhere: Workspace (scene objects)
                -- and ReplicatedStorage (prefab templates used for runtime spawning)
                -- (MeshId is read-only at runtime, so we clone the loaded part instead)
                local allParts = findMeshParts(Workspace)
                for _, p in ipairs(findMeshParts(ReplicatedStorage)) do
                    table.insert(allParts, p)
                end
                for _, part in ipairs(allParts) do
                    if baseName(part.Name) == asset.name then
                        local replacement = sourceMeshPart:Clone()
                        replacement.Name = part.Name
                        replacement.CFrame = part.CFrame
                        replacement.Anchored = true
                        replacement.CanCollide = part.CanCollide
                        replacement.Transparency = part.Transparency
                        replacement.Color = part.Color
                        replacement.Size = part.Size
                        -- Copy SurfaceAppearance and other children from placeholder
                        -- (the rbxl has textures as SurfaceAppearance children,
                        --  but the InsertService-loaded mesh won't have them)
                        for _, child in ipairs(part:GetChildren()) do
                            child.Parent = replacement
                        end
                        replacement.Parent = part.Parent
                        part:Destroy()
                    end
                end
            else
                local child = model:GetChildren()[1]
                if child then
                    child.Name = asset.name
                    child.Parent = Templates
                end
            end

            model:Destroy()
            loaded = loaded + 1
            return true
        else
            if attempt < MAX_RETRIES then
                task.wait(1 * attempt)
            else
                warn("[MeshLoader] Failed to load " .. asset.name .. ": " .. tostring(model))
                failed = failed + 1
            end
        end
    end
    return false
end

-- Load in batches to avoid overwhelming InsertService
local BATCH_SIZE = 10
for i = 1, #meshAssets, BATCH_SIZE do
    local batchEnd = math.min(i + BATCH_SIZE - 1, #meshAssets)
    for j = i, batchEnd do
        task.spawn(function()
            loadOneAsset(meshAssets[j])
        end)
    end
    -- Wait for this batch to finish before starting the next
    local batchCount = batchEnd - i + 1
    local prevTotal = loaded + failed - batchCount
    while (loaded + failed) < (i - 1 + batchCount) do
        task.wait(0.1)
    end
    task.wait(0.2)
end

-- Wait for any stragglers
while loaded + failed < #meshAssets do
    task.wait(0.1)
end

print("[MeshLoader] Loaded " .. loaded .. "/" .. #meshAssets .. " mesh assets into ReplicatedStorage/Templates")

-- Signal completion so game scripts can proceed
local done = Instance.new("BoolValue")
done.Name = "MeshLoaderDone"
done.Parent = ReplicatedStorage
'''

    # Find or create ServerScriptService
    sss = None
    for item in root.findall("Item"):
        if item.get("class") == "ServerScriptService":
            sss = item
            break
    if sss is None:
        sss = ET.SubElement(root, "Item")
        sss.set("class", "ServerScriptService")
        sp = ET.SubElement(sss, "Properties")
        n = ET.SubElement(sp, "string")
        n.set("name", "Name")
        n.text = "ServerScriptService"

    # Remove any existing MeshLoader
    for existing in sss.findall("Item"):
        ep = existing.find("Properties")
        if ep is not None:
            for p in ep:
                if p.get("name") == "Name" and p.text == "MeshLoader":
                    sss.remove(existing)
                    break

    # Add the MeshLoader script
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
    asset_cache_path: Path | None = None,
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

    # ── Auto-extract creator_id from API key JWT if not provided ──────
    if creator_id is None:
        creator_id = _extract_owner_id(api_key)
        if creator_id:
            logger.info("Auto-detected creator_id=%d from API key", creator_id)

    # ── Load asset cache from previous runs ───────────────────────────
    asset_cache: dict[str, dict] = {}
    if asset_cache_path:
        asset_cache = _load_asset_cache(asset_cache_path)
        # Pre-populate result.asset_ids with cached entries so patching works
        for name, entry in asset_cache.items():
            result.asset_ids[name] = entry["asset_id"]
        if asset_cache:
            logger.info("Loaded %d cached asset IDs — will skip re-upload for these", len(asset_cache))

    # ── Convert FBX→GLB with textures, then upload ──────────────────
    if meshes_dir and meshes_dir.is_dir():
        mesh_exts = {".fbx", ".obj", ".dae"}
        glb_dir = meshes_dir / "glb"
        glb_dir.mkdir(exist_ok=True)

        # Build mesh→texture mapping for texture injection
        _mesh_mat_map = _build_mesh_material_map(unity_project_path) if unity_project_path else {}
        textures_dir_path = meshes_dir.parent / "textures"

        for mesh_path in sorted(meshes_dir.iterdir()):
            if mesh_path.suffix.lower() not in mesh_exts:
                continue

            # Skip if already cached from a previous run
            if _is_cached(mesh_path.name, asset_cache):
                logger.debug("Skipping cached mesh: %s", mesh_path.name)
                continue

            # Find matching texture for this mesh
            tex_path = None
            mesh_stem = mesh_path.stem.lower()
            tex_filename = _mesh_mat_map.get(mesh_stem)
            if tex_filename and textures_dir_path.is_dir():
                candidate = textures_dir_path / tex_filename
                if candidate.exists():
                    tex_path = candidate

            # Convert FBX → GLB with embedded texture
            glb_path = _convert_fbx_to_glb(mesh_path, tex_path, glb_dir)
            upload_path = glb_path if glb_path else mesh_path

            try:
                resp = _upload_asset(
                    upload_path, api_key, asset_type="Model",
                    display_name=mesh_path.stem[:50],
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
            if _is_cached(img_path.name, asset_cache):
                logger.debug("Skipping cached texture: %s", img_path.name)
                continue
            try:
                resp = _upload_asset(
                    img_path, api_key, asset_type="Image",
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
            if _is_cached(img_path.name, asset_cache):
                logger.debug("Skipping cached sprite: %s", img_path.name)
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
            if _is_cached(audio_path.name, asset_cache):
                logger.debug("Skipping cached audio: %s", audio_path.name)
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

    # ── Save asset cache with newly uploaded assets ─────────────────
    if asset_cache_path:
        # Merge new uploads into the cache (type is inferred from extension)
        _TYPE_BY_EXT: dict[str, str] = {
            ".fbx": "MODEL", ".obj": "MODEL", ".dae": "MODEL",
            ".png": "IMAGE", ".jpg": "IMAGE", ".jpeg": "IMAGE",
            ".ogg": "AUDIO", ".mp3": "AUDIO", ".wav": "AUDIO",
        }
        for name, aid in result.asset_ids.items():
            if name not in asset_cache:
                ext = Path(name).suffix.lower()
                asset_cache[name] = {
                    "asset_id": aid,
                    "type": _TYPE_BY_EXT.get(ext, "UNKNOWN"),
                }
        _save_asset_cache(asset_cache_path, asset_cache)
        logger.info("Saved asset cache with %d entries to %s", len(asset_cache), asset_cache_path)

    # ── Inject MeshLoader script into .rbxl ──────────────────────────
    # Meshes uploaded as GLB Model assets can only be loaded at runtime
    # via InsertService:LoadAsset(). Generate a Script that loads each
    # mesh Model and parents it into ReplicatedStorage/Templates.
    # Identify mesh assets by extension OR by cache type metadata
    mesh_exts = {".fbx", ".obj", ".dae"}
    mesh_asset_ids = {}
    for k, v in result.asset_ids.items():
        if Path(k).suffix.lower() in mesh_exts:
            mesh_asset_ids[k] = v
        elif asset_cache.get(k, {}).get("type") == "MODEL":
            mesh_asset_ids[k] = v
    if mesh_asset_ids and rbxl_path.exists():
        try:
            _inject_mesh_loader(rbxl_path, mesh_asset_ids)
            logger.info("Injected MeshLoader with %d mesh assets", len(mesh_asset_ids))
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"MeshLoader injection failed: {exc}")

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
