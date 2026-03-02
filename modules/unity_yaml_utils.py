"""
unity_yaml_utils.py — Shared helpers for parsing Unity YAML files.

Unity scene (.unity) and prefab (.prefab) files both use multi-document YAML
with a custom header and document separators:

    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!{classID} &{fileID}

This module provides the common parsing infrastructure shared by scene_parser
and prefab_parser.

No other module is imported here.
"""

from __future__ import annotations

import re
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Unity YAML regex patterns
# ---------------------------------------------------------------------------

UNITY_YAML_HEADER = re.compile(r"^%YAML.*\n%TAG.*\n", re.MULTILINE)
UNITY_DOC_SEPARATOR = re.compile(r"^--- !u!(\d+) &(\d+).*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Well-known Unity classIDs
# ---------------------------------------------------------------------------

CID_GAME_OBJECT = 1
CID_TRANSFORM = 4
CID_MESH_RENDERER = 23
CID_MESH_FILTER = 33
CID_BOX_COLLIDER = 65
CID_AUDIO_SOURCE = 82
CID_ANIMATOR = 95
CID_LIGHT = 108
CID_SPHERE_COLLIDER = 135
CID_CAPSULE_COLLIDER = 136
CID_MESH_COLLIDER = 64
CID_RIGIDBODY = 54
CID_CHARACTER_CONTROLLER = 143
CID_SKINNED_MESH_RENDERER = 137
CID_MONO_BEHAVIOUR = 114
CID_PARTICLE_SYSTEM = 198
CID_RECT_TRANSFORM = 224
CID_PREFAB_INSTANCE = 1001


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_vec3(d: dict, key: str) -> tuple[float, float, float]:
    """Extract a Vector3 (x, y, z) from a Unity YAML dict."""
    v = d.get(key, {})
    if not isinstance(v, dict):
        return (0.0, 0.0, 0.0)
    return (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))


def extract_quat(d: dict, key: str) -> tuple[float, float, float, float]:
    """Extract a Quaternion (x, y, z, w) from a Unity YAML dict."""
    v = d.get(key, {})
    if not isinstance(v, dict):
        return (0.0, 0.0, 0.0, 1.0)
    return (float(v.get("x", 0)), float(v.get("y", 0)),
            float(v.get("z", 0)), float(v.get("w", 1)))


def ref_file_id(ref: Any) -> str | None:
    """Extract fileID from a Unity object reference dict, or None."""
    if isinstance(ref, dict):
        fid = ref.get("fileID", 0)
        if fid:
            return str(fid)
    return None


def ref_guid(ref: Any) -> str | None:
    """Extract guid from a Unity object reference dict, or None."""
    if isinstance(ref, dict):
        guid = ref.get("guid", "")
        if guid and guid != "0" * 32:
            return guid
    return None


def parse_documents(raw_text: str) -> list[tuple[int, str, dict]]:
    """
    Parse a Unity YAML file into (classID, fileID, body_dict) triples.

    Pre-scans the document separators to capture classID and fileID before
    handing the cleaned text to PyYAML.
    """
    # Step 1: collect (classID, fileID) for every document separator
    doc_headers: list[tuple[int, str]] = []
    for m in UNITY_DOC_SEPARATOR.finditer(raw_text):
        doc_headers.append((int(m.group(1)), m.group(2)))

    # Step 2: strip the non-standard header and replace separators
    cleaned = UNITY_YAML_HEADER.sub("", raw_text, count=1)
    cleaned = UNITY_DOC_SEPARATOR.sub("---", cleaned)

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


def doc_body(doc: dict) -> dict:
    """
    Unity YAML documents are wrapped: ``{ClassName: {actual_props}}``.
    Return the inner dict.
    """
    for v in doc.values():
        if isinstance(v, dict):
            return v
    return doc
