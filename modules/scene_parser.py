"""
scene_parser.py — Parses Unity .unity scene files into a structured hierarchy.

Unity scene files are multi-document YAML with a custom header.  Each YAML
document represents one serialised object (GameObject, Transform, MeshRenderer,
etc.) and is preceded by a separator carrying the Unity classID and local
fileID:

    --- !u!{classID} &{fileID}

This module:
  1. Pre-scans separators to capture (classID, fileID) per document.
  2. Strips the non-standard header so PyYAML can parse the body.
  3. Pairs each parsed document with its (classID, fileID).
  4. Builds SceneNode objects from GameObjects (classID 1).
  5. Resolves Transform/RectTransform docs (classID 4/224) to populate
     position, rotation, scale, and parent/child hierarchy via m_Father.
  6. Attaches other components (MeshFilter, MeshRenderer, MonoBehaviour, …)
     to their owning GameObjects via m_GameObject back-references.
  7. Extracts mesh GUIDs from MeshFilter.m_Mesh.
  8. Extracts material GUIDs from MeshRenderer.m_Materials.
  9. Records PrefabInstance docs (classID 1001) with their source GUID
     and property modifications for downstream resolution.

No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # PyYAML


# ---------------------------------------------------------------------------
# Unity YAML helpers
# ---------------------------------------------------------------------------

_UNITY_YAML_HEADER = re.compile(r"^%YAML.*\n%TAG.*\n", re.MULTILINE)
_UNITY_DOC_SEPARATOR = re.compile(r"^--- !u!(\d+) &(\d+).*$", re.MULTILINE)

# Well-known Unity classIDs
_CID_GAME_OBJECT = 1
_CID_TRANSFORM = 4
_CID_MESH_RENDERER = 23
_CID_MESH_FILTER = 33
_CID_BOX_COLLIDER = 65
_CID_SPHERE_COLLIDER = 135
_CID_CAPSULE_COLLIDER = 136
_CID_MESH_COLLIDER = 64
_CID_RIGIDBODY = 54
_CID_SKINNED_MESH_RENDERER = 137
_CID_MONO_BEHAVIOUR = 114
_CID_RECT_TRANSFORM = 224
_CID_PREFAB_INSTANCE = 1001


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ComponentData:
    """Raw key/value data for a Unity component attached to a GameObject."""
    component_type: str          # e.g. "Transform", "MeshRenderer", "Rigidbody"
    file_id: str                 # Unity local file ID
    properties: dict[str, Any]  # Raw parsed YAML properties


@dataclass
class PrefabInstanceData:
    """A PrefabInstance document found in the scene."""
    file_id: str
    source_prefab_guid: str              # GUID of the .prefab asset
    source_prefab_file_id: str           # fileID inside the prefab
    transform_parent_file_id: str        # parent Transform in the scene
    modifications: list[dict[str, Any]]  # m_Modifications entries
    removed_components: list[Any] = field(default_factory=list)


@dataclass
class SceneNode:
    """A single GameObject in the Unity scene hierarchy."""
    name: str
    file_id: str
    active: bool
    layer: int
    tag: str
    components: list[ComponentData] = field(default_factory=list)
    children: list["SceneNode"] = field(default_factory=list)
    parent_file_id: str | None = None    # None → root node

    # Transform shorthand (populated from Transform component)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # quaternion
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    # Mesh reference (populated from MeshFilter or SkinnedMeshRenderer)
    mesh_guid: str | None = None
    mesh_file_id: str | None = None      # sub-asset fileID inside the mesh asset

    # Whether this node came from a PrefabInstance
    from_prefab_instance: bool = False


@dataclass
class ParsedScene:
    """Top-level result of parsing a Unity scene file."""
    scene_path: Path
    roots: list[SceneNode] = field(default_factory=list)   # top-level GameObjects
    all_nodes: dict[str, SceneNode] = field(default_factory=dict)  # file_id → node
    raw_documents: list[dict[str, Any]] = field(default_factory=list)
    referenced_material_guids: set[str] = field(default_factory=set)
    referenced_mesh_guids: set[str] = field(default_factory=set)
    prefab_instances: list[PrefabInstanceData] = field(default_factory=list)


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
    """Extract fileID from a Unity object reference dict, or None."""
    if isinstance(ref, dict):
        fid = ref.get("fileID", 0)
        if fid:
            return str(fid)
    return None


def _ref_guid(ref: Any) -> str | None:
    """Extract guid from a Unity object reference dict, or None."""
    if isinstance(ref, dict):
        guid = ref.get("guid", "")
        if guid and guid != "0" * 32:
            return guid
    return None


def _parse_documents(raw_text: str) -> list[tuple[int, str, dict]]:
    """
    Parse a Unity YAML file into (classID, fileID, body_dict) triples.

    Pre-scans the document separators to capture classID and fileID before
    handing the cleaned text to PyYAML.
    """
    # Step 1: collect (classID, fileID) for every document separator
    doc_headers: list[tuple[int, str]] = []
    for m in _UNITY_DOC_SEPARATOR.finditer(raw_text):
        doc_headers.append((int(m.group(1)), m.group(2)))

    # Step 2: strip the non-standard header and replace separators
    cleaned = _UNITY_YAML_HEADER.sub("", raw_text, count=1)
    cleaned = _UNITY_DOC_SEPARATOR.sub("---", cleaned)

    # Step 3: parse YAML documents
    try:
        docs: list[dict] = list(yaml.safe_load_all(cleaned))
    except yaml.YAMLError:
        return []

    # Step 4: pair each document with its header
    # PyYAML may produce fewer docs than separators (empty docs are skipped),
    # and it may produce extra None docs.  Filter non-dict results.
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


def _doc_body(doc: dict) -> dict:
    """
    Unity YAML documents are wrapped: ``{ClassName: {actual_props}}``.
    Return the inner dict.
    """
    for v in doc.values():
        if isinstance(v, dict):
            return v
    return doc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_scene(scene_path: str | Path) -> ParsedScene:
    """
    Parse a Unity .unity scene file into a tree of SceneNode objects.

    Resolves Transform hierarchy, attaches components to GameObjects, and
    extracts mesh and material GUIDs.

    Args:
        scene_path: Path to the .unity scene file.

    Returns:
        ParsedScene with root nodes and a flat all_nodes lookup.

    Raises:
        FileNotFoundError: If the scene file does not exist.
        ValueError: If the file cannot be parsed as a Unity YAML scene.
    """
    scene_path = Path(scene_path).resolve()
    if not scene_path.exists():
        raise FileNotFoundError(f"Scene file not found: {scene_path}")

    raw_text = scene_path.read_text(encoding="utf-8", errors="replace")
    triples = _parse_documents(raw_text)

    result = ParsedScene(scene_path=scene_path)
    result.raw_documents = [doc for _, _, doc in triples]

    # ------------------------------------------------------------------
    # Pass 1: Index all documents by fileID and classify by classID
    # ------------------------------------------------------------------

    file_id_to_doc: dict[str, dict] = {}            # fileID → raw body
    file_id_to_class: dict[str, int] = {}            # fileID → classID
    go_docs: dict[str, dict] = {}                    # fileID → GameObject body
    transform_docs: dict[str, dict] = {}             # fileID → Transform body
    component_docs: list[tuple[str, int, dict]] = [] # (fileID, classID, body)
    prefab_instance_docs: list[tuple[str, dict]] = []  # (fileID, body)

    for cid, fid, doc in triples:
        body = _doc_body(doc)
        file_id_to_doc[fid] = body
        file_id_to_class[fid] = cid

        if cid == _CID_GAME_OBJECT:
            go_docs[fid] = body
        elif cid in (_CID_TRANSFORM, _CID_RECT_TRANSFORM):
            transform_docs[fid] = body
        elif cid == _CID_PREFAB_INSTANCE:
            prefab_instance_docs.append((fid, body))
        elif cid in (_CID_MESH_FILTER, _CID_MESH_RENDERER,
                     _CID_SKINNED_MESH_RENDERER, _CID_MONO_BEHAVIOUR,
                     _CID_BOX_COLLIDER, _CID_SPHERE_COLLIDER,
                     _CID_CAPSULE_COLLIDER, _CID_MESH_COLLIDER,
                     _CID_RIGIDBODY):
            component_docs.append((fid, cid, body))

    # ------------------------------------------------------------------
    # Pass 2: Build SceneNode stubs from GameObjects
    # ------------------------------------------------------------------

    for fid, go in go_docs.items():
        node = SceneNode(
            name=go.get("m_Name", "GameObject"),
            file_id=fid,
            active=bool(go.get("m_IsActive", 1)),
            layer=int(go.get("m_Layer", 0)),
            tag=go.get("m_TagString", "Untagged"),
        )
        result.all_nodes[fid] = node

    # ------------------------------------------------------------------
    # Pass 3: Resolve Transforms → populate position, rotation, scale,
    #         parent/child hierarchy, and attach as component
    # ------------------------------------------------------------------

    # Build Transform.m_GameObject → Transform body lookup
    # (a Transform's m_GameObject points to the owning GO)
    go_fid_to_transform: dict[str, tuple[str, dict]] = {}  # GO fileID → (xform fileID, body)
    for xform_fid, xform in transform_docs.items():
        go_ref = _ref_file_id(xform.get("m_GameObject"))
        if go_ref:
            go_fid_to_transform[go_ref] = (xform_fid, xform)

    # Also build transform fileID → GO fileID for parent wiring
    xform_fid_to_go_fid: dict[str, str] = {}
    for go_fid, (xform_fid, _xform) in go_fid_to_transform.items():
        xform_fid_to_go_fid[xform_fid] = go_fid

    for go_fid, node in result.all_nodes.items():
        entry = go_fid_to_transform.get(go_fid)
        if entry is None:
            continue
        xform_fid, xform = entry

        # Populate transform values
        node.position = _extract_vec3(xform, "m_LocalPosition")
        node.rotation = _extract_quat(xform, "m_LocalRotation")
        node.scale = _extract_vec3(xform, "m_LocalScale")

        # Determine parent via m_Father
        father_xform_fid = _ref_file_id(xform.get("m_Father"))
        if father_xform_fid:
            parent_go_fid = xform_fid_to_go_fid.get(father_xform_fid)
            if parent_go_fid and parent_go_fid in result.all_nodes:
                node.parent_file_id = parent_go_fid

        # Attach Transform as a component
        comp_type = "RectTransform" if file_id_to_class.get(xform_fid) == _CID_RECT_TRANSFORM else "Transform"
        node.components.append(ComponentData(
            component_type=comp_type,
            file_id=xform_fid,
            properties=xform,
        ))

    # ------------------------------------------------------------------
    # Pass 4: Attach other components to their GameObjects
    # ------------------------------------------------------------------

    _CLASS_ID_TO_NAME: dict[int, str] = {
        _CID_MESH_FILTER: "MeshFilter",
        _CID_MESH_RENDERER: "MeshRenderer",
        _CID_SKINNED_MESH_RENDERER: "SkinnedMeshRenderer",
        _CID_MONO_BEHAVIOUR: "MonoBehaviour",
        _CID_BOX_COLLIDER: "BoxCollider",
        _CID_SPHERE_COLLIDER: "SphereCollider",
        _CID_CAPSULE_COLLIDER: "CapsuleCollider",
        _CID_MESH_COLLIDER: "MeshCollider",
        _CID_RIGIDBODY: "Rigidbody",
    }

    for comp_fid, cid, body in component_docs:
        go_ref = _ref_file_id(body.get("m_GameObject"))
        if not go_ref:
            continue
        node = result.all_nodes.get(go_ref)
        if node is None:
            continue

        comp_type = _CLASS_ID_TO_NAME.get(cid, f"Component_{cid}")
        node.components.append(ComponentData(
            component_type=comp_type,
            file_id=comp_fid,
            properties=body,
        ))

        # Extract mesh GUID from MeshFilter.m_Mesh
        if cid == _CID_MESH_FILTER:
            mesh_ref = body.get("m_Mesh", {})
            guid = _ref_guid(mesh_ref)
            if guid:
                node.mesh_guid = guid
                node.mesh_file_id = str(mesh_ref.get("fileID", ""))
                result.referenced_mesh_guids.add(guid)

        # Extract mesh GUID from SkinnedMeshRenderer.m_Mesh
        if cid == _CID_SKINNED_MESH_RENDERER:
            mesh_ref = body.get("m_Mesh", {})
            guid = _ref_guid(mesh_ref)
            if guid:
                node.mesh_guid = guid
                node.mesh_file_id = str(mesh_ref.get("fileID", ""))
                result.referenced_mesh_guids.add(guid)

        # Extract material GUIDs from renderers
        if cid in (_CID_MESH_RENDERER, _CID_SKINNED_MESH_RENDERER):
            for mat_ref in body.get("m_Materials", []):
                guid = _ref_guid(mat_ref)
                if guid:
                    result.referenced_material_guids.add(guid)

    # ------------------------------------------------------------------
    # Pass 5: Wire parent/child hierarchy
    # ------------------------------------------------------------------

    for node in result.all_nodes.values():
        if node.parent_file_id is None:
            result.roots.append(node)
        else:
            parent = result.all_nodes.get(node.parent_file_id)
            if parent:
                parent.children.append(node)
            else:
                # Parent not found (may be a PrefabInstance-owned GO) → root
                result.roots.append(node)

    # ------------------------------------------------------------------
    # Pass 6: Record PrefabInstance documents
    # ------------------------------------------------------------------

    for pi_fid, body in prefab_instance_docs:
        source_ref = body.get("m_SourcePrefab", {})
        source_guid = _ref_guid(source_ref) or ""
        source_file_id = str(source_ref.get("fileID", ""))

        modification = body.get("m_Modification", {})
        transform_parent = _ref_file_id(modification.get("m_TransformParent")) or ""
        modifications = modification.get("m_Modifications", []) or []
        removed = modification.get("m_RemovedComponents", []) or []

        result.prefab_instances.append(PrefabInstanceData(
            file_id=pi_fid,
            source_prefab_guid=source_guid,
            source_prefab_file_id=source_file_id,
            transform_parent_file_id=transform_parent,
            modifications=modifications,
            removed_components=removed,
        ))

    return result
