"""
prefab_parser.py — Parses Unity .prefab files into reusable PrefabTemplate objects.

Prefabs are self-contained GameObject hierarchies in Unity. This module reads
each .prefab file, resolves its internal component graph, and returns a
PrefabTemplate that can be referenced when building the Roblox place.

No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_UNITY_HEADER = re.compile(r"^%.*\n", re.MULTILINE)
_DOC_SEP = re.compile(r"^--- !u!\d+ &\d+", re.MULTILINE)


@dataclass
class PrefabComponent:
    """A component attached to a node inside a prefab."""
    component_type: str
    properties: dict[str, Any]


@dataclass
class PrefabNode:
    """A single GameObject node within a prefab hierarchy."""
    name: str
    active: bool
    components: list[PrefabComponent] = field(default_factory=list)
    children: list["PrefabNode"] = field(default_factory=list)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass
class PrefabTemplate:
    """Parsed representation of a Unity prefab."""
    prefab_path: Path
    name: str                            # Derived from filename
    root: PrefabNode | None              # Root node of the prefab hierarchy
    all_nodes: list[PrefabNode] = field(default_factory=list)
    raw_documents: list[dict] = field(default_factory=list)


@dataclass
class PrefabLibrary:
    """Collection of all parsed prefabs found in a Unity project."""
    prefabs: list[PrefabTemplate] = field(default_factory=list)
    by_name: dict[str, PrefabTemplate] = field(default_factory=dict)


def _clean_yaml(text: str) -> str:
    text = _UNITY_HEADER.sub("", text)
    text = _DOC_SEP.sub("---", text)
    return text


def _build_node(go: dict) -> PrefabNode:
    return PrefabNode(
        name=go.get("m_Name", "Node"),
        active=bool(go.get("m_IsActive", 1)),
    )


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

    for prefab_path in assets_dir.rglob("*.prefab"):
        raw = prefab_path.read_text(encoding="utf-8", errors="replace")
        cleaned = _clean_yaml(raw)

        try:
            docs = list(yaml.safe_load_all(cleaned))
        except yaml.YAMLError:
            docs = []

        template = PrefabTemplate(
            prefab_path=prefab_path,
            name=prefab_path.stem,
            root=None,
            raw_documents=docs,
        )

        # Build nodes from GameObject entries
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if "GameObject" in doc:
                node = _build_node(doc["GameObject"])
                template.all_nodes.append(node)

        # First node is treated as root (simplified)
        if template.all_nodes:
            template.root = template.all_nodes[0]
            # Wire remaining as children of root for stub purposes
            for child in template.all_nodes[1:]:
                template.root.children.append(child)

        library.prefabs.append(template)
        library.by_name[template.name] = template

    return library
