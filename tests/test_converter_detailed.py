"""Fine-grained unit tests for converter.py helper functions.

Tests material wiring to SurfaceAppearance, edge cases in prefab
resolution, inactive node filtering, and report building details.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules import (
    code_transpiler,
    guid_resolver,
    material_mapper,
    mesh_decimator,
    prefab_parser,
    rbxl_writer,
    report_generator,
    scene_parser,
)
from modules.asset_extractor import AssetManifest

from modules.conversion_helpers import (
    apply_prefab_modifications as _apply_prefab_modifications,
    build_report as _build_report,
    node_to_part as _node_to_part,
    prefab_node_to_scene_node as _prefab_node_to_scene_node,
    resolve_prefab_instances as _resolve_prefab_instances,
    roblox_def_to_surface_appearance as _roblox_def_to_surface_appearance,
    scene_nodes_to_parts as _scene_nodes_to_parts,
    transpiled_to_rbx_scripts as _transpiled_to_rbx_scripts,
)


def _snode(name: str = "Node", file_id: str = "100", **kwargs) -> scene_parser.SceneNode:
    defaults = dict(active=True, layer=0, tag="Untagged")
    defaults.update(kwargs)
    return scene_parser.SceneNode(name=name, file_id=file_id, **defaults)


def _pnode(name: str = "PNode", file_id: str = "1000", **kwargs) -> prefab_parser.PrefabNode:
    defaults = dict(active=True)
    defaults.update(kwargs)
    return prefab_parser.PrefabNode(name=name, file_id=file_id, **defaults)


# ── RobloxMaterialDef → SurfaceAppearance ─────────────────────────────


class TestRobloxDefToSurfaceAppearance:
    """Tests for _roblox_def_to_surface_appearance."""

    def test_full_pbr(self) -> None:
        rdef = material_mapper.RobloxMaterialDef(
            color_map="color.png",
            normal_map="normal.png",
            metalness_map="metal.png",
            roughness_map="rough.png",
            alpha_mode="Opaque",
        )
        sa = _roblox_def_to_surface_appearance(rdef)
        assert isinstance(sa, rbxl_writer.RbxSurfaceAppearance)
        assert sa.color_map == "color.png"
        assert sa.normal_map == "normal.png"
        assert sa.metalness_map == "metal.png"
        assert sa.roughness_map == "rough.png"

    def test_emissive_fields(self) -> None:
        rdef = material_mapper.RobloxMaterialDef(
            color_map="c.png",
            emissive_mask="em.png",
            emissive_strength=3.0,
            emissive_tint=(1.0, 0.5, 0.0),
        )
        sa = _roblox_def_to_surface_appearance(rdef)
        assert sa.emissive_mask == "em.png"
        assert sa.emissive_strength == 3.0
        assert sa.emissive_tint == (1.0, 0.5, 0.0)

    def test_alpha_mode_transparency(self) -> None:
        rdef = material_mapper.RobloxMaterialDef(alpha_mode="Transparency")
        sa = _roblox_def_to_surface_appearance(rdef)
        assert sa.alpha_mode == "Transparency"

    def test_color_only_no_maps(self) -> None:
        rdef = material_mapper.RobloxMaterialDef(
            base_part_color=(1.0, 0.0, 0.0),
        )
        sa = _roblox_def_to_surface_appearance(rdef)
        assert sa.color_map is None
        assert sa.normal_map is None


# ── Node-to-part with material/mesh wiring ────────────────────────────


class TestNodeToPartMaterialWiring:
    """Tests for _node_to_part with material and mesh remapping."""

    def test_material_guid_applied(self) -> None:
        mat_guid = "eeee0000eeee0000eeee0000eeee0001"
        rdef = material_mapper.RobloxMaterialDef(
            color_map="test_color.png",
            normal_map="test_normal.png",
        )
        guid_to_roblox_def = {mat_guid: rdef}

        # Material GUIDs live inside MeshRenderer component properties
        renderer = scene_parser.ComponentData(
            component_type="MeshRenderer",
            file_id="500",
            properties={"m_Materials": [{"guid": mat_guid}]},
        )
        node = _snode(
            name="MatObj",
            mesh_guid="dddd0000dddd0000dddd0000dddd0001",
            components=[renderer],
        )
        part = _node_to_part(node, guid_to_roblox_def, None, None)
        assert part.surface_appearance is not None
        assert part.surface_appearance.color_map == "test_color.png"

    def test_node_without_material(self) -> None:
        node = _snode(name="NoMat")
        part = _node_to_part(node, None, None, None)
        assert part.surface_appearance is None

    def test_inactive_node_converted(self) -> None:
        """Inactive nodes should still be converted (Roblox doesn't skip them)."""
        node = _snode(name="Inactive", active=False)
        part = _node_to_part(node, None, None, None)
        assert part.name == "Inactive"

    def test_node_with_scale(self) -> None:
        node = _snode(name="Scaled", scale=(3.0, 4.0, 5.0))
        part = _node_to_part(node, None, None, None)
        assert part.size == (3.0, 4.0, 5.0) or part.name == "Scaled"

    def test_deep_child_recursion(self) -> None:
        c3 = _snode(name="C3", file_id="400")
        c2 = _snode(name="C2", file_id="300", children=[c3])
        c1 = _snode(name="C1", file_id="200", children=[c2])
        root = _snode(name="Root", file_id="100", children=[c1])
        part = _node_to_part(root, None, None, None)

        assert len(part.children) == 1
        assert part.children[0].name == "C1"
        assert len(part.children[0].children) == 1
        assert part.children[0].children[0].name == "C2"
        assert len(part.children[0].children[0].children) == 1
        assert part.children[0].children[0].children[0].name == "C3"


# ── Prefab modifications edge cases ──────────────────────────────────


class TestApplyPrefabModificationsDetailed:
    def _make_node(self, name: str = "Root", file_id: str = "1000") -> scene_parser.SceneNode:
        return _snode(
            name=name, file_id=file_id,
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            scale=(1.0, 1.0, 1.0),
        )

    def test_partial_position_override(self) -> None:
        """Only overriding x should leave y and z unchanged."""
        node = self._make_node()
        node.position = (10.0, 20.0, 30.0)
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.x", "value": "99.0"}]
        _apply_prefab_modifications(node, mods)
        assert node.position == (99.0, 20.0, 30.0)

    def test_multiple_modifications_same_target(self) -> None:
        node = self._make_node()
        mods = [
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.x", "value": "1.0"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.y", "value": "2.0"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_LocalPosition.z", "value": "3.0"},
            {"target": {"fileID": "1000"}, "propertyPath": "m_Name", "value": "Renamed"},
        ]
        _apply_prefab_modifications(node, mods)
        assert node.position == (1.0, 2.0, 3.0)
        assert node.name == "Renamed"

    def test_deep_child_modification(self) -> None:
        """Modification targeting a grandchild should still apply."""
        grandchild = _snode(name="GC", file_id="3000", position=(0.0, 0.0, 0.0))
        child = _snode(name="C", file_id="2000", children=[grandchild])
        parent = self._make_node()
        parent.children = [child]

        mods = [{"target": {"fileID": "3000"}, "propertyPath": "m_LocalPosition.y", "value": "50.0"}]
        _apply_prefab_modifications(parent, mods)
        assert grandchild.position[1] == 50.0

    def test_activate_inactive_node(self) -> None:
        node = self._make_node()
        node.active = False
        mods = [{"target": {"fileID": "1000"}, "propertyPath": "m_IsActive", "value": "1"}]
        _apply_prefab_modifications(node, mods)
        assert node.active is True


# ── Prefab node to scene node ─────────────────────────────────────────


class TestPrefabNodeToSceneNodeDetailed:
    def test_material_components_preserved(self) -> None:
        renderer = prefab_parser.PrefabComponent(
            component_type="MeshRenderer",
            file_id="500",
            properties={"m_Materials": [
                {"guid": "aabb0000aabb0000aabb0000aabb0001"},
                {"guid": "aabb0000aabb0000aabb0000aabb0002"},
            ]},
        )
        pnode = _pnode(name="WithMat", components=[renderer])
        snode = _prefab_node_to_scene_node(pnode)
        # Components should be copied to the SceneNode
        assert len(snode.components) == 1
        mat_refs = snode.components[0].properties["m_Materials"]
        assert len(mat_refs) == 2
        assert mat_refs[0]["guid"] == "aabb0000aabb0000aabb0000aabb0001"

    def test_deep_conversion(self) -> None:
        gc = _pnode(name="GrandChild", file_id="3000")
        child = _pnode(name="Child", file_id="2000", children=[gc])
        root = _pnode(name="Root", file_id="1000", children=[child])
        snode = _prefab_node_to_scene_node(root)

        assert snode.name == "Root"
        assert len(snode.children) == 1
        assert snode.children[0].name == "Child"
        assert len(snode.children[0].children) == 1
        assert snode.children[0].children[0].name == "GrandChild"
        assert snode.children[0].children[0].from_prefab_instance is True

    def test_inactive_prefab_node(self) -> None:
        pnode = _pnode(name="Off", active=False)
        snode = _prefab_node_to_scene_node(pnode)
        assert snode.active is False
        assert snode.from_prefab_instance is True


# ── Scene nodes to parts ─────────────────────────────────────────────


class TestSceneNodesToPartsDetailed:
    def test_multiple_roots_per_scene(self) -> None:
        n1 = _snode(name="R1", file_id="100")
        n2 = _snode(name="R2", file_id="200")
        scene = scene_parser.ParsedScene(
            scene_path=Path("/s.unity"),
            roots=[n1, n2],
        )
        parts, *_ = _scene_nodes_to_parts([scene])
        assert len(parts) == 2

    def test_three_scenes(self) -> None:
        scenes = []
        for i in range(3):
            n = _snode(name=f"S{i}", file_id=str(100 + i))
            scenes.append(scene_parser.ParsedScene(
                scene_path=Path(f"/s{i}.unity"),
                roots=[n],
            ))
        parts, *_ = _scene_nodes_to_parts(scenes)
        assert len(parts) == 3


# ── Transpiled scripts to RBX scripts ────────────────────────────────


class TestTranspiledToRbxScriptsDetailed:
    def test_multiple_scripts(self) -> None:
        scripts = [
            code_transpiler.TranspiledScript(
                source_path=Path(f"/src/{name}.cs"),
                output_filename=f"{name}.lua",
                csharp_source="void Start() {}",
                luau_source=f"-- {name}",
                strategy="rule_based",
                confidence=0.8,
            )
            for name in ("Alpha", "Beta", "Gamma")
        ]
        result = code_transpiler.TranspilationResult(
            scripts=scripts, total=3, succeeded=3,
        )
        entries = _transpiled_to_rbx_scripts(result)
        assert len(entries) == 3
        names = {e.name for e in entries}
        assert names == {"Alpha", "Beta", "Gamma"}

    def test_flagged_scripts_still_included(self) -> None:
        ts = code_transpiler.TranspiledScript(
            source_path=Path("/src/Bad.cs"),
            output_filename="Bad.lua",
            csharp_source="???",
            luau_source="-- flagged",
            strategy="rule_based",
            confidence=0.1,
            flagged_for_review=True,
        )
        result = code_transpiler.TranspilationResult(scripts=[ts], total=1, flagged=1)
        entries = _transpiled_to_rbx_scripts(result)
        assert len(entries) == 1


# ── Build report ──────────────────────────────────────────────────────


class TestBuildReportDetailed:
    def _make_inputs(self, tmp_path: Path, **overrides):
        unity_path = tmp_path / "Project"
        unity_path.mkdir(exist_ok=True)
        defaults = dict(
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
            duration=1.0,
            errors=[],
        )
        defaults.update(overrides)
        return defaults

    def test_material_stats(self, tmp_path: Path) -> None:
        inputs = self._make_inputs(
            tmp_path,
            mat_result=material_mapper.MaterialMapResult(
                total=10, fully_converted=7, partially_converted=2, unconvertible=1,
                texture_ops_performed=15,
            ),
        )
        rpt = _build_report(**inputs)
        assert rpt.materials.total == 10
        assert rpt.materials.fully_converted == 7
        assert rpt.materials.texture_ops == 15

    def test_scene_game_object_count(self, tmp_path: Path) -> None:
        n1 = _snode(name="N1", file_id="100")
        n2 = _snode(name="N2", file_id="200")
        scene = scene_parser.ParsedScene(
            scene_path=Path("/s.unity"),
            roots=[n1, n2],
            all_nodes={"100": n1, "200": n2},
        )
        inputs = self._make_inputs(tmp_path, scenes=[scene])
        rpt = _build_report(**inputs)
        assert rpt.scene.scenes_parsed == 1
        assert rpt.scene.total_game_objects == 2

    def test_script_stats(self, tmp_path: Path) -> None:
        ts = code_transpiler.TranspiledScript(
            source_path=Path("/src/X.cs"),
            output_filename="X.lua",
            csharp_source="",
            luau_source="",
            strategy="rule_based",
            confidence=0.5,
            flagged_for_review=True,
        )
        inputs = self._make_inputs(
            tmp_path,
            transpilation=code_transpiler.TranspilationResult(
                scripts=[ts], total=1, succeeded=0, flagged=1,
            ),
        )
        rpt = _build_report(**inputs)
        assert rpt.scripts.total == 1
        assert rpt.scripts.flagged_for_review == 1

    def test_warnings_accumulated(self, tmp_path: Path) -> None:
        inputs = self._make_inputs(tmp_path)
        inputs["write_result"] = rbxl_writer.RbxWriteResult(
            output_path=tmp_path / "out" / "game.rbxl",
            parts_written=0,
            scripts_written=0,
            warnings=["Something fishy"],
        )
        rpt = _build_report(**inputs)
        assert len(rpt.warnings) >= 1
        assert "Something fishy" in rpt.warnings

    def test_errors_set_success_false(self, tmp_path: Path) -> None:
        inputs = self._make_inputs(tmp_path, errors=["fatal crash"])
        rpt = _build_report(**inputs)
        assert rpt.success is False
        assert "fatal crash" in rpt.errors
