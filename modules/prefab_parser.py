"""
prefab_parser.py — Parses Unity .prefab files into reusable PrefabTemplate objects.

Prefabs are self-contained GameObject hierarchies in Unity.  Like scene files,
they are multi-document YAML with ``--- !u!{classID} &{fileID}`` separators.

This module applies the same document-resolution strategy as scene_parser:
  1. Pre-scan separators to capture (classID, fileID) per document.
  2. Build nodes from GameObjects, resolve Transforms for hierarchy and
     position/rotation/scale, attach components.
  3. Extract mesh GUIDs from MeshFilter and material GUIDs from renderers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.unity_yaml_utils import (
    CID_GAME_OBJECT as _CID_GAME_OBJECT,
    CID_TRANSFORM as _CID_TRANSFORM,
    CID_MESH_RENDERER as _CID_MESH_RENDERER,
    CID_MESH_FILTER as _CID_MESH_FILTER,
    CID_SKINNED_MESH_RENDERER as _CID_SKINNED_MESH_RENDERER,
    CID_RECT_TRANSFORM as _CID_RECT_TRANSFORM,
    KNOWN_COMPONENT_CIDS as _KNOWN_COMPONENT_CIDS,
    COMPONENT_CID_TO_NAME as _COMPONENT_CID_TO_NAME,
    extract_vec3 as _extract_vec3,
    extract_quat as _extract_quat,
    ref_file_id as _ref_file_id,
    ref_guid as _ref_guid,
    parse_documents as _parse_documents,
    doc_body as _doc_body,
)


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
    is_multi_root: bool = False          # True when prefab had multiple root nodes


@dataclass
class PrefabLibrary:
    """Collection of all parsed prefabs found in a Unity project."""
    prefabs: list[PrefabTemplate] = field(default_factory=list)
    by_name: dict[str, PrefabTemplate] = field(default_factory=dict)
    referenced_material_guids: set[str] = field(default_factory=set)
    referenced_mesh_guids: set[str] = field(default_factory=set)




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
        elif cid in _KNOWN_COMPONENT_CIDS:
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
    for comp_fid, cid, body in component_docs:
        go_ref = _ref_file_id(body.get("m_GameObject"))
        if not go_ref:
            continue
        node = template.all_nodes.get(go_ref)
        if node is None:
            continue

        comp_type = _COMPONENT_CID_TO_NAME.get(cid, f"Component_{cid}")
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
            for mat_ref in body.get("m_Materials") or []:
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

    if len(roots) == 1:
        template.root = roots[0]
    elif len(roots) > 1:
        # Multi-root prefab: create a synthetic container node to hold all roots.
        # This is common in procedurally-generated prefabs and prefabs with
        # detached hierarchies (e.g. particle systems, UI overlays).
        template.is_multi_root = True
        container = PrefabNode(
            name=template.name,
            file_id="__synthetic_root__",
            active=True,
            children=roots,
        )
        template.root = container

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
