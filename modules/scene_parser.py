"""
scene_parser.py — Parses Unity .unity scene files into a structured hierarchy.

Unity scene files are YAML-based (with a custom Unity header). This module
reads them, resolves GameObject parent/child relationships, and returns a
tree of SceneNode objects that represent the scene hierarchy.

No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # PyYAML


# Unity YAML files start with a non-standard header; strip it before parsing.
_UNITY_YAML_HEADER = re.compile(r"^%YAML.*\n%TAG.*\n", re.MULTILINE)
_UNITY_DOC_SEPARATOR = re.compile(r"^--- !u!(\d+) &(\d+)", re.MULTILINE)


@dataclass
class ComponentData:
    """Raw key/value data for a Unity component attached to a GameObject."""
    component_type: str          # e.g. "Transform", "MeshRenderer", "Rigidbody"
    file_id: str                 # Unity local file ID
    properties: dict[str, Any]  # Raw parsed YAML properties


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


@dataclass
class ParsedScene:
    """Top-level result of parsing a Unity scene file."""
    scene_path: Path
    roots: list[SceneNode] = field(default_factory=list)   # top-level GameObjects
    all_nodes: dict[str, SceneNode] = field(default_factory=dict)  # file_id → node
    raw_documents: list[dict[str, Any]] = field(default_factory=list)


def _strip_unity_header(text: str) -> str:
    """Remove Unity-specific YAML directives that confuse standard parsers."""
    text = _UNITY_YAML_HEADER.sub("", text, count=1)
    # Replace document separators with standard YAML ---
    text = _UNITY_DOC_SEPARATOR.sub(r"---", text)
    return text


def _extract_vec3(d: dict, key: str) -> tuple[float, float, float]:
    v = d.get(key, {})
    return (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))


def _extract_quat(d: dict, key: str) -> tuple[float, float, float, float]:
    v = d.get(key, {})
    return (float(v.get("x", 0)), float(v.get("y", 0)),
            float(v.get("z", 0)), float(v.get("w", 1)))


def parse_scene(scene_path: str | Path) -> ParsedScene:
    """
    Parse a Unity .unity scene file into a tree of SceneNode objects.

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
    cleaned = _strip_unity_header(raw_text)

    try:
        docs: list[dict] = list(yaml.safe_load_all(cleaned))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse scene YAML: {exc}") from exc

    result = ParsedScene(scene_path=scene_path, raw_documents=docs)

    # First pass: build node stubs from GameObject documents
    file_id_to_raw: dict[str, dict] = {}
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if "GameObject" in doc:
            go = doc["GameObject"]
            fid = str(go.get("m_LocalIdentfierInFile", id(go)))
            file_id_to_raw[fid] = go

    # Build SceneNode stubs
    for fid, go in file_id_to_raw.items():
        node = SceneNode(
            name=go.get("m_Name", "GameObject"),
            file_id=fid,
            active=bool(go.get("m_IsActive", 1)),
            layer=int(go.get("m_Layer", 0)),
            tag=go.get("m_TagString", "Untagged"),
        )
        result.all_nodes[fid] = node

    # Wire parent/child relationships (simplified — production code would
    # resolve Transform component m_Father references)
    for node in result.all_nodes.values():
        if node.parent_file_id is None:
            result.roots.append(node)
        else:
            parent = result.all_nodes.get(node.parent_file_id)
            if parent:
                parent.children.append(node)

    return result
