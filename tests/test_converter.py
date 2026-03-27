"""Black-box integration tests for converter.py helper functions.

These tests exercise the internal wiring functions of the converter pipeline
via their public-facing effects. Since the converter CLI requires all modules
to be present, these tests validate the conversion helpers directly.
"""

from pathlib import Path

import pytest

from modules import (
    scene_parser,
    prefab_parser,
    guid_resolver,
    material_mapper,
    code_transpiler,
    mesh_decimator,
    rbxl_writer,
    report_generator,
)

# Import conversion helpers from the dedicated module
from modules.conversion_helpers import (
    node_to_part as _node_to_part,
    prefab_node_to_scene_node as _prefab_node_to_scene_node,
    apply_prefab_modifications as _apply_prefab_modifications,
    resolve_prefab_instances as _resolve_prefab_instances,
    scene_nodes_to_parts as _scene_nodes_to_parts,
    transpiled_to_rbx_scripts as _transpiled_to_rbx_scripts,
    build_report as _build_report,
)


def _snode(name: str = "Node", file_id: str = "100", **kwargs) -> scene_parser.SceneNode:
    """Shortcut to create a SceneNode with required fields filled in."""
    defaults = dict(active=True, layer=0, tag="Untagged")
    defaults.update(kwargs)
    return scene_parser.SceneNode(name=name, file_id=file_id, **defaults)


def _pnode(name: str = "PNode", file_id: str = "1000", **kwargs) -> prefab_parser.PrefabNode:
    """Shortcut to create a PrefabNode with required fields filled in."""
    defaults = dict(active=True)
    defaults.update(kwargs)
    return prefab_parser.PrefabNode(name=name, file_id=file_id, **defaults)


class TestNodeToPart:
    """Tests for _node_to_part conversion."""

    def test_basic_node(self) -> None:
        node = _snode(name="TestObj", position=(1.0, 2.0, 3.0))
        part = _node_to_part(node, None, None, None)
        assert isinstance(part, rbxl_writer.RbxPartEntry)
        assert part.name == "TestObj"
        assert part.position == (1.0, 2.0, 3.0)

    def test_children_recursive(self) -> None:
        child = _snode(name="Child", file_id="200")
        parent = _snode(name="Parent", file_id="100", children=[child])
        part = _node_to_part(parent, None, None, None)
        assert len(part.children) == 1
        assert part.children[0].name == "Child"

    def test_mesh_guid_resolved(self, unity_project: Path) -> None:
        guid_index = guid_resolver.build_guid_index(unity_project)
        mesh_guid = "dddd0000dddd0000dddd0000dddd0001"
        node = _snode(name="MeshObj", mesh_guid=mesh_guid)
        part = _node_to_part(node, None, None, guid_index)
        assert part.mesh_id is not None
        assert "cube" in part.mesh_id.lower()

    def test_mesh_path_remap(self, unity_project: Path) -> None:
        guid_index = guid_resolver.build_guid_index(unity_project)
        mesh_guid = "dddd0000dddd0000dddd0000dddd0001"
        original_path = str(guid_index.resolve(mesh_guid))
        node = _snode(name="RemappedMesh", mesh_guid=mesh_guid)
        remap = {original_path: "/new/path/mesh.obj"}
        part = _node_to_part(node, None, None, guid_index, mesh_path_remap=remap)
        assert part.mesh_id == "/new/path/mesh.obj"

    def test_anchored_by_default(self) -> None:
        node = _snode(name="Anch")
        part = _node_to_part(node, None, None, None)
        assert part.anchored is True

    def test_no_mesh_guid_no_mesh_id(self) -> None:
        node = _snode(name="NoMesh")
        part = _node_to_part(node, None, None, None)
        assert part.mesh_id is None


class TestPrefabNodeToSceneNode:
    """Tests for _prefab_node_to_scene_node."""

    def test_basic_conversion(self) -> None:
        pnode = _pnode(
            name="PrefabRoot",
            position=(5.0, 10.0, 15.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            scale=(2.0, 2.0, 2.0),
        )
        snode = _prefab_node_to_scene_node(pnode)
        assert isinstance(snode, scene_parser.SceneNode)
        assert snode.name == "PrefabRoot"
        assert snode.position == (5.0, 10.0, 15.0)
        assert snode.scale == (2.0, 2.0, 2.0)
        assert snode.from_prefab_instance is True

    def test_children_converted(self) -> None:
        child = _pnode(name="Child", file_id="2000")
        parent = _pnode(name="Root", file_id="1000", children=[child])
        snode = _prefab_node_to_scene_node(parent)
        assert len(snode.children) == 1
        assert snode.children[0].name == "Child"
        assert snode.children[0].from_prefab_instance is True

    def test_components_copied(self) -> None:
        comp = prefab_parser.PrefabComponent(
            component_type="MeshFilter",
            file_id="5000",
            properties={"m_Mesh": {"guid": "abc123"}},
        )
        pnode = _pnode(name="WithComp", components=[comp])
        snode = _prefab_node_to_scene_node(pnode)
        assert len(snode.components) == 1
        assert snode.components[0].component_type == "MeshFilter"

    def test_mesh_guid_preserved(self) -> None:
        pnode = _pnode(
            name="MeshPrefab",
            mesh_guid="aaaa1111aaaa1111aaaa1111aaaa1111",
        )
        snode = _prefab_node_to_scene_node(pnode)
        assert snode.mesh_guid == "aaaa1111aaaa1111aaaa1111aaaa1111"


class TestApplyPrefabModifications:
    """Tests for _apply_prefab_modifications."""

    def _make_node(self, name: str = "Root", file_id: str = "1000") -> scene_parser.SceneNode:
        return _snode(
            name=name,
            file_id=file_id,
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            scale=(1.0, 1.0, 1.0),
        )

    def test_position_override_x(self) -> None:
        node = self._make_node()
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.x", "value": "42.5"}]
        _apply_prefab_modifications(node, mods)
        assert node.position[0] == 42.5

    def test_position_override_y(self) -> None:
        node = self._make_node()
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.y", "value": "10.0"}]
        _apply_prefab_modifications(node, mods)
        assert node.position[1] == 10.0

    def test_position_override_z(self) -> None:
        node = self._make_node()
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.z", "value": "-5.0"}]
        _apply_prefab_modifications(node, mods)
        assert node.position[2] == -5.0

    def test_rotation_override(self) -> None:
        node = self._make_node()
        mods = [
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalRotation.x", "value": "0.1"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalRotation.y", "value": "0.2"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalRotation.z", "value": "0.3"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalRotation.w", "value": "0.9"},
        ]
        _apply_prefab_modifications(node, mods)
        assert node.rotation == (0.1, 0.2, 0.3, 0.9)

    def test_scale_override(self) -> None:
        node = self._make_node()
        mods = [
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalScale.x", "value": "3.0"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalScale.y", "value": "4.0"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalScale.z", "value": "5.0"},
        ]
        _apply_prefab_modifications(node, mods)
        assert node.scale == (3.0, 4.0, 5.0)

    def test_name_override(self) -> None:
        node = self._make_node()
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_Name", "value": "NewName"}]
        _apply_prefab_modifications(node, mods)
        assert node.name == "NewName"

    def test_active_state_override(self) -> None:
        node = self._make_node()
        node.active = True
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_IsActive", "value": "0"}]
        _apply_prefab_modifications(node, mods)
        assert node.active is False

    def test_child_node_targeted(self) -> None:
        child = _snode(
            name="Child", file_id="2000",
            position=(0.0, 0.0, 0.0),
        )
        parent = self._make_node()
        parent.children.append(child)
        mods = [{"target": {"fileID": "2000"}, "propertyPath": "m_LocalPosition.x", "value": "99.0"}]
        _apply_prefab_modifications(parent, mods)
        assert parent.children[0].position[0] == 99.0

    def test_unknown_target_ignored(self) -> None:
        node = self._make_node()
        mods = [{"target": {"fileID": "9999"}, "propertyPath": "m_Name", "value": "Ghost"}]
        _apply_prefab_modifications(node, mods)
        assert node.name == "Root"  # unchanged

    def test_empty_modifications(self) -> None:
        node = self._make_node()
        _apply_prefab_modifications(node, [])
        assert node.position == (0.0, 0.0, 0.0)

    def test_invalid_mod_entries_skipped(self) -> None:
        node = self._make_node()
        mods = [None, "bad", 42, {"target": {"fileID": "1000"}, "propertyPath": "m_Name", "value": "Valid"}]
        _apply_prefab_modifications(node, mods)
        assert node.name == "Valid"


class TestSceneNodesToParts:
    """Tests for _scene_nodes_to_parts."""

    def test_empty_scenes(self) -> None:
        parts, lighting, cam, sky, comp_warnings = _scene_nodes_to_parts([])
        assert parts == []
        assert lighting is None
        assert cam is None
        assert sky is None
        assert comp_warnings == []

    def test_single_root_node(self) -> None:
        node = _snode(name="Root")
        scene = scene_parser.ParsedScene(
            scene_path=Path("/fake/scene.unity"),
            roots=[node],
        )
        parts, *_ = _scene_nodes_to_parts([scene])
        assert len(parts) == 1
        assert parts[0].name == "Root"

    def test_multiple_scenes(self) -> None:
        node1 = _snode(name="A", file_id="100")
        node2 = _snode(name="B", file_id="200")
        s1 = scene_parser.ParsedScene(scene_path=Path("/s1.unity"), roots=[node1])
        s2 = scene_parser.ParsedScene(scene_path=Path("/s2.unity"), roots=[node2])
        parts, *_ = _scene_nodes_to_parts([s1, s2])
        assert len(parts) == 2

    def test_hierarchy_preserved(self) -> None:
        child = _snode(name="Child", file_id="200")
        parent = _snode(name="Parent", file_id="100", children=[child])
        scene = scene_parser.ParsedScene(scene_path=Path("/s.unity"), roots=[parent])
        parts, *_ = _scene_nodes_to_parts([scene])
        assert len(parts[0].children) == 1
        assert parts[0].children[0].name == "Child"

    def test_unconverted_components_produce_warnings(self) -> None:
        node = _snode(name="Enemy", components=[
            scene_parser.ComponentData("Animator", "1", {}),
            scene_parser.ComponentData("NavMeshAgent", "2", {}),
            scene_parser.ComponentData("MeshRenderer", "3", {}),
        ])
        scene = scene_parser.ParsedScene(scene_path=Path("/s.unity"), roots=[node])
        parts, _, _, _, comp_warnings = _scene_nodes_to_parts([scene])
        assert len(parts) == 1
        warning_types = {w.component_type for w in comp_warnings}
        assert "Animator" not in warning_types  # now converted via AnimatorBridge
        assert "NavMeshAgent" in warning_types
        assert "MeshRenderer" not in warning_types  # converted, not warned

    def test_no_warnings_for_converted_components(self) -> None:
        node = _snode(name="Cube", components=[
            scene_parser.ComponentData("MeshFilter", "1", {}),
            scene_parser.ComponentData("MeshRenderer", "2", {}),
            scene_parser.ComponentData("BoxCollider", "3", {}),
        ])
        scene = scene_parser.ParsedScene(scene_path=Path("/s.unity"), roots=[node])
        _, _, _, _, comp_warnings = _scene_nodes_to_parts([scene])
        assert comp_warnings == []


class TestTranspiledToRbxScripts:
    """Tests for _transpiled_to_rbx_scripts."""

    def test_empty_result(self) -> None:
        result = code_transpiler.TranspilationResult()
        entries = _transpiled_to_rbx_scripts(result)
        assert entries == []

    def test_scripts_converted(self) -> None:
        ts = code_transpiler.TranspiledScript(
            source_path=Path("/src/Test.cs"),
            output_filename="Test.lua",
            csharp_source="void Start() {}",
            luau_source="-- test",
            strategy="ai",
            confidence=0.8,
        )
        result = code_transpiler.TranspilationResult(scripts=[ts], total=1, succeeded=1)
        entries = _transpiled_to_rbx_scripts(result)
        assert len(entries) == 1
        assert entries[0].name == "Test"
        assert entries[0].luau_source == "-- test"

    def test_lua_extension_stripped(self) -> None:
        ts = code_transpiler.TranspiledScript(
            source_path=Path("/src/Foo.cs"),
            output_filename="Foo.lua",
            csharp_source="",
            luau_source="",
            strategy="ai",
            confidence=0.5,
        )
        result = code_transpiler.TranspilationResult(scripts=[ts])
        entries = _transpiled_to_rbx_scripts(result)
        assert ".lua" not in entries[0].name


class TestBuildReport:
    """Tests for _build_report."""

    def _make_empty_inputs(self, tmp_path: Path):
        """Create minimal empty pipeline outputs for _build_report."""
        from modules.asset_extractor import AssetManifest
        unity_path = tmp_path / "Project"
        unity_path.mkdir()
        return dict(
            unity_path=unity_path,
            output_dir=tmp_path / "out",
            manifest=AssetManifest(unity_project_path=unity_path),
            mat_result=material_mapper.MaterialMapResult(),
            scenes=[],
            prefabs=prefab_parser.PrefabLibrary(),
            transpilation=code_transpiler.TranspilationResult(),
            write_result=rbxl_writer.RbxWriteResult(
                output_path=tmp_path / "out" / "game.rbxl",
                parts_written=0,
                scripts_written=0,
            ),
            decimation=mesh_decimator.DecimationResult(),
            prefab_instances_resolved=0,
            duration=1.5,
            errors=[],
        )

    def test_returns_conversion_report(self, tmp_path: Path) -> None:
        inputs = self._make_empty_inputs(tmp_path)
        rpt = _build_report(**inputs)
        assert isinstance(rpt, report_generator.ConversionReport)

    def test_success_when_no_errors(self, tmp_path: Path) -> None:
        inputs = self._make_empty_inputs(tmp_path)
        rpt = _build_report(**inputs)
        assert rpt.success is True

    def test_failure_when_errors(self, tmp_path: Path) -> None:
        inputs = self._make_empty_inputs(tmp_path)
        inputs["errors"] = ["something failed"]
        rpt = _build_report(**inputs)
        assert rpt.success is False

    def test_duration_recorded(self, tmp_path: Path) -> None:
        inputs = self._make_empty_inputs(tmp_path)
        inputs["duration"] = 42.7
        rpt = _build_report(**inputs)
        assert rpt.duration_seconds == 42.7

    def test_prefab_instances_recorded(self, tmp_path: Path) -> None:
        inputs = self._make_empty_inputs(tmp_path)
        inputs["prefab_instances_resolved"] = 5
        rpt = _build_report(**inputs)
        assert rpt.scene.prefab_instances_resolved == 5

    def test_decimation_stats_recorded(self, tmp_path: Path) -> None:
        inputs = self._make_empty_inputs(tmp_path)
        inputs["decimation"] = mesh_decimator.DecimationResult(
            decimated=3, already_compliant=7, total_meshes=10,
        )
        rpt = _build_report(**inputs)
        assert rpt.scene.meshes_decimated == 3
        assert rpt.scene.meshes_compliant == 7


class TestResolvePrefabInstances:
    """Tests for _resolve_prefab_instances."""

    def test_no_instances_returns_zero(self) -> None:
        scene = scene_parser.ParsedScene(scene_path=Path("/s.unity"), roots=[])
        lib = prefab_parser.PrefabLibrary()
        idx = guid_resolver.GuidIndex(project_root=Path("/fake"))
        result = _resolve_prefab_instances([scene], lib, idx)
        assert result == 0

    def test_resolves_with_matching_prefab(self, unity_project_with_prefab_instance: Path) -> None:
        """Full integration: parse scene with PrefabInstance and resolve it."""
        project = unity_project_with_prefab_instance
        guid_index = guid_resolver.build_guid_index(project)

        # Parse the scene that has a PrefabInstance
        prefab_scene_path = project / "Assets" / "PrefabScene.unity"
        parsed = scene_parser.parse_scene(prefab_scene_path)

        # Parse prefabs
        prefab_lib = prefab_parser.parse_prefabs(project)

        count = _resolve_prefab_instances([parsed], prefab_lib, guid_index)
        # Should resolve at least the one PrefabInstance in the scene
        assert count >= 1
        # The resolved prefab nodes should appear in the scene roots or as children
        all_names = set()
        def _collect(node):
            all_names.add(node.name)
            for c in node.children:
                _collect(c)
        for r in parsed.roots:
            _collect(r)
        # Either "PrefabRoot" or "OverriddenName" (from modification)
        assert "OverriddenName" in all_names or "PrefabRoot" in all_names
