"""Tests for modules/unity_yaml_utils.py.

Covers Vector3/Quaternion extraction, Unity object reference parsing,
YAML document parsing, doc_body unwrapping, regex patterns, and
classID constant sanity checks.
"""

from __future__ import annotations

import textwrap

import pytest

from modules.unity_yaml_utils import (
    UNITY_YAML_HEADER,
    UNITY_DOC_SEPARATOR,
    CID_GAME_OBJECT,
    CID_TRANSFORM,
    CID_MESH_RENDERER,
    CID_MESH_FILTER,
    CID_MONO_BEHAVIOUR,
    CID_RECT_TRANSFORM,
    CID_PREFAB_INSTANCE,
    CID_LIGHT,
    CID_AUDIO_SOURCE,
    CID_PARTICLE_SYSTEM,
    extract_vec3,
    extract_quat,
    ref_file_id,
    ref_guid,
    parse_documents,
    doc_body,
)


# ---------------------------------------------------------------------------
# ClassID constants
# ---------------------------------------------------------------------------

class TestClassIDConstants:
    def test_well_known_ids(self) -> None:
        assert CID_GAME_OBJECT == 1
        assert CID_TRANSFORM == 4
        assert CID_MESH_RENDERER == 23
        assert CID_MESH_FILTER == 33
        assert CID_MONO_BEHAVIOUR == 114
        assert CID_RECT_TRANSFORM == 224
        assert CID_PREFAB_INSTANCE == 1001
        assert CID_LIGHT == 108
        assert CID_AUDIO_SOURCE == 82
        assert CID_PARTICLE_SYSTEM == 198

    def test_ids_are_unique(self) -> None:
        ids = [
            CID_GAME_OBJECT, CID_TRANSFORM, CID_MESH_RENDERER,
            CID_MESH_FILTER, CID_MONO_BEHAVIOUR, CID_RECT_TRANSFORM,
            CID_PREFAB_INSTANCE, CID_LIGHT, CID_AUDIO_SOURCE,
            CID_PARTICLE_SYSTEM,
        ]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

class TestRegexPatterns:
    def test_yaml_header_matches(self) -> None:
        text = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1 &100\n"
        match = UNITY_YAML_HEADER.search(text)
        assert match is not None

    def test_yaml_header_no_match(self) -> None:
        assert UNITY_YAML_HEADER.search("just plain text") is None

    def test_doc_separator_captures(self) -> None:
        line = "--- !u!42 &9999"
        match = UNITY_DOC_SEPARATOR.search(line)
        assert match is not None
        assert match.group(1) == "42"
        assert match.group(2) == "9999"

    def test_doc_separator_with_extra(self) -> None:
        line = "--- !u!1 &100 stripped"
        match = UNITY_DOC_SEPARATOR.search(line)
        assert match is not None
        assert match.group(1) == "1"
        assert match.group(2) == "100"


# ---------------------------------------------------------------------------
# extract_vec3
# ---------------------------------------------------------------------------

class TestExtractVec3:
    def test_normal(self) -> None:
        d = {"m_LocalPosition": {"x": 1.0, "y": 2.5, "z": -3.0}}
        assert extract_vec3(d, "m_LocalPosition") == (1.0, 2.5, -3.0)

    def test_integer_values(self) -> None:
        d = {"pos": {"x": 1, "y": 2, "z": 3}}
        assert extract_vec3(d, "pos") == (1.0, 2.0, 3.0)

    def test_missing_key(self) -> None:
        assert extract_vec3({}, "m_LocalPosition") == (0.0, 0.0, 0.0)

    def test_missing_components(self) -> None:
        d = {"pos": {"x": 5.0}}
        assert extract_vec3(d, "pos") == (5.0, 0.0, 0.0)

    def test_non_dict_value(self) -> None:
        d = {"pos": "invalid"}
        assert extract_vec3(d, "pos") == (0.0, 0.0, 0.0)

    def test_none_value(self) -> None:
        d = {"pos": None}
        assert extract_vec3(d, "pos") == (0.0, 0.0, 0.0)

    def test_zero_vector(self) -> None:
        d = {"pos": {"x": 0, "y": 0, "z": 0}}
        assert extract_vec3(d, "pos") == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# extract_quat
# ---------------------------------------------------------------------------

class TestExtractQuat:
    def test_identity(self) -> None:
        d = {"rot": {"x": 0, "y": 0, "z": 0, "w": 1}}
        assert extract_quat(d, "rot") == (0.0, 0.0, 0.0, 1.0)

    def test_rotation(self) -> None:
        d = {"rot": {"x": 0.0, "y": 0.707, "z": 0.0, "w": 0.707}}
        result = extract_quat(d, "rot")
        assert result == pytest.approx((0.0, 0.707, 0.0, 0.707))

    def test_missing_key(self) -> None:
        assert extract_quat({}, "rot") == (0.0, 0.0, 0.0, 1.0)

    def test_non_dict_value(self) -> None:
        d = {"rot": 42}
        assert extract_quat(d, "rot") == (0.0, 0.0, 0.0, 1.0)

    def test_missing_w_defaults_to_one(self) -> None:
        d = {"rot": {"x": 0.1, "y": 0.2, "z": 0.3}}
        assert extract_quat(d, "rot") == (0.1, 0.2, 0.3, 1.0)

    def test_missing_xyz_defaults_to_zero(self) -> None:
        d = {"rot": {"w": 0.5}}
        assert extract_quat(d, "rot") == (0.0, 0.0, 0.0, 0.5)


# ---------------------------------------------------------------------------
# ref_file_id
# ---------------------------------------------------------------------------

class TestRefFileId:
    def test_valid_ref(self) -> None:
        assert ref_file_id({"fileID": 12345}) == "12345"

    def test_zero_file_id(self) -> None:
        assert ref_file_id({"fileID": 0}) is None

    def test_missing_file_id(self) -> None:
        assert ref_file_id({}) is None

    def test_none_input(self) -> None:
        assert ref_file_id(None) is None

    def test_non_dict_input(self) -> None:
        assert ref_file_id("not a dict") is None
        assert ref_file_id(42) is None

    def test_string_file_id(self) -> None:
        assert ref_file_id({"fileID": "999"}) == "999"


# ---------------------------------------------------------------------------
# ref_guid
# ---------------------------------------------------------------------------

class TestRefGuid:
    def test_valid_guid(self) -> None:
        assert ref_guid({"guid": "abcdef1234567890abcdef1234567890"}) == "abcdef1234567890abcdef1234567890"

    def test_empty_guid(self) -> None:
        assert ref_guid({"guid": ""}) is None

    def test_zero_guid(self) -> None:
        assert ref_guid({"guid": "0" * 32}) is None

    def test_missing_guid(self) -> None:
        assert ref_guid({}) is None

    def test_none_input(self) -> None:
        assert ref_guid(None) is None

    def test_non_dict_input(self) -> None:
        assert ref_guid("not a dict") is None

    def test_short_guid(self) -> None:
        """Non-standard but valid — not all-zero, so should be returned."""
        assert ref_guid({"guid": "abc123"}) == "abc123"

    def test_guid_with_extra_fields(self) -> None:
        ref = {"fileID": 2800000, "guid": "aaa111bbb222ccc333ddd444eee555ff", "type": 3}
        assert ref_guid(ref) == "aaa111bbb222ccc333ddd444eee555ff"


# ---------------------------------------------------------------------------
# doc_body
# ---------------------------------------------------------------------------

class TestDocBody:
    def test_unwraps_standard_document(self) -> None:
        doc = {"GameObject": {"m_Name": "Cube", "m_IsActive": 1}}
        body = doc_body(doc)
        assert body == {"m_Name": "Cube", "m_IsActive": 1}

    def test_unwraps_transform(self) -> None:
        doc = {"Transform": {"m_LocalPosition": {"x": 0, "y": 0, "z": 0}}}
        body = doc_body(doc)
        assert "m_LocalPosition" in body

    def test_flat_dict_returned_as_is(self) -> None:
        doc = {"x": 1, "y": 2}
        assert doc_body(doc) == {"x": 1, "y": 2}

    def test_empty_dict(self) -> None:
        assert doc_body({}) == {}


# ---------------------------------------------------------------------------
# parse_documents
# ---------------------------------------------------------------------------

class TestParseDocuments:
    def test_single_document(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: TestObj
              m_IsActive: 1
        """)
        result = parse_documents(raw)
        assert len(result) == 1
        cid, fid, doc = result[0]
        assert cid == 1
        assert fid == "100"
        assert "GameObject" in doc

    def test_multiple_documents(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Obj1
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
            --- !u!33 &300
            MeshFilter:
              m_GameObject: {fileID: 100}
        """)
        result = parse_documents(raw)
        assert len(result) == 3
        assert result[0][0] == 1    # GameObject
        assert result[1][0] == 4    # Transform
        assert result[2][0] == 33   # MeshFilter

    def test_preserves_file_ids(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &999
            GameObject:
              m_Name: Test
            --- !u!4 &888
            Transform:
              m_GameObject: {fileID: 999}
        """)
        result = parse_documents(raw)
        assert result[0][1] == "999"
        assert result[1][1] == "888"

    def test_empty_input(self) -> None:
        assert parse_documents("") == []

    def test_invalid_yaml(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            {{{not valid yaml!!!
        """)
        assert parse_documents(raw) == []

    def test_no_header(self) -> None:
        """YAML without Unity header — separators still parsed."""
        raw = textwrap.dedent("""\
            --- !u!1 &100
            GameObject:
              m_Name: NoHeader
        """)
        result = parse_documents(raw)
        assert len(result) == 1
        assert result[0][0] == 1

    def test_prefab_instance_document(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1001 &5000
            PrefabInstance:
              m_SourcePrefab: {fileID: 100100000, guid: abcd1234, type: 3}
        """)
        result = parse_documents(raw)
        assert len(result) == 1
        assert result[0][0] == 1001
        assert result[0][1] == "5000"

    def test_large_file_ids(self) -> None:
        raw = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100100000
            GameObject:
              m_Name: BigId
        """)
        result = parse_documents(raw)
        assert result[0][1] == "100100000"
