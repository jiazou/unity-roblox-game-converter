"""
prefab_parser.py — Parses Unity .prefab files into reusable PrefabTemplate objects.

Prefabs are self-contained GameObject hierarchies in Unity.  Like scene files,
they are multi-document YAML with ``--- !u!{classID} &{fileID}`` separators.

This module applies the same document-resolution strategy as scene_parser:
  1. Pre-scan separators to capture (classID, fileID) per document.
  2. Build nodes from GameObjects, resolve Transforms for hierarchy and
     position/rotation/scale, attach components.
  3. Extract mesh GUIDs from MeshFilter and material GUIDs from renderers.

No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Unity YAML helpers (same patterns as scene_parser)
# ---------------------------------------------------------------------------

_UNITY_YAML_HEADER = re.compile(r"^%YAML.*\n%TAG.*\n", re.MULTILINE)
_UNITY_DOC_SEPARATOR = re.compile(r"^--- !u!(\d+) &(\d+).*$", re.MULTILINE)

_CID_GAME_OBJECT = 1
_CID_TRANSFORM = 4
_CID_MESH_RENDERER = 23
_CID_MESH_FILTER = 33
_CID_SKINNED_MESH_RENDERER = 137
_CID_MONO_BEHAVIOUR = 114
_CID_RECT_TRANSFORM = 224


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PrefabComponent:
    """A component attached to a node inside a prefab."""
    component_type: str
    file_id: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class PrefabNode:
    """A single GameObject node within a prefab hierarchy."""
    name: str
    file_id: str
    active: bool
    components: list[PrefabComponent] = field(default_factory=list)
    children: list["PrefabNode"] = field(default_factory=list)
    parent_file_id: str | None = None
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    mesh_guid: str | None = None
    mesh_file_id: str | None = None


@dataclass
class PrefabTemplate:
    """Parsed representation of a Unity prefab."""
    prefab_path: Path
    name: str                            # Derived from filename
    root: PrefabNode | None              # Root node of the prefab hierarchy
    all_nodes: dict[str, PrefabNode] = field(default_factory=dict)
    raw_documents: list[dict] = field(default_factory=list)
    referenced_material_guids: set[str] = field(default_factory=set)
    referenced_mesh_guids: set[str] = field(default_factory=set)


@dataclass
class PrefabLibrary:
    """Collection of all parsed prefabs found in a Unity project."""
    prefabs: list[PrefabTemplate] = field(default_factory=list)
    by_name: dict[str, PrefabTemplate] = field(default_factory=dict)
    referenced_material_guids: set[str] = field(default_factory=set)
    referenced_mesh_guids: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_vec3(d: dict, key: str) -> tuple[float, float, float]:
    v = d.get(key, {})
    if not isinstance(v, dict):
        return (0.0, 0.0, 0.0)
    return (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))


def _extract_quat(d: dict, key: str) -> tuple[float, float, float, float]:
    v = d.get(key, {})
    if not isinstance(v, dict):
        return (0.0, 0.0, 0.0, 1.0)
    return (float(v.get("x", 0)), float(v.get("y", 0)),
            float(v.get("z", 0)), float(v.get("w", 1)))


def _ref_file_id(ref: Any) -> str | None:
    if isinstance(ref, dict):
        fid = ref.get("fileID", 0)
        if fid:
            return str(fid)
    return None


def _ref_guid(ref: Any) -> str | None:
    if isinstance(ref, dict):
        guid = ref.get("guid", "")
        if guid and guid != "0" * 32:
            return guid
    return None


def _doc_body(doc: dict) -> dict:
    for v in doc.values():
        if isinstance(v, dict):
            return v
    return doc


def _parse_documents(raw_text: str) -> list[tuple[int, str, dict]]:
    """Parse Unity YAML into (classID, fileID, body_dict) triples."""
    doc_headers: list[tuple[int, str]] = []
    for m in _UNITY_DOC_SEPARATOR.finditer(raw_text):
        doc_headers.append((int(m.group(1)), m.group(2)))

    cleaned = _UNITY_YAML_HEADER.sub("", raw_text, count=1)
    cleaned = _UNITY_DOC_SEPARATOR.sub("---", cleaned)

    try:
        docs: list[dict] = list(yaml.safe_load_all(cleaned))
    except yaml.YAMLError:
        return []

    result: list[tuple[int, str, dict]] = []
    header_idx = 0
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if header_idx < len(doc_headers):
            cid, fid = doc_headers[header_idx]
            header_idx += 1
        else:
            cid, fid = 0, "0"
        result.append((cid, fid, doc))

    return result


# ---------------------------------------------------------------------------
# Single-prefab parser
# ---------------------------------------------------------------------------

def _parse_single_prefab(prefab_path: Path) -> PrefabTemplate:
    """Parse one .prefab file into a PrefabTemplate."""
    raw = prefab_path.read_text(encoding="utf-8", errors="replace")
    triples = _parse_documents(raw)

    template = PrefabTemplate(
        prefab_path=prefab_path,
        name=prefab_path.stem,
        root=None,
        raw_documents=[doc for _, _, doc in triples],
    )

    # Classify documents
    go_docs: dict[str, dict] = {}
    transform_docs: dict[str, dict] = {}
    component_docs: list[tuple[str, int, dict]] = []
    file_id_to_class: dict[str, int] = {}

    for cid, fid, doc in triples:
        body = _doc_body(doc)
        file_id_to_class[fid] = cid

        if cid == _CID_GAME_OBJECT:
            go_docs[fid] = body
        elif cid in (_CID_TRANSFORM, _CID_RECT_TRANSFORM):
            transform_docs[fid] = body
        elif cid in (_CID_MESH_FILTER, _CID_MESH_RENDERER,
                     _CID_SKINNED_MESH_RENDERER, _CID_MONO_BEHAVIOUR):
            component_docs.append((fid, cid, body))

    # Build PrefabNode stubs
    for fid, go in go_docs.items():
        node = PrefabNode(
            name=go.get("m_Name", "Node"),
            file_id=fid,
            active=bool(go.get("m_IsActive", 1)),
        )
        template.all_nodes[fid] = node

    # Resolve Transforms
    go_fid_to_transform: dict[str, tuple[str, dict]] = {}
    for xform_fid, xform in transform_docs.items():
        go_ref = _ref_file_id(xform.get("m_GameObject"))
        if go_ref:
            go_fid_to_transform[go_ref] = (xform_fid, xform)

    xform_fid_to_go_fid: dict[str, str] = {}
    for go_fid, (xform_fid, _) in go_fid_to_transform.items():
        xform_fid_to_go_fid[xform_fid] = go_fid

    for go_fid, node in template.all_nodes.items():
        entry = go_fid_to_transform.get(go_fid)
        if entry is None:
            continue
        xform_fid, xform = entry

        node.position = _extract_vec3(xform, "m_LocalPosition")
        node.rotation = _extract_quat(xform, "m_LocalRotation")
        node.scale = _extract_vec3(xform, "m_LocalScale")

        father_xform_fid = _ref_file_id(xform.get("m_Father"))
        if father_xform_fid:
            parent_go_fid = xform_fid_to_go_fid.get(father_xform_fid)
            if parent_go_fid and parent_go_fid in template.all_nodes:
                node.parent_file_id = parent_go_fid

        comp_type = "RectTransform" if file_id_to_class.get(xform_fid) == _CID_RECT_TRANSFORM else "Transform"
        node.components.append(PrefabComponent(
            component_type=comp_type,
            file_id=xform_fid,
            properties=xform,
        ))

    # Attach other components
    _CLASS_ID_TO_NAME: dict[int, str] = {
        _CID_MESH_FILTER: "MeshFilter",
        _CID_MESH_RENDERER: "MeshRenderer",
        _CID_SKINNED_MESH_RENDERER: "SkinnedMeshRenderer",
        _CID_MONO_BEHAVIOUR: "MonoBehaviour",
    }

    for comp_fid, cid, body in component_docs:
        go_ref = _ref_file_id(body.get("m_GameObject"))
        if not go_ref:
            continue
        node = template.all_nodes.get(go_ref)
        if node is None:
            continue

        comp_type = _CLASS_ID_TO_NAME.get(cid, f"Component_{cid}")
        node.components.append(PrefabComponent(
            component_type=comp_type,
            file_id=comp_fid,
            properties=body,
        ))

        if cid == _CID_MESH_FILTER:
            mesh_ref = body.get("m_Mesh", {})
            guid = _ref_guid(mesh_ref)
            if guid:
                node.mesh_guid = guid
                node.mesh_file_id = str(mesh_ref.get("fileID", ""))
                template.referenced_mesh_guids.add(guid)

        if cid == _CID_SKINNED_MESH_RENDERER:
            mesh_ref = body.get("m_Mesh", {})
            guid = _ref_guid(mesh_ref)
            if guid:
                node.mesh_guid = guid
                node.mesh_file_id = str(mesh_ref.get("fileID", ""))
                template.referenced_mesh_guids.add(guid)

        if cid in (_CID_MESH_RENDERER, _CID_SKINNED_MESH_RENDERER):
            for mat_ref in body.get("m_Materials", []):
                guid = _ref_guid(mat_ref)
                if guid:
                    template.referenced_material_guids.add(guid)

    # Wire hierarchy
    roots: list[PrefabNode] = []
    for node in template.all_nodes.values():
        if node.parent_file_id is None:
            roots.append(node)
        else:
            parent = template.all_nodes.get(node.parent_file_id)
            if parent:
                parent.children.append(node)
            else:
                roots.append(node)

    if roots:
        # Use the first root (typically the top-level prefab GameObject)
        template.root = roots[0]

    return template


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_prefabs(unity_project_path: str | Path) -> PrefabLibrary:
    """
    Discover and parse all .prefab files under *unity_project_path*/Assets.

    Args:
        unity_project_path: Root directory of the Unity project.

    Returns:
        PrefabLibrary containing a PrefabTemplate for each discovered prefab.

    Raises:
        FileNotFoundError: If the Assets/ directory does not exist.
    """
    root = Path(unity_project_path).resolve()
    assets_dir = root / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Assets directory not found: {assets_dir}")

    library = PrefabLibrary()

    for prefab_path in sorted(assets_dir.rglob("*.prefab")):
        try:
            template = _parse_single_prefab(prefab_path)
        except Exception:  # noqa: BLE001
            continue

        library.prefabs.append(template)
        library.by_name[template.name] = template
        library.referenced_material_guids |= template.referenced_material_guids
        library.referenced_mesh_guids |= template.referenced_mesh_guids

    return library
