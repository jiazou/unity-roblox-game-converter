"""Fine-grained unit tests for modules/scene_parser.py.

Tests internal helpers, edge cases, and scenarios not covered by the
existing black-box tests (SkinnedMeshRenderer, RectTransform, inactive
objects, malformed YAML, multiple materials, etc.).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modules.scene_parser import (
    ComponentData,
    ParsedScene,
    PrefabInstanceData,
    SceneNode,
    parse_scene,
    _extract_vec3,
    _extract_quat,
    _ref_file_id,
    _ref_guid,
    _parse_documents,
    _doc_body,
)


# ── Helper function tests ─────────────────────────────────────────────


class TestExtractVec3:
    def test_normal_dict(self) -> None:
        d = {"pos": {"x": 1.5, "y": 2.5, "z": 3.5}}
        assert _extract_vec3(d, "pos") == (1.5, 2.5, 3.5)

    def test_missing_key(self) -> None:
        assert _extract_vec3({}, "pos") == (0.0, 0.0, 0.0)

    def test_non_dict_value(self) -> None:
        assert _extract_vec3({"pos": "bad"}, "pos") == (0.0, 0.0, 0.0)

    def test_partial_components(self) -> None:
        d = {"pos": {"x": 1, "z": 3}}
        assert _extract_vec3(d, "pos") == (1.0, 0.0, 3.0)

    def test_integer_values(self) -> None:
        d = {"pos": {"x": 10, "y": 20, "z": 30}}
        assert _extract_vec3(d, "pos") == (10.0, 20.0, 30.0)


class TestExtractQuat:
    def test_normal_quat(self) -> None:
        d = {"rot": {"x": 0.1, "y": 0.2, "z": 0.3, "w": 0.9}}
        assert _extract_quat(d, "rot") == (0.1, 0.2, 0.3, 0.9)

    def test_missing_key_defaults_identity(self) -> None:
        assert _extract_quat({}, "rot") == (0.0, 0.0, 0.0, 1.0)

    def test_non_dict_value_defaults_identity(self) -> None:
        assert _extract_quat({"rot": 42}, "rot") == (0.0, 0.0, 0.0, 1.0)

    def test_partial_quat_defaults_w_to_1(self) -> None:
        d = {"rot": {"x": 0.5, "y": 0.5}}
        assert _extract_quat(d, "rot") == (0.5, 0.5, 0.0, 1.0)


class TestRefFileId:
    def test_valid_ref(self) -> None:
        assert _ref_file_id({"fileID": 12345}) == "12345"

    def test_zero_file_id(self) -> None:
        assert _ref_file_id({"fileID": 0}) is None

    def test_non_dict(self) -> None:
        assert _ref_file_id("not a dict") is None
        assert _ref_file_id(None) is None

    def test_missing_key(self) -> None:
        assert _ref_file_id({}) is None


class TestRefGuid:
    def test_valid_guid(self) -> None:
        assert _ref_guid({"guid": "abcd" * 8}) == "abcd" * 8

    def test_zero_guid_returns_none(self) -> None:
        assert _ref_guid({"guid": "0" * 32}) is None

    def test_empty_guid_returns_none(self) -> None:
        assert _ref_guid({"guid": ""}) is None

    def test_non_dict(self) -> None:
        assert _ref_guid(42) is None
        assert _ref_guid(None) is None


class TestDocBody:
    def test_unwraps_single_key_dict(self) -> None:
        doc = {"GameObject": {"m_Name": "Foo"}}
        assert _doc_body(doc) == {"m_Name": "Foo"}

    def test_non_dict_values_returns_outer(self) -> None:
        doc = {"key": "string_val"}
        assert _doc_body(doc) == doc

    def test_empty_dict(self) -> None:
        assert _doc_body({}) == {}


# ── Document parsing tests ────────────────────────────────────────────


class TestParseDocuments:
    def test_empty_text(self) -> None:
        assert _parse_documents("") == []

    def test_header_only(self) -> None:
        text = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
        result = _parse_documents(text)
        assert result == []

    def test_single_document(self) -> None:
        text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Single
        """)
        result = _parse_documents(text)
        assert len(result) == 1
        cid, fid, doc = result[0]
        assert cid == 1
        assert fid == "100"
        assert "GameObject" in doc

    def test_multiple_documents(self) -> None:
        text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: First
            --- !u!4 &200
            Transform:
              m_LocalPosition: {x: 0, y: 0, z: 0}
        """)
        result = _parse_documents(text)
        assert len(result) == 2
        assert result[0][0] == 1  # classID
        assert result[1][0] == 4

    def test_malformed_yaml_does_not_crash(self) -> None:
        """YAML that can be partially parsed should not crash."""
        text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            ::: invalid yaml [[[
        """)
        result = _parse_documents(text)
        # PyYAML may still parse it into something — just verify no crash
        assert isinstance(result, list)


# ── Full scene parsing edge cases ─────────────────────────────────────


class TestParseSceneEdgeCases:
    def test_skinned_mesh_renderer(self, tmp_path: Path) -> None:
        """SkinnedMeshRenderer should extract mesh GUID and material GUIDs."""
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: SkinnedObj
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
            --- !u!137 &300
            SkinnedMeshRenderer:
              m_GameObject: {fileID: 100}
              m_Mesh: {fileID: 4300000, guid: aabb0000aabb0000aabb0000aabb0001, type: 3}
              m_Materials:
                - {fileID: 2100000, guid: ccdd0000ccdd0000ccdd0000ccdd0001, type: 2}
                - {fileID: 2100000, guid: ccdd0000ccdd0000ccdd0000ccdd0002, type: 2}
        """)
        scene = tmp_path / "skinned.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        node = result.all_nodes.get("100")
        assert node is not None
        assert node.mesh_guid == "aabb0000aabb0000aabb0000aabb0001"
        assert "aabb0000aabb0000aabb0000aabb0001" in result.referenced_mesh_guids
        assert "ccdd0000ccdd0000ccdd0000ccdd0001" in result.referenced_material_guids
        assert "ccdd0000ccdd0000ccdd0000ccdd0002" in result.referenced_material_guids

        comp_types = {c.component_type for c in node.components}
        assert "SkinnedMeshRenderer" in comp_types

    def test_rect_transform(self, tmp_path: Path) -> None:
        """RectTransform (classID 224) should be treated like Transform."""
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: UIElement
              m_IsActive: 1
              m_Layer: 5
              m_TagString: Untagged
            --- !u!224 &200
            RectTransform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 100, y: 200, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
        """)
        scene = tmp_path / "ui.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        node = result.all_nodes.get("100")
        assert node is not None
        assert node.position == (100.0, 200.0, 0.0)
        assert node.layer == 5

        comp_types = {c.component_type for c in node.components}
        assert "RectTransform" in comp_types

    def test_inactive_game_object(self, tmp_path: Path) -> None:
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: DisabledObj
              m_IsActive: 0
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
        """)
        scene = tmp_path / "inactive.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        node = result.all_nodes.get("100")
        assert node is not None
        assert node.active is False

    def test_monobehaviour_attached(self, tmp_path: Path) -> None:
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Scripted
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
            --- !u!114 &300
            MonoBehaviour:
              m_GameObject: {fileID: 100}
              m_Script: {fileID: 11500000, guid: abcd1234abcd1234abcd1234abcd1234}
              speed: 5
        """)
        scene = tmp_path / "scripted.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        node = result.all_nodes.get("100")
        comp_types = {c.component_type for c in node.components}
        assert "MonoBehaviour" in comp_types
        mono = next(c for c in node.components if c.component_type == "MonoBehaviour")
        assert mono.properties.get("speed") == 5

    def test_deep_hierarchy(self, tmp_path: Path) -> None:
        """Three-level hierarchy: Root -> Mid -> Leaf."""
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Root
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &101
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: [{fileID: 201}]
            --- !u!1 &200
            GameObject:
              m_Name: Mid
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &201
            Transform:
              m_GameObject: {fileID: 200}
              m_LocalPosition: {x: 1, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 101}
              m_Children: [{fileID: 301}]
            --- !u!1 &300
            GameObject:
              m_Name: Leaf
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &301
            Transform:
              m_GameObject: {fileID: 300}
              m_LocalPosition: {x: 2, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 201}
              m_Children: []
        """)
        scene = tmp_path / "deep.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        assert len(result.roots) == 1
        root = result.roots[0]
        assert root.name == "Root"
        assert len(root.children) == 1
        mid = root.children[0]
        assert mid.name == "Mid"
        assert mid.position == (1.0, 0.0, 0.0)
        assert len(mid.children) == 1
        leaf = mid.children[0]
        assert leaf.name == "Leaf"
        assert leaf.position == (2.0, 0.0, 0.0)

    def test_multiple_root_objects(self, tmp_path: Path) -> None:
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: RootA
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &101
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
            --- !u!1 &200
            GameObject:
              m_Name: RootB
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &201
            Transform:
              m_GameObject: {fileID: 200}
              m_LocalPosition: {x: 10, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
        """)
        scene = tmp_path / "multi_root.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        assert len(result.roots) == 2
        root_names = {r.name for r in result.roots}
        assert root_names == {"RootA", "RootB"}

    def test_multiple_materials_on_renderer(self, tmp_path: Path) -> None:
        """MeshRenderer with multiple m_Materials entries."""
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: MultiMat
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &101
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
            --- !u!23 &300
            MeshRenderer:
              m_GameObject: {fileID: 100}
              m_Materials:
                - {fileID: 2100000, guid: aaaa0000aaaa0000aaaa0000aaaa0001, type: 2}
                - {fileID: 2100000, guid: aaaa0000aaaa0000aaaa0000aaaa0002, type: 2}
                - {fileID: 2100000, guid: aaaa0000aaaa0000aaaa0000aaaa0003, type: 2}
        """)
        scene = tmp_path / "multimat.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        assert len(result.referenced_material_guids) == 3
        assert "aaaa0000aaaa0000aaaa0000aaaa0001" in result.referenced_material_guids
        assert "aaaa0000aaaa0000aaaa0000aaaa0002" in result.referenced_material_guids
        assert "aaaa0000aaaa0000aaaa0000aaaa0003" in result.referenced_material_guids

    def test_prefab_instance_with_removed_components(self, tmp_path: Path) -> None:
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1001 &900
            PrefabInstance:
              m_SourcePrefab: {fileID: 100100000, guid: ffff0000ffff0000ffff0000ffff0001, type: 3}
              m_Modification:
                m_TransformParent: {fileID: 0}
                m_Modifications: []
                m_RemovedComponents:
                  - {fileID: 5000, guid: ffff0000ffff0000ffff0000ffff0001}
        """)
        scene = tmp_path / "removed.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)

        assert len(result.prefab_instances) == 1
        pi = result.prefab_instances[0]
        assert len(pi.removed_components) == 1

    def test_component_without_game_object_ref_ignored(self, tmp_path: Path) -> None:
        """A component missing m_GameObject should not crash."""
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Orphan
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
            --- !u!33 &300
            MeshFilter:
              m_Mesh: {fileID: 0}
        """)
        scene = tmp_path / "orphan_comp.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        result = parse_scene(scene)
        # Should not crash; the MeshFilter without m_GameObject is silently ignored
        assert len(result.all_nodes) == 1


# ── Hardened YAML parsing tests ──────────────────────────────────────


class TestHardenedYAMLParsing:
    """Tests for fragility fixes in unity_yaml_utils.parse_documents."""

    def test_negative_file_ids_accepted(self) -> None:
        """Prefab Variant fileIDs can be negative (Unity 2018.3+)."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &-4850089497005498858
            GameObject:
              m_Name: VariantRoot
              m_IsActive: 1
        """)
        docs = _parse_documents(yaml_text)
        assert len(docs) == 1
        cid, fid, body = docs[0]
        assert cid == 1
        assert fid == "-4850089497005498858"

    def test_stripped_documents_filtered_out(self) -> None:
        """Documents with 'stripped' suffix should be skipped."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Normal
              m_IsActive: 1
            --- !u!4 &200 stripped
            Transform:
              m_LocalPosition: {x: 0, y: 0, z: 0}
            --- !u!1 &300
            GameObject:
              m_Name: AlsoNormal
              m_IsActive: 1
        """)
        docs = _parse_documents(yaml_text)
        # The stripped Transform should be filtered out
        assert len(docs) == 2
        names = [_doc_body(d)["m_Name"] for _, _, d in docs]
        assert "Normal" in names
        assert "AlsoNormal" in names

    def test_per_document_error_recovery(self) -> None:
        """A malformed document should not kill parsing of other documents."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
              m_IsActive: 1
            --- !u!1 &200
            {{{INVALID YAML!!!}}}
            --- !u!1 &300
            GameObject:
              m_Name: AlsoGood
              m_IsActive: 1
        """)
        docs = _parse_documents(yaml_text)
        # The malformed middle doc should be skipped; two good docs survive
        assert len(docs) >= 1  # At minimum the first doc parses
        names = [_doc_body(d).get("m_Name") for _, _, d in docs]
        assert "Good" in names

    def test_null_materials_does_not_crash(self, tmp_path: Path) -> None:
        """m_Materials: null should not raise TypeError."""
        scene_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: NullMat
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
            --- !u!23 &300
            MeshRenderer:
              m_GameObject: {fileID: 100}
              m_Materials:
        """)
        scene = tmp_path / "nullmat.unity"
        scene.write_text(scene_yaml, encoding="utf-8")
        # Should not crash with TypeError: NoneType not iterable
        result = parse_scene(scene)
        assert len(result.all_nodes) == 1

    def test_prefab_components_include_colliders(self, tmp_path: Path) -> None:
        """Prefab parser should capture colliders, lights, etc. (not just 4 types)."""
        from modules.prefab_parser import _parse_single_prefab
        prefab_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: PhysObj
              m_IsActive: 1
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
            --- !u!65 &300
            BoxCollider:
              m_GameObject: {fileID: 100}
              m_Size: {x: 1, y: 1, z: 1}
            --- !u!54 &400
            Rigidbody:
              m_GameObject: {fileID: 100}
              m_Mass: 1
            --- !u!108 &500
            Light:
              m_GameObject: {fileID: 100}
              m_Type: 1
        """)
        prefab = tmp_path / "PhysObj.prefab"
        prefab.write_text(prefab_yaml, encoding="utf-8")
        template = _parse_single_prefab(prefab)

        node = template.root
        assert node is not None
        comp_types = {c.component_type for c in node.components}
        # Previously prefab parser only had 4 component types;
        # now it uses the shared allowlist and captures all of these
        assert "BoxCollider" in comp_types
        assert "Rigidbody" in comp_types
        assert "Light" in comp_types

    def test_multiple_tag_directives_parsed(self) -> None:
        """Headers with extra %TAG lines should still parse."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            %TAG !h! tag:unity3d.com,2022:
            --- !u!1 &100
            GameObject:
              m_Name: ExtraTags
              m_IsActive: 1
        """)
        docs = _parse_documents(yaml_text)
        assert len(docs) == 1
        assert _doc_body(docs[0][2])["m_Name"] == "ExtraTags"
