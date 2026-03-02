"""Fine-grained unit tests for modules/prefab_parser.py.

Covers multi-root prefabs, RectTransform nodes, missing fields,
deeply nested hierarchies, and other edge cases.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modules.prefab_parser import (
    PrefabComponent,
    PrefabLibrary,
    PrefabNode,
    PrefabTemplate,
    parse_prefabs,
    _extract_vec3,
    _extract_quat,
    _ref_file_id,
    _ref_guid,
    _doc_body,
    _parse_documents,
    _parse_single_prefab,
)
from tests.conftest import make_meta


class TestPrefabHelpers:
    """Verify that local duplicated helpers work identically to scene_parser's."""

    def test_extract_vec3(self) -> None:
        assert _extract_vec3({"v": {"x": 1, "y": 2, "z": 3}}, "v") == (1.0, 2.0, 3.0)
        assert _extract_vec3({}, "v") == (0.0, 0.0, 0.0)

    def test_extract_quat(self) -> None:
        assert _extract_quat({"q": {"x": 0, "y": 0, "z": 0, "w": 1}}, "q") == (0.0, 0.0, 0.0, 1.0)
        assert _extract_quat({}, "q") == (0.0, 0.0, 0.0, 1.0)

    def test_ref_file_id(self) -> None:
        assert _ref_file_id({"fileID": 5}) == "5"
        assert _ref_file_id({"fileID": 0}) is None
        assert _ref_file_id(None) is None

    def test_ref_guid(self) -> None:
        assert _ref_guid({"guid": "a" * 32}) == "a" * 32
        assert _ref_guid({"guid": "0" * 32}) is None

    def test_doc_body(self) -> None:
        assert _doc_body({"Transform": {"x": 1}}) == {"x": 1}


class TestParseSinglePrefab:
    """Tests for internal _parse_single_prefab function."""

    def test_single_node_prefab(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Solo
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
        """)
        prefab = tmp_path / "Solo.prefab"
        prefab.write_text(yaml_text, encoding="utf-8")
        tmpl = _parse_single_prefab(prefab)

        assert tmpl.name == "Solo"
        assert tmpl.root is not None
        assert tmpl.root.name == "Solo"
        assert len(tmpl.all_nodes) == 1
        assert tmpl.root.children == []

    def test_rect_transform_in_prefab(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: UIButton
              m_IsActive: 1
              m_Layer: 5
              m_TagString: Untagged
            --- !u!224 &200
            RectTransform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 50, y: 100, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
        """)
        prefab = tmp_path / "UIButton.prefab"
        prefab.write_text(yaml_text, encoding="utf-8")
        tmpl = _parse_single_prefab(prefab)

        assert tmpl.root is not None
        assert tmpl.root.position == (50.0, 100.0, 0.0)
        comp_types = {c.component_type for c in tmpl.root.components}
        assert "RectTransform" in comp_types

    def test_skinned_mesh_renderer_in_prefab(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Character
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
            --- !u!137 &300
            SkinnedMeshRenderer:
              m_GameObject: {fileID: 100}
              m_Mesh: {fileID: 4300000, guid: skinmeshguid000skinmeshguid0001, type: 3}
              m_Materials:
                - {fileID: 2100000, guid: skinmatguid0000skinmatguid00001, type: 2}
        """)
        prefab = tmp_path / "Character.prefab"
        prefab.write_text(yaml_text, encoding="utf-8")
        tmpl = _parse_single_prefab(prefab)

        assert tmpl.root is not None
        assert tmpl.root.mesh_guid == "skinmeshguid000skinmeshguid0001"
        assert "skinmeshguid000skinmeshguid0001" in tmpl.referenced_mesh_guids
        assert "skinmatguid0000skinmatguid00001" in tmpl.referenced_material_guids

    def test_deep_hierarchy(self, tmp_path: Path) -> None:
        """Three-level prefab: A -> B -> C."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: A
              m_IsActive: 1
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
              m_Name: B
              m_IsActive: 1
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
              m_Name: C
              m_IsActive: 1
            --- !u!4 &301
            Transform:
              m_GameObject: {fileID: 300}
              m_LocalPosition: {x: 2, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 201}
        """)
        prefab = tmp_path / "Deep.prefab"
        prefab.write_text(yaml_text, encoding="utf-8")
        tmpl = _parse_single_prefab(prefab)

        assert tmpl.root is not None
        assert tmpl.root.name == "A"
        assert len(tmpl.root.children) == 1
        b = tmpl.root.children[0]
        assert b.name == "B"
        assert b.position == (1.0, 0.0, 0.0)
        assert len(b.children) == 1
        c = b.children[0]
        assert c.name == "C"
        assert c.position == (2.0, 0.0, 0.0)

    def test_inactive_node(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Hidden
              m_IsActive: 0
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
        """)
        prefab = tmp_path / "Hidden.prefab"
        prefab.write_text(yaml_text, encoding="utf-8")
        tmpl = _parse_single_prefab(prefab)

        assert tmpl.root.active is False


class TestParsePrefabsDiscovery:
    """Tests for parse_prefabs directory walking and library construction."""

    def test_multiple_prefabs(self, tmp_path: Path) -> None:
        project = tmp_path / "Multi"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        for name in ("Alpha", "Beta", "Gamma"):
            yaml_text = textwrap.dedent(f"""\
                %YAML 1.1
                %TAG !u! tag:unity3d.com,2011:
                --- !u!1 &100
                GameObject:
                  m_Name: {name}
                  m_IsActive: 1
                --- !u!4 &200
                Transform:
                  m_GameObject: {{fileID: 100}}
                  m_LocalPosition: {{x: 0, y: 0, z: 0}}
                  m_LocalRotation: {{x: 0, y: 0, z: 0, w: 1}}
                  m_LocalScale: {{x: 1, y: 1, z: 1}}
                  m_Father: {{fileID: 0}}
            """)
            (assets / f"{name}.prefab").write_text(yaml_text, encoding="utf-8")

        lib = parse_prefabs(project)
        assert len(lib.prefabs) == 3
        assert set(lib.by_name.keys()) == {"Alpha", "Beta", "Gamma"}

    def test_nested_directory_prefabs(self, tmp_path: Path) -> None:
        project = tmp_path / "Nested"
        subdir = project / "Assets" / "Prefabs" / "Enemies"
        subdir.mkdir(parents=True)

        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: DeepEnemy
              m_IsActive: 1
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
        """)
        (subdir / "DeepEnemy.prefab").write_text(yaml_text, encoding="utf-8")

        lib = parse_prefabs(project)
        assert len(lib.prefabs) == 1
        assert "DeepEnemy" in lib.by_name

    def test_malformed_prefab_skipped(self, tmp_path: Path) -> None:
        """A prefab with invalid YAML should be skipped, not crash."""
        project = tmp_path / "BadPrefab"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        (assets / "Bad.prefab").write_text("::: invalid [[[", encoding="utf-8")

        good_yaml = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Good
              m_IsActive: 1
            --- !u!4 &200
            Transform:
              m_GameObject: {fileID: 100}
              m_LocalPosition: {x: 0, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
        """)
        (assets / "Good.prefab").write_text(good_yaml, encoding="utf-8")

        lib = parse_prefabs(project)
        # Good prefab should still be parsed; bad one skipped
        assert len(lib.prefabs) >= 1
        assert "Good" in lib.by_name
