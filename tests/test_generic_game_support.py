"""
Tests for broader game support fixes — validates that the converter handles
patterns common in real-world Unity games beyond simple test projects.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from modules.prefab_parser import PrefabNode, PrefabTemplate, _parse_single_prefab
from modules.code_transpiler import (
    _rule_based_transpile,
    _post_process_luau,
    _is_editor_or_test_path,
    transpile_scripts,
)
from modules.unity_yaml_utils import (
    KNOWN_COMPONENT_CIDS,
    COMPONENT_CID_TO_NAME,
    CID_CANVAS,
    CID_LOD_GROUP,
    CID_NAV_MESH_AGENT,
    CID_TERRAIN,
    CID_LINE_RENDERER,
    CID_TRAIL_RENDERER,
    CID_SPRITE_RENDERER,
    CID_RIGIDBODY_2D,
    CID_VIDEO_PLAYER,
    CID_PLAYABLE_DIRECTOR,
    CID_REFLECTION_PROBE,
    CID_HINGE_JOINT,
    CID_FIXED_JOINT,
    CID_AUDIO_LISTENER,
)
from modules.conversion_helpers import apply_materials
from modules import scene_parser, rbxl_writer, material_mapper
import config


# ---------------------------------------------------------------------------
# Component recognition tests
# ---------------------------------------------------------------------------

class TestComponentRecognition:
    """Verify new Unity component classIDs are recognised."""

    def test_canvas_recognised(self) -> None:
        assert CID_CANVAS in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_CANVAS] == "Canvas"

    def test_lod_group_recognised(self) -> None:
        assert CID_LOD_GROUP in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_LOD_GROUP] == "LODGroup"

    def test_nav_mesh_agent_recognised(self) -> None:
        assert CID_NAV_MESH_AGENT in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_NAV_MESH_AGENT] == "NavMeshAgent"

    def test_terrain_recognised(self) -> None:
        assert CID_TERRAIN in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_TERRAIN] == "Terrain"

    def test_line_renderer_recognised(self) -> None:
        assert CID_LINE_RENDERER in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_LINE_RENDERER] == "LineRenderer"

    def test_trail_renderer_recognised(self) -> None:
        assert CID_TRAIL_RENDERER in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_TRAIL_RENDERER] == "TrailRenderer"

    def test_sprite_renderer_recognised(self) -> None:
        assert CID_SPRITE_RENDERER in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_SPRITE_RENDERER] == "SpriteRenderer"

    def test_rigidbody_2d_recognised(self) -> None:
        assert CID_RIGIDBODY_2D in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_RIGIDBODY_2D] == "Rigidbody2D"

    def test_video_player_recognised(self) -> None:
        assert CID_VIDEO_PLAYER in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_VIDEO_PLAYER] == "VideoPlayer"

    def test_playable_director_recognised(self) -> None:
        assert CID_PLAYABLE_DIRECTOR in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_PLAYABLE_DIRECTOR] == "PlayableDirector"

    def test_reflection_probe_recognised(self) -> None:
        assert CID_REFLECTION_PROBE in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_REFLECTION_PROBE] == "ReflectionProbe"

    def test_hinge_joint_recognised(self) -> None:
        assert CID_HINGE_JOINT in KNOWN_COMPONENT_CIDS
        assert COMPONENT_CID_TO_NAME[CID_HINGE_JOINT] == "HingeJoint"

    def test_fixed_joint_recognised(self) -> None:
        assert CID_FIXED_JOINT in KNOWN_COMPONENT_CIDS

    def test_audio_listener_recognised(self) -> None:
        assert CID_AUDIO_LISTENER in KNOWN_COMPONENT_CIDS


# ---------------------------------------------------------------------------
# Multi-root prefab tests
# ---------------------------------------------------------------------------

class TestMultiRootPrefab:
    """Verify multi-root prefab handling."""

    def test_multi_root_creates_synthetic_container(self, tmp_path: Path) -> None:
        """A prefab with multiple root nodes should wrap them in a container."""
        prefab_content = (
            "%YAML 1.1\n"
            "%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &100\n"
            "GameObject:\n"
            "  m_Name: RootA\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &200\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 100}\n"
            "  m_Father: {fileID: 0}\n"
            "  m_LocalPosition: {x: 0, y: 0, z: 0}\n"
            "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
            "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
            "--- !u!1 &300\n"
            "GameObject:\n"
            "  m_Name: RootB\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &400\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 300}\n"
            "  m_Father: {fileID: 0}\n"
            "  m_LocalPosition: {x: 1, y: 0, z: 0}\n"
            "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
            "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        )
        prefab_file = tmp_path / "MultiRoot.prefab"
        prefab_file.write_text(prefab_content, encoding="utf-8")

        template = _parse_single_prefab(prefab_file)

        assert template.root is not None
        assert template.is_multi_root is True
        assert template.root.name == "MultiRoot"
        assert len(template.root.children) == 2
        child_names = {c.name for c in template.root.children}
        assert child_names == {"RootA", "RootB"}

    def test_single_root_no_synthetic(self, tmp_path: Path) -> None:
        """A prefab with a single root should NOT create a synthetic container."""
        prefab_content = (
            "%YAML 1.1\n"
            "%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &100\n"
            "GameObject:\n"
            "  m_Name: OnlyRoot\n"
            "  m_IsActive: 1\n"
            "--- !u!4 &200\n"
            "Transform:\n"
            "  m_GameObject: {fileID: 100}\n"
            "  m_Father: {fileID: 0}\n"
            "  m_LocalPosition: {x: 0, y: 0, z: 0}\n"
            "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
            "  m_LocalScale: {x: 1, y: 1, z: 1}\n"
        )
        prefab_file = tmp_path / "SingleRoot.prefab"
        prefab_file.write_text(prefab_content, encoding="utf-8")

        template = _parse_single_prefab(prefab_file)

        assert template.root is not None
        assert template.is_multi_root is False
        assert template.root.name == "OnlyRoot"


# ---------------------------------------------------------------------------
# Editor / test script filtering tests
# ---------------------------------------------------------------------------

class TestEditorScriptFiltering:
    """Verify editor-only and test scripts are skipped."""

    def test_editor_path_detected(self) -> None:
        assert _is_editor_or_test_path(("Scripts", "Editor", "MyEditorTool.cs")) is True

    def test_tests_path_detected(self) -> None:
        assert _is_editor_or_test_path(("Scripts", "Tests", "TestFoo.cs")) is True

    def test_test_path_detected(self) -> None:
        assert _is_editor_or_test_path(("Test", "TestBar.cs")) is True

    def test_normal_path_not_filtered(self) -> None:
        assert _is_editor_or_test_path(("Scripts", "Player", "Movement.cs")) is False

    def test_editor_tests_path_detected(self) -> None:
        assert _is_editor_or_test_path(("EditorTests", "Foo.cs")) is True

    def test_editor_scripts_skipped_in_transpilation(self, tmp_path: Path) -> None:
        """Editor scripts should be excluded from transpilation."""
        project = tmp_path / "TestProject"
        (project / "Assets" / "Scripts").mkdir(parents=True)
        (project / "Assets" / "Editor").mkdir(parents=True)

        (project / "Assets" / "Scripts" / "Player.cs").write_text(
            "using UnityEngine;\npublic class Player : MonoBehaviour { void Start() {} }",
            encoding="utf-8",
        )
        (project / "Assets" / "Editor" / "MyTool.cs").write_text(
            "using UnityEditor;\npublic class MyTool : EditorWindow { }",
            encoding="utf-8",
        )

        result = transpile_scripts(project, use_ai=False)
        assert result.total == 1  # Only Player.cs, not MyTool.cs
        assert result.scripts[0].source_path.name == "Player.cs"


# ---------------------------------------------------------------------------
# Transpiler pattern tests (new C# patterns)
# ---------------------------------------------------------------------------

class TestTranspilerNewPatterns:
    """Test transpilation of additional C# patterns."""

    def test_switch_case_converted(self) -> None:
        code = 'switch (state) {\n  case 0: DoA(); break;\n  case 1: DoB(); break;\n  default: DoC(); break;\n}'
        luau, _, _ = _rule_based_transpile(code)
        assert "switch on state" in luau

    def test_try_catch_converted(self) -> None:
        code = 'try {\n  DoSomething();\n} catch (Exception e) {\n  Debug.Log(e);\n}'
        luau, _, _ = _rule_based_transpile(code)
        assert "pcall" in luau
        assert "not ok" in luau

    def test_enum_converted(self) -> None:
        code = "public enum GameState { Menu, Playing, Paused }"
        luau, _, _ = _rule_based_transpile(code)
        assert "GameState" in luau
        assert "Menu" in luau
        assert "Playing" in luau

    def test_lambda_converted(self) -> None:
        code = "var callback = (x) => x * 2;"
        luau, _, _ = _rule_based_transpile(code)
        assert "function" in luau

    def test_auto_property_converted(self) -> None:
        code = "public int Health { get; set; }"
        luau, _, _ = _rule_based_transpile(code)
        assert "Health" in luau
        assert "nil" in luau or "local" in luau

    def test_textmeshpro_mapped(self) -> None:
        code = 'tmpText.SetText("Hello");'
        luau, _, _ = _rule_based_transpile(code)
        assert ".Text =" in luau

    def test_dotween_mapped(self) -> None:
        code = 'transform.DOMove(target, 1f);'
        luau, _, _ = _rule_based_transpile(code)
        assert "TweenService" in luau

    def test_linq_where_commented(self) -> None:
        code = "items.Where(x => x > 0);"
        luau, _, _ = _rule_based_transpile(code)
        assert "Where" in luau  # Should have a comment about manual loop

    def test_navmesh_mapped(self) -> None:
        code = "NavMesh.CalculatePath(start, end, path);"
        luau, _, _ = _rule_based_transpile(code)
        assert "PathfindingService" in luau or "CreatePath" in luau

    def test_async_await_handled(self) -> None:
        code = "await Task.Delay(1000);"
        luau, _, _ = _rule_based_transpile(code)
        assert "task.wait" in luau

    def test_invoke_mapped(self) -> None:
        code = 'Invoke("DoAction", 2f);'
        luau, _, _ = _rule_based_transpile(code)
        assert "task.delay" in luau

    def test_resources_load_mapped(self) -> None:
        code = 'Resources.Load("Prefabs/Enemy");'
        luau, _, _ = _rule_based_transpile(code)
        assert "ReplicatedStorage" in luau or "FindFirstChild" in luau


# ---------------------------------------------------------------------------
# Multi-material mesh warning tests
# ---------------------------------------------------------------------------

class TestMultiMaterialWarnings:
    """Verify multi-material mesh warnings."""

    def test_multi_material_generates_warning(self) -> None:
        """A node with multiple materials should generate a warning."""
        part = rbxl_writer.RbxPartEntry(name="TestMesh")
        node = scene_parser.SceneNode(
            name="TestMesh", file_id="1", active=True, layer=0, tag="Untagged",
            components=[
                scene_parser.ComponentData(
                    component_type="MeshRenderer",
                    file_id="2",
                    properties={
                        "m_Materials": [
                            {"guid": "aaa", "fileID": 0},
                            {"guid": "bbb", "fileID": 0},
                        ]
                    },
                )
            ],
        )
        rdef_a = material_mapper.RobloxMaterialDef(
            base_part_color=(1.0, 0.0, 0.0),
        )
        rdef_b = material_mapper.RobloxMaterialDef(
            base_part_color=(0.0, 1.0, 0.0),
        )
        guid_to_roblox = {"aaa": rdef_a, "bbb": rdef_b}
        warnings: list[str] = []
        apply_materials(part, node, guid_to_roblox, None, multi_material_warnings=warnings)

        assert len(warnings) == 1
        assert "2 materials" in warnings[0]
        assert "TestMesh" in warnings[0]
        # First material should still be applied
        assert part.color3 == (1.0, 0.0, 0.0)

    def test_single_material_no_warning(self) -> None:
        """A node with a single material should NOT generate a warning."""
        part = rbxl_writer.RbxPartEntry(name="TestMesh")
        node = scene_parser.SceneNode(
            name="TestMesh", file_id="1", active=True, layer=0, tag="Untagged",
            components=[
                scene_parser.ComponentData(
                    component_type="MeshRenderer",
                    file_id="2",
                    properties={
                        "m_Materials": [{"guid": "aaa", "fileID": 0}]
                    },
                )
            ],
        )
        rdef = material_mapper.RobloxMaterialDef(
            base_part_color=(1.0, 0.0, 0.0),
        )
        warnings: list[str] = []
        apply_materials(part, node, {"aaa": rdef}, None, multi_material_warnings=warnings)

        assert len(warnings) == 0
        assert part.color3 == (1.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Asset extension coverage tests
# ---------------------------------------------------------------------------

class TestAssetExtensions:
    """Verify new asset extensions are recognized."""

    def test_gltf_recognised(self) -> None:
        assert ".gltf" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".gltf"] == "mesh"

    def test_glb_recognised(self) -> None:
        assert ".glb" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".glb"] == "mesh"

    def test_usd_recognised(self) -> None:
        assert ".usd" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".usd"] == "mesh"

    def test_shadergraph_recognised(self) -> None:
        assert ".shadergraph" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".shadergraph"] == "shader"

    def test_mp4_video_recognised(self) -> None:
        assert ".mp4" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".mp4"] == "video"

    def test_asmdef_recognised(self) -> None:
        assert ".asmdef" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".asmdef"] == "assembly_definition"

    def test_ttf_font_recognised(self) -> None:
        assert ".ttf" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".ttf"] == "font"

    def test_inputactions_recognised(self) -> None:
        assert ".inputactions" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".inputactions"] == "input"

    def test_override_controller_recognised(self) -> None:
        assert ".overrideController" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".overrideController"] == "animation"

    def test_aiff_audio_recognised(self) -> None:
        assert ".aiff" in config.ASSET_EXT_TO_KIND
        assert config.ASSET_EXT_TO_KIND[".aiff"] == "audio"


# ---------------------------------------------------------------------------
# _post_process_luau standalone tests
# ---------------------------------------------------------------------------


class TestPostProcessLuau:
    """Tests for the _post_process_luau post-processing function."""

    def test_textmeshpro_set_text(self) -> None:
        result = _post_process_luau('tmpText.SetText("Hello World")')
        assert result == 'tmpText.Text = "Hello World"'

    def test_dotween_domove(self) -> None:
        result = _post_process_luau("transform.DOMove(target, duration)")
        assert "TweenService:Create" in result
        assert "Position = target" in result
        assert ":Play()" in result

    def test_task_delay_with_await(self) -> None:
        result = _post_process_luau("await Task.Delay(2000)")
        assert "task.wait(2.0)" in result

    def test_task_delay_without_await(self) -> None:
        result = _post_process_luau("Task.Delay(500)")
        assert "task.wait(0.5)" in result

    def test_invoke_to_task_delay(self) -> None:
        result = _post_process_luau('Invoke("DoAction", 2)')
        assert "task.delay(2, DoAction)" in result

    def test_passthrough_unrelated_code(self) -> None:
        code = "local x = 42\nprint(x)"
        assert _post_process_luau(code) == code

    def test_multiple_patterns_in_same_source(self) -> None:
        code = 'tmpText.SetText("Hi")\nInvoke("Reset", 5)'
        result = _post_process_luau(code)
        assert 'tmpText.Text = "Hi"' in result
        assert "task.delay(5, Reset)" in result


# ---------------------------------------------------------------------------
# Bridge module file existence
# ---------------------------------------------------------------------------


class TestBridgeModules:
    """Verify that bridge Luau modules exist and are structurally sound."""

    def test_state_machine_exists(self) -> None:
        sm = Path(__file__).resolve().parent.parent / "bridge" / "StateMachine.lua"
        assert sm.exists(), "bridge/StateMachine.lua should exist"

    def test_state_machine_returns_module(self) -> None:
        sm = Path(__file__).resolve().parent.parent / "bridge" / "StateMachine.lua"
        content = sm.read_text()
        assert "return StateMachine" in content

    def test_state_machine_has_lifecycle_methods(self) -> None:
        sm = Path(__file__).resolve().parent.parent / "bridge" / "StateMachine.lua"
        content = sm.read_text()
        for method in ("AddState", "Start", "Stop", "SwitchState", "PushState", "PopState"):
            assert f"function StateMachine:{method}" in content, f"Missing {method}"

    def test_state_machine_has_stack(self) -> None:
        sm = Path(__file__).resolve().parent.parent / "bridge" / "StateMachine.lua"
        content = sm.read_text()
        assert "_stack" in content
        assert "_states" in content
