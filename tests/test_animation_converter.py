"""Tests for modules/animation_converter.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modules.animation_converter import (
    AnimationClipInfo,
    AnimationConversionResult,
    AnimKeyframe,
    AnimatorControllerData,
    AnimatorInstance,
    AnimatorParameter,
    AnimatorState,
    BlendTree,
    BlendTreeEntry,
    FbxRootMotion,
    StateTransition,
    TransformAnimationResult,
    TransformCurve,
    TransitionCondition,
    UNITY_TO_R15_BONE_MAP,
    _lua_value,
    _lua_string,
    _extract_keyframes,
    _find_anim_file,
    _quat_to_euler,
    convert_animations,
    convert_transform_animations,
    generate_animator_config,
    generate_root_motion_config,
    generate_transform_anim_config,
    is_transform_only_anim,
    parse_anim_file,
    parse_controller_file,
)
from modules import guid_resolver, scene_parser
from tests.conftest import make_meta


# ---------------------------------------------------------------------------
# Minimal Unity .anim YAML fixture
# ---------------------------------------------------------------------------

MINIMAL_ANIM_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!74 &7400000
    AnimationClip:
      m_Name: Idle
      m_SampleRate: 30
      m_AnimationClipSettings:
        m_StartTime: 0
        m_StopTime: 2.5
        m_LoopTime: 1
      m_RotationCurves:
        - path: Hips/Spine/Chest
          curve:
            m_Curve: []
      m_PositionCurves:
        - path: Hips
          curve:
            m_Curve: []
      m_ScaleCurves: []
      m_FloatCurves: []
      m_EulerCurves: []
""")


MINIMAL_CONTROLLER_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!91 &9100000
    AnimatorController:
      m_Name: EnemyController
      m_AnimatorParameters:
        - m_Name: speed
          m_Type: 1
          m_DefaultFloat: 0
        - m_Name: isGrounded
          m_Type: 4
          m_DefaultBool: 1
        - m_Name: attack
          m_Type: 9
          m_DefaultFloat: 0
      m_AnimatorLayers:
        - m_Name: Base Layer
          m_StateMachine: {fileID: 1100000}
    --- !u!1107 &1100000
    AnimatorStateMachine:
      m_Name: Base Layer
      m_DefaultState: {fileID: 1102000}
      m_ChildStates:
        - state: {fileID: 1102000}
        - state: {fileID: 1102001}
      m_AnyStateTransitions:
        - {fileID: 1101002}
    --- !u!1102 &1102000
    AnimatorState:
      m_Name: Idle
      m_Speed: 1
      m_Motion: {fileID: 7400001}
      m_Transitions:
        - {fileID: 1101000}
    --- !u!1102 &1102001
    AnimatorState:
      m_Name: Walk
      m_Speed: 1.2
      m_Motion: {fileID: 7400002}
      m_Transitions:
        - {fileID: 1101001}
    --- !u!74 &7400001
    AnimationClip:
      m_Name: Idle
    --- !u!74 &7400002
    AnimationClip:
      m_Name: Walk
    --- !u!1101 &1101000
    AnimatorStateTransition:
      m_DstState: {fileID: 1102001}
      m_HasExitTime: 0
      m_ExitTime: 1
      m_TransitionDuration: 0.25
      m_Conditions:
        - m_ConditionMode: 1
          m_ConditionEvent: speed
          m_EventTreshold: 0.1
    --- !u!1101 &1101001
    AnimatorStateTransition:
      m_DstState: {fileID: 1102000}
      m_HasExitTime: 0
      m_ExitTime: 1
      m_TransitionDuration: 0.15
      m_Conditions:
        - m_ConditionMode: 2
          m_ConditionEvent: speed
          m_EventTreshold: 0.1
    --- !u!1101 &1101002
    AnimatorStateTransition:
      m_DstState: {fileID: 1102000}
      m_HasExitTime: 0
      m_ExitTime: 1
      m_TransitionDuration: 0.1
      m_Conditions:
        - m_ConditionMode: 6
          m_ConditionEvent: attack
          m_EventTreshold: 0
""")


BLEND_TREE_CONTROLLER_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!91 &9100000
    AnimatorController:
      m_Name: LocomotionController
      m_AnimatorParameters:
        - m_Name: speed
          m_Type: 1
          m_DefaultFloat: 0
      m_AnimatorLayers:
        - m_Name: Base Layer
          m_StateMachine: {fileID: 1100000}
    --- !u!1107 &1100000
    AnimatorStateMachine:
      m_Name: Base Layer
      m_DefaultState: {fileID: 1102000}
      m_ChildStates:
        - state: {fileID: 1102000}
      m_AnyStateTransitions: []
    --- !u!1102 &1102000
    AnimatorState:
      m_Name: Locomotion
      m_Speed: 1
      m_Motion: {fileID: 2060000}
      m_Transitions: []
    --- !u!206 &2060000
    BlendTree:
      m_Name: LocomotionBlend
      m_BlendType: 0
      m_BlendParameter: speed
      m_Childs:
        - m_Motion: {fileID: 7400001}
          m_Threshold: 0
        - m_Motion: {fileID: 7400002}
          m_Threshold: 1
        - m_Motion: {fileID: 7400003}
          m_Threshold: 2
    --- !u!74 &7400001
    AnimationClip:
      m_Name: Idle
    --- !u!74 &7400002
    AnimationClip:
      m_Name: Walk
    --- !u!74 &7400003
    AnimationClip:
      m_Name: Run
""")


SCENE_WITH_ANIMATOR_YAML = textwrap.dedent("""\
    %YAML 1.1
    %TAG !u! tag:unity3d.com,2011:
    --- !u!1 &100
    GameObject:
      m_Name: Enemy
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
    --- !u!95 &300
    Animator:
      m_GameObject: {fileID: 100}
      m_Controller: {fileID: 9100000, guid: aabbccdd00112233aabbccdd00112233, type: 2}
      m_ApplyRootMotion: 1
""")


# ---------------------------------------------------------------------------
# Tests: .anim parsing
# ---------------------------------------------------------------------------

class TestParseAnimFile:
    def test_parses_basic_clip(self, tmp_path: Path) -> None:
        anim_file = tmp_path / "Idle.anim"
        anim_file.write_text(MINIMAL_ANIM_YAML, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert clip.name == "Idle"
        assert clip.sample_rate == 30.0
        assert clip.duration == 2.5
        assert clip.loop is True

    def test_extracts_bone_paths(self, tmp_path: Path) -> None:
        anim_file = tmp_path / "Idle.anim"
        anim_file.write_text(MINIMAL_ANIM_YAML, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert "Hips/Spine/Chest" in clip.bone_paths
        assert "Hips" in clip.bone_paths

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = parse_anim_file(tmp_path / "nonexistent.anim")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        anim_file = tmp_path / "empty.anim"
        anim_file.write_text("", encoding="utf-8")
        result = parse_anim_file(anim_file)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: .controller parsing
# ---------------------------------------------------------------------------

class TestParseControllerFile:
    def test_parses_controller_name(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "EnemyController.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert ctrl.name == "EnemyController"

    def test_parses_parameters(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "EnemyController.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.parameters) == 3

        speed = next(p for p in ctrl.parameters if p.name == "speed")
        assert speed.param_type == "Float"
        assert speed.default_value == 0

        grounded = next(p for p in ctrl.parameters if p.name == "isGrounded")
        assert grounded.param_type == "Bool"
        assert grounded.default_value is True

        attack = next(p for p in ctrl.parameters if p.name == "attack")
        assert attack.param_type == "Trigger"

    def test_parses_states(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "EnemyController.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.states) == 2

        state_names = [s.name for s in ctrl.states]
        assert "Idle" in state_names
        assert "Walk" in state_names

        walk = next(s for s in ctrl.states if s.name == "Walk")
        assert walk.clip_name == "Walk"
        assert walk.speed == 1.2

    def test_parses_default_state(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "EnemyController.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert ctrl.default_state == "Idle"

    def test_parses_transitions(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "EnemyController.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        # 2 per-state transitions + 1 AnyState transition
        assert len(ctrl.transitions) == 3

        # Idle → Walk when speed > 0.1
        idle_to_walk = next(
            t for t in ctrl.transitions
            if t.from_state == "Idle" and t.to_state == "Walk"
        )
        assert len(idle_to_walk.conditions) == 1
        assert idle_to_walk.conditions[0].param == "speed"
        assert idle_to_walk.conditions[0].op == ">"

        # AnyState transition
        any_tr = next(t for t in ctrl.transitions if t.from_state == "Any")
        assert any_tr.conditions[0].op == "trigger"

    def test_parses_blend_tree(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "Locomotion.controller"
        ctrl_file.write_text(BLEND_TREE_CONTROLLER_YAML, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.states) == 1

        loco = ctrl.states[0]
        assert loco.name == "Locomotion"
        assert loco.blend_tree is not None
        assert loco.blend_tree.param == "speed"
        assert len(loco.blend_tree.entries) == 3
        assert loco.blend_tree.entries[0].clip_name == "Idle"
        assert loco.blend_tree.entries[1].threshold == 1.0
        assert loco.blend_tree.entries[2].clip_name == "Run"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = parse_controller_file(tmp_path / "nonexistent.controller")
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        ctrl_file = tmp_path / "empty.controller"
        ctrl_file.write_text("", encoding="utf-8")
        result = parse_controller_file(ctrl_file)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Luau config generation
# ---------------------------------------------------------------------------

class TestGenerateAnimatorConfig:
    def test_generates_valid_luau(self) -> None:
        instance = AnimatorInstance(
            game_object_name="Enemy",
            controller=AnimatorControllerData(
                name="EnemyCtrl",
                path=Path("test.controller"),
                parameters=[
                    AnimatorParameter("speed", "Float", 0),
                    AnimatorParameter("isAlive", "Bool", True),
                ],
                states=[
                    AnimatorState("Idle", clip_name="Idle", speed=1, loop=True),
                    AnimatorState("Walk", clip_name="Walk", speed=1.2, loop=True),
                ],
                transitions=[
                    StateTransition(
                        from_state="Idle", to_state="Walk",
                        conditions=[TransitionCondition("speed", ">", 0.1)],
                        transition_duration=0.25,
                    ),
                ],
                default_state="Idle",
            ),
        )

        source = generate_animator_config(instance)
        assert "return {" in source
        assert "parameters" in source
        assert "speed" in source
        assert '"Float"' in source
        assert "states" in source
        assert "Idle" in source
        assert "Walk" in source
        assert "transitions" in source
        assert "defaultState" in source
        assert '"Idle"' in source

    def test_includes_blend_trees(self) -> None:
        instance = AnimatorInstance(
            game_object_name="Player",
            controller=AnimatorControllerData(
                name="PlayerCtrl",
                path=Path("test.controller"),
                parameters=[AnimatorParameter("speed", "Float", 0)],
                states=[
                    AnimatorState(
                        "Locomotion", speed=1,
                        blend_tree=BlendTree(
                            name="LocomotionBlend",
                            param="speed",
                            entries=[
                                BlendTreeEntry(0, "Idle"),
                                BlendTreeEntry(1, "Walk"),
                                BlendTreeEntry(2, "Run"),
                            ],
                        ),
                    ),
                ],
                transitions=[],
                default_state="Locomotion",
            ),
        )

        source = generate_animator_config(instance)
        assert "blendTrees" in source
        assert "LocomotionBlend" in source
        assert "threshold" in source

    def test_includes_root_motion_flag(self) -> None:
        instance = AnimatorInstance(
            game_object_name="Char",
            controller=AnimatorControllerData(
                name="Ctrl", path=Path("t.controller"),
                parameters=[], states=[], transitions=[], default_state=None,
            ),
            apply_root_motion=True,
        )

        source = generate_animator_config(instance)
        assert "applyRootMotion = true" in source

    def test_auto_generated_comment(self) -> None:
        instance = AnimatorInstance(
            game_object_name="NPC",
            controller=AnimatorControllerData(
                name="NPCCtrl", path=Path("t.controller"),
                parameters=[], states=[], transitions=[], default_state=None,
            ),
        )

        source = generate_animator_config(instance)
        assert "Auto-generated" in source
        assert "NPC" in source


# ---------------------------------------------------------------------------
# Tests: scene parsing extracts animator controller GUIDs
# ---------------------------------------------------------------------------

class TestSceneParserAnimator:
    def test_extracts_animator_controller_guid(self, tmp_path: Path) -> None:
        scene_file = tmp_path / "test.unity"
        scene_file.write_text(SCENE_WITH_ANIMATOR_YAML, encoding="utf-8")

        result = scene_parser.parse_scene(scene_file)
        assert "aabbccdd00112233aabbccdd00112233" in result.referenced_animator_controller_guids


# ---------------------------------------------------------------------------
# Tests: quaternion → euler conversion
# ---------------------------------------------------------------------------

class TestQuatToEuler:
    def test_identity_quaternion(self) -> None:
        """Identity quaternion (0,0,0,1) should produce zero euler angles."""
        rx, ry, rz = _quat_to_euler(0.0, 0.0, 0.0, 1.0)
        assert abs(rx) < 0.01
        assert abs(ry) < 0.01
        assert abs(rz) < 0.01

    def test_90_degree_yaw(self) -> None:
        """90° rotation around Z axis → rz ≈ 90."""
        import math
        # Quaternion for 90° around Z: (0, 0, sin(45°), cos(45°))
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        rx, ry, rz = _quat_to_euler(0.0, 0.0, s, c)
        assert abs(rz - 90.0) < 0.1
        assert abs(rx) < 0.1
        assert abs(ry) < 0.1

    def test_negative_pitch(self) -> None:
        """45° rotation around Y axis."""
        import math
        s = math.sin(math.radians(22.5))
        c = math.cos(math.radians(22.5))
        rx, ry, rz = _quat_to_euler(0.0, s, 0.0, c)
        assert abs(ry - 45.0) < 0.1


# ---------------------------------------------------------------------------
# Tests: FbxRootMotion + generate_root_motion_config
# ---------------------------------------------------------------------------

class TestFbxRootMotion:
    def _make_motion(self) -> FbxRootMotion:
        return FbxRootMotion(
            duration=2.0,
            position_keyframes=[
                AnimKeyframe(time=0.0, value=(0.0, 0.0, 0.0)),
                AnimKeyframe(time=0.5, value=(0.0, 0.1, 0.0)),
                AnimKeyframe(time=1.0, value=(0.0, 0.2, 0.0)),
                AnimKeyframe(time=1.5, value=(0.0, 0.1, 0.0)),
                AnimKeyframe(time=2.0, value=(0.0, 0.0, 0.0)),
            ],
            euler_keyframes=[
                AnimKeyframe(time=0.0, value=(0.0, 0.0, 0.0)),
                AnimKeyframe(time=1.0, value=(5.0, 0.0, 2.0)),
                AnimKeyframe(time=2.0, value=(0.0, 0.0, 0.0)),
            ],
        )

    def test_generate_root_motion_config_structure(self) -> None:
        config = generate_root_motion_config(self._make_motion(), "TestMesh")
        assert "return {" in config
        assert "loop = true" in config
        assert "duration = 2.000000" in config
        assert "position = {" in config
        assert "euler = {" in config
        assert "Vector3.new(" in config

    def test_generate_root_motion_config_name_in_comment(self) -> None:
        config = generate_root_motion_config(self._make_motion(), "Rat")
        assert "Rat" in config
        assert "Auto-generated" in config

    def test_generate_root_motion_config_keyframe_count(self) -> None:
        motion = self._make_motion()
        config = generate_root_motion_config(motion, "Rat")
        # 5 position keyframes + 3 euler keyframes = 8 Vector3.new lines
        assert config.count("Vector3.new(") == 8

    def test_generate_root_motion_config_position_only(self) -> None:
        motion = FbxRootMotion(
            duration=1.0,
            position_keyframes=[
                AnimKeyframe(time=0.0, value=(0.0, 0.0, 0.0)),
                AnimKeyframe(time=1.0, value=(0.0, 0.5, 0.0)),
            ],
        )
        config = generate_root_motion_config(motion, "Bounce")
        assert "position = {" in config
        assert "euler" not in config

    def test_generate_root_motion_config_euler_only(self) -> None:
        motion = FbxRootMotion(
            duration=1.0,
            euler_keyframes=[
                AnimKeyframe(time=0.0, value=(0.0, 0.0, 0.0)),
                AnimKeyframe(time=1.0, value=(10.0, 0.0, 0.0)),
            ],
        )
        config = generate_root_motion_config(motion, "Spin")
        assert "euler = {" in config
        assert "position" not in config

    def test_animator_component_attached_to_node(self, tmp_path: Path) -> None:
        scene_file = tmp_path / "test.unity"
        scene_file.write_text(SCENE_WITH_ANIMATOR_YAML, encoding="utf-8")

        result = scene_parser.parse_scene(scene_file)
        enemy = result.all_nodes.get("100")
        assert enemy is not None
        comp_types = [c.component_type for c in enemy.components]
        assert "Animator" in comp_types


# ---------------------------------------------------------------------------
# Tests: full convert_animations pipeline
# ---------------------------------------------------------------------------

class TestConvertAnimations:
    def test_no_animators_returns_empty(self, tmp_path: Path) -> None:
        """Project with no Animator components returns empty result."""
        scene_file = tmp_path / "Assets" / "test.unity"
        scene_file.parent.mkdir(parents=True)
        scene_file.write_text(textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Empty
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
        """), encoding="utf-8")

        parsed = [scene_parser.parse_scene(scene_file)]
        guid_index = guid_resolver.GuidIndex(project_root=tmp_path)

        result = convert_animations(parsed, guid_index, tmp_path)
        assert result.animators_found == 0
        assert result.animators_converted == 0
        assert result.bridge_needed is False
        assert len(result.config_modules) == 0

    def test_animator_with_resolved_controller(self, tmp_path: Path) -> None:
        """Full pipeline: scene with Animator → parse controller → generate config."""
        project = tmp_path / "TestProject"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        # Write the scene with an Animator
        scene_file = assets / "Main.unity"
        scene_file.write_text(SCENE_WITH_ANIMATOR_YAML, encoding="utf-8")

        # Write the controller file
        ctrl_file = assets / "EnemyController.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")
        make_meta(
            ctrl_file.with_suffix(".controller.meta"),
            "aabbccdd00112233aabbccdd00112233",
        )

        # Write anim files so clips can be resolved
        idle_anim = assets / "Idle.anim"
        idle_anim.write_text(MINIMAL_ANIM_YAML, encoding="utf-8")

        # Build GUID index
        guid_index = guid_resolver.build_guid_index(project)

        # Parse scene
        parsed = [scene_parser.parse_scene(scene_file)]

        # Convert
        result = convert_animations(parsed, guid_index, project)
        assert result.animators_found == 1
        assert result.animators_converted == 1
        assert result.bridge_needed is True
        assert len(result.config_modules) == 1

        mod_name, mod_source = result.config_modules[0]
        assert mod_name == "Enemy_AnimatorConfig"
        assert "return {" in mod_source
        assert "speed" in mod_source
        assert "Idle" in mod_source
        assert "Walk" in mod_source

    def test_unresolved_controller_warns(self, tmp_path: Path) -> None:
        """Animator with missing controller GUID produces a warning."""
        scene_file = tmp_path / "test.unity"
        scene_file.write_text(SCENE_WITH_ANIMATOR_YAML, encoding="utf-8")

        parsed = [scene_parser.parse_scene(scene_file)]
        guid_index = guid_resolver.GuidIndex(project_root=tmp_path)

        result = convert_animations(parsed, guid_index, tmp_path)
        assert result.animators_found == 1
        assert result.animators_converted == 0
        assert len(result.warnings) > 0
        assert "Cannot resolve controller GUID" in result.warnings[0]


# ---------------------------------------------------------------------------
# Tests: bone mapping
# ---------------------------------------------------------------------------

class TestBoneMapping:
    def test_standard_humanoid_bones_mapped(self) -> None:
        assert UNITY_TO_R15_BONE_MAP["Hips"] == "HumanoidRootPart"
        assert UNITY_TO_R15_BONE_MAP["Head"] == "Head"
        assert UNITY_TO_R15_BONE_MAP["LeftUpperArm"] == "LeftUpperArm"
        assert UNITY_TO_R15_BONE_MAP["RightFoot"] == "RightFoot"

    def test_all_r15_parts_covered(self) -> None:
        r15_parts = {
            "HumanoidRootPart", "LowerTorso", "UpperTorso", "Head",
            "LeftUpperArm", "LeftLowerArm", "LeftHand",
            "RightUpperArm", "RightLowerArm", "RightHand",
            "LeftUpperLeg", "LeftLowerLeg", "LeftFoot",
            "RightUpperLeg", "RightLowerLeg", "RightFoot",
        }
        mapped_parts = set(UNITY_TO_R15_BONE_MAP.values())
        # All R15 parts should appear in the mapped values
        assert r15_parts.issubset(mapped_parts)


# ---------------------------------------------------------------------------
# Tests: Luau helpers
# ---------------------------------------------------------------------------

class TestLuaHelpers:
    def test_lua_value_bool_true(self) -> None:
        assert _lua_value(True) == "true"

    def test_lua_value_bool_false(self) -> None:
        assert _lua_value(False) == "false"

    def test_lua_value_int(self) -> None:
        assert _lua_value(42) == "42"

    def test_lua_value_float(self) -> None:
        result = _lua_value(1.5)
        assert "1.5" in result

    def test_lua_value_zero(self) -> None:
        assert _lua_value(0) == "0"

    def test_lua_string_simple(self) -> None:
        assert _lua_string("hello") == '"hello"'

    def test_lua_string_with_quotes(self) -> None:
        assert _lua_string('say "hi"') == '"say \\"hi\\""'

    def test_lua_string_with_backslash(self) -> None:
        assert _lua_string("path\\to") == '"path\\\\to"'

    def test_lua_string_with_newline(self) -> None:
        assert _lua_string("line1\nline2") == '"line1\\nline2"'

    def test_lua_string_empty(self) -> None:
        assert _lua_string("") == '""'


# ---------------------------------------------------------------------------
# Tests: .anim edge cases
# ---------------------------------------------------------------------------

class TestParseAnimFileEdgeCases:
    def test_non_looping_clip(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: Attack
              m_SampleRate: 24
              m_AnimationClipSettings:
                m_StartTime: 0
                m_StopTime: 1.0
                m_LoopTime: 0
              m_RotationCurves: []
              m_PositionCurves: []
              m_ScaleCurves: []
              m_FloatCurves: []
              m_EulerCurves: []
        """)
        anim_file = tmp_path / "Attack.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert clip.name == "Attack"
        assert clip.loop is False
        assert clip.sample_rate == 24.0
        assert clip.duration == 1.0

    def test_clip_with_only_scale_curves(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: ScaleAnim
              m_SampleRate: 30
              m_AnimationClipSettings:
                m_StartTime: 0
                m_StopTime: 0.5
                m_LoopTime: 1
              m_RotationCurves: []
              m_PositionCurves: []
              m_ScaleCurves:
                - path: Root/Body
                  curve:
                    m_Curve: []
              m_FloatCurves: []
              m_EulerCurves: []
        """)
        anim_file = tmp_path / "ScaleAnim.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert "Root/Body" in clip.bone_paths

    def test_clip_with_float_curves(self, tmp_path: Path) -> None:
        """Float curves are used for material/blend shape animations."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: BlendShape
              m_SampleRate: 60
              m_AnimationClipSettings:
                m_StartTime: 0
                m_StopTime: 1
                m_LoopTime: 0
              m_RotationCurves: []
              m_PositionCurves: []
              m_ScaleCurves: []
              m_FloatCurves:
                - path: Face
                  curve:
                    m_Curve: []
              m_EulerCurves: []
        """)
        anim_file = tmp_path / "BlendShape.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert "Face" in clip.bone_paths

    def test_clip_missing_settings_block(self, tmp_path: Path) -> None:
        """Clip with no m_AnimationClipSettings gets defaults."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: Minimal
              m_SampleRate: 30
        """)
        anim_file = tmp_path / "Minimal.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert clip.name == "Minimal"
        assert clip.loop is False
        assert clip.duration == 0.0

    def test_clip_name_falls_back_to_filename(self, tmp_path: Path) -> None:
        """When m_Name is absent, use the file stem."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_SampleRate: 60
        """)
        anim_file = tmp_path / "JumpUp.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert clip.name == "JumpUp"

    def test_malformed_yaml_returns_none(self, tmp_path: Path) -> None:
        anim_file = tmp_path / "broken.anim"
        anim_file.write_text("{{{{not yaml at all", encoding="utf-8")
        result = parse_anim_file(anim_file)
        assert result is None

    def test_multiple_bone_paths_deduplicated(self, tmp_path: Path) -> None:
        """Same path in rotation and position curves should appear only once."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: Dup
              m_SampleRate: 30
              m_AnimationClipSettings:
                m_StartTime: 0
                m_StopTime: 1
                m_LoopTime: 0
              m_RotationCurves:
                - path: Hips/Spine
                  curve: {m_Curve: []}
              m_PositionCurves:
                - path: Hips/Spine
                  curve: {m_Curve: []}
              m_ScaleCurves: []
              m_FloatCurves: []
              m_EulerCurves: []
        """)
        anim_file = tmp_path / "Dup.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert clip.bone_paths.count("Hips/Spine") == 1


# ---------------------------------------------------------------------------
# Tests: .controller edge cases
# ---------------------------------------------------------------------------

class TestParseControllerEdgeCases:
    def test_2d_blend_tree_skipped(self, tmp_path: Path) -> None:
        """2D blend trees (m_BlendType != 0) are not supported and return None."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: Blend2D
              m_AnimatorParameters:
                - m_Name: speedX
                  m_Type: 1
                  m_DefaultFloat: 0
              m_AnimatorLayers:
                - m_Name: Base Layer
                  m_StateMachine: {fileID: 1100000}
            --- !u!1107 &1100000
            AnimatorStateMachine:
              m_Name: Base Layer
              m_DefaultState: {fileID: 1102000}
              m_ChildStates:
                - state: {fileID: 1102000}
              m_AnyStateTransitions: []
            --- !u!1102 &1102000
            AnimatorState:
              m_Name: Move
              m_Speed: 1
              m_Motion: {fileID: 2060000}
              m_Transitions: []
            --- !u!206 &2060000
            BlendTree:
              m_Name: Move2D
              m_BlendType: 1
              m_BlendParameter: speedX
              m_Childs: []
        """)
        ctrl_file = tmp_path / "Blend2D.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        state = ctrl.states[0]
        assert state.blend_tree is None

    def test_int_parameter_type(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: IntCtrl
              m_AnimatorParameters:
                - m_Name: weaponType
                  m_Type: 3
                  m_DefaultInt: 2
              m_AnimatorLayers: []
        """)
        ctrl_file = tmp_path / "IntCtrl.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.parameters) == 1
        p = ctrl.parameters[0]
        assert p.param_type == "Int"
        assert p.default_value == 2

    def test_unknown_condition_mode_defaults_to_greater(self, tmp_path: Path) -> None:
        """Condition mode 5 (not mapped) should fall back to '>'."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: UnknownCond
              m_AnimatorParameters:
                - m_Name: val
                  m_Type: 1
                  m_DefaultFloat: 0
              m_AnimatorLayers:
                - m_Name: Base Layer
                  m_StateMachine: {fileID: 1100000}
            --- !u!1107 &1100000
            AnimatorStateMachine:
              m_Name: Base Layer
              m_DefaultState: {fileID: 1102000}
              m_ChildStates:
                - state: {fileID: 1102000}
                - state: {fileID: 1102001}
              m_AnyStateTransitions: []
            --- !u!1102 &1102000
            AnimatorState:
              m_Name: A
              m_Speed: 1
              m_Motion: {fileID: 0}
              m_Transitions:
                - {fileID: 1101000}
            --- !u!1102 &1102001
            AnimatorState:
              m_Name: B
              m_Speed: 1
              m_Motion: {fileID: 0}
              m_Transitions: []
            --- !u!1101 &1101000
            AnimatorStateTransition:
              m_DstState: {fileID: 1102001}
              m_HasExitTime: 0
              m_ExitTime: 1
              m_TransitionDuration: 0.1
              m_Conditions:
                - m_ConditionMode: 5
                  m_ConditionEvent: val
                  m_EventTreshold: 0
        """)
        ctrl_file = tmp_path / "UnknownCond.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.transitions) == 1
        assert ctrl.transitions[0].conditions[0].op == ">"

    def test_multiple_conditions_on_transition(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: MultiCond
              m_AnimatorParameters:
                - m_Name: speed
                  m_Type: 1
                  m_DefaultFloat: 0
                - m_Name: isGrounded
                  m_Type: 4
                  m_DefaultBool: 1
              m_AnimatorLayers:
                - m_Name: Base Layer
                  m_StateMachine: {fileID: 1100000}
            --- !u!1107 &1100000
            AnimatorStateMachine:
              m_Name: Base Layer
              m_DefaultState: {fileID: 1102000}
              m_ChildStates:
                - state: {fileID: 1102000}
                - state: {fileID: 1102001}
              m_AnyStateTransitions: []
            --- !u!1102 &1102000
            AnimatorState:
              m_Name: Idle
              m_Speed: 1
              m_Motion: {fileID: 0}
              m_Transitions:
                - {fileID: 1101000}
            --- !u!1102 &1102001
            AnimatorState:
              m_Name: Run
              m_Speed: 1
              m_Motion: {fileID: 0}
              m_Transitions: []
            --- !u!1101 &1101000
            AnimatorStateTransition:
              m_DstState: {fileID: 1102001}
              m_HasExitTime: 0
              m_ExitTime: 1
              m_TransitionDuration: 0.2
              m_Conditions:
                - m_ConditionMode: 1
                  m_ConditionEvent: speed
                  m_EventTreshold: 1.0
                - m_ConditionMode: 3
                  m_ConditionEvent: isGrounded
                  m_EventTreshold: 1
        """)
        ctrl_file = tmp_path / "MultiCond.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.transitions) == 1
        tr = ctrl.transitions[0]
        assert len(tr.conditions) == 2
        assert tr.conditions[0].param == "speed"
        assert tr.conditions[0].op == ">"
        assert tr.conditions[1].param == "isGrounded"
        assert tr.conditions[1].op == "=="

    def test_exit_time_transition(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: ExitCtrl
              m_AnimatorParameters: []
              m_AnimatorLayers:
                - m_Name: Base Layer
                  m_StateMachine: {fileID: 1100000}
            --- !u!1107 &1100000
            AnimatorStateMachine:
              m_Name: Base Layer
              m_DefaultState: {fileID: 1102000}
              m_ChildStates:
                - state: {fileID: 1102000}
                - state: {fileID: 1102001}
              m_AnyStateTransitions: []
            --- !u!1102 &1102000
            AnimatorState:
              m_Name: PlayOnce
              m_Speed: 1
              m_Motion: {fileID: 0}
              m_Transitions:
                - {fileID: 1101000}
            --- !u!1102 &1102001
            AnimatorState:
              m_Name: Done
              m_Speed: 1
              m_Motion: {fileID: 0}
              m_Transitions: []
            --- !u!1101 &1101000
            AnimatorStateTransition:
              m_DstState: {fileID: 1102001}
              m_HasExitTime: 1
              m_ExitTime: 0.9
              m_TransitionDuration: 0.15
              m_Conditions: []
        """)
        ctrl_file = tmp_path / "ExitCtrl.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.transitions) == 1
        tr = ctrl.transitions[0]
        assert tr.has_exit_time is True
        assert tr.exit_time == 0.9
        assert tr.transition_duration == 0.15

    def test_controller_with_no_layers(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: NoLayers
              m_AnimatorParameters: []
              m_AnimatorLayers: []
        """)
        ctrl_file = tmp_path / "NoLayers.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert ctrl.name == "NoLayers"
        assert len(ctrl.states) == 0
        assert len(ctrl.transitions) == 0

    def test_controller_with_no_parameters(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!91 &9100000
            AnimatorController:
              m_Name: NoParams
              m_AnimatorLayers: []
        """)
        ctrl_file = tmp_path / "NoParams.controller"
        ctrl_file.write_text(yaml_text, encoding="utf-8")

        ctrl = parse_controller_file(ctrl_file)
        assert ctrl is not None
        assert len(ctrl.parameters) == 0


# ---------------------------------------------------------------------------
# Tests: config generation edge cases
# ---------------------------------------------------------------------------

class TestGenerateAnimatorConfigEdgeCases:
    def test_exit_time_in_transition(self) -> None:
        instance = AnimatorInstance(
            game_object_name="Test",
            controller=AnimatorControllerData(
                name="Ctrl", path=Path("t.controller"),
                parameters=[],
                states=[
                    AnimatorState("A", clip_name="ClipA", speed=1),
                    AnimatorState("B", clip_name="ClipB", speed=1),
                ],
                transitions=[
                    StateTransition(
                        from_state="A", to_state="B",
                        conditions=[],
                        has_exit_time=True,
                        exit_time=0.85,
                        transition_duration=0.1,
                    ),
                ],
                default_state="A",
            ),
        )

        source = generate_animator_config(instance)
        assert "hasExitTime = true" in source
        assert "exitTime = 0.85" in source

    def test_state_with_nil_clip(self) -> None:
        instance = AnimatorInstance(
            game_object_name="Ghost",
            controller=AnimatorControllerData(
                name="Ctrl", path=Path("t.controller"),
                parameters=[],
                states=[AnimatorState("Empty", clip_name=None, speed=1)],
                transitions=[],
                default_state="Empty",
            ),
        )

        source = generate_animator_config(instance)
        assert "clip = nil" in source

    def test_clip_info_overrides_loop(self) -> None:
        """When clip_infos has loop info, it overrides the state default."""
        clip = AnimationClipInfo(name="Walk", path=Path("Walk.anim"), loop=True)
        instance = AnimatorInstance(
            game_object_name="Player",
            controller=AnimatorControllerData(
                name="Ctrl", path=Path("t.controller"),
                parameters=[],
                states=[AnimatorState("Walk", clip_name="Walk", speed=1, loop=False)],
                transitions=[],
                default_state="Walk",
            ),
            clip_infos={"Walk": clip},
        )

        source = generate_animator_config(instance)
        assert "loop = true" in source

    def test_no_default_state(self) -> None:
        instance = AnimatorInstance(
            game_object_name="X",
            controller=AnimatorControllerData(
                name="Ctrl", path=Path("t.controller"),
                parameters=[], states=[], transitions=[],
                default_state=None,
            ),
        )

        source = generate_animator_config(instance)
        assert "defaultState" not in source

    def test_multiple_transitions(self) -> None:
        instance = AnimatorInstance(
            game_object_name="NPC",
            controller=AnimatorControllerData(
                name="Ctrl", path=Path("t.controller"),
                parameters=[AnimatorParameter("speed", "Float", 0)],
                states=[
                    AnimatorState("Idle", clip_name="Idle", speed=1),
                    AnimatorState("Walk", clip_name="Walk", speed=1),
                    AnimatorState("Run", clip_name="Run", speed=1),
                ],
                transitions=[
                    StateTransition("Idle", "Walk",
                                    [TransitionCondition("speed", ">", 0.1)], transition_duration=0.2),
                    StateTransition("Walk", "Run",
                                    [TransitionCondition("speed", ">", 2.0)], transition_duration=0.3),
                    StateTransition("Walk", "Idle",
                                    [TransitionCondition("speed", "<", 0.1)], transition_duration=0.2),
                ],
                default_state="Idle",
            ),
        )

        source = generate_animator_config(instance)
        # All 3 transitions should be present
        assert source.count("from =") == 3


# ---------------------------------------------------------------------------
# Tests: convert_animations edge cases
# ---------------------------------------------------------------------------

class TestConvertAnimationsEdgeCases:
    def test_multiple_animators_same_scene(self, tmp_path: Path) -> None:
        """Scene with two GameObjects each having an Animator."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: EnemyA
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
            --- !u!95 &300
            Animator:
              m_GameObject: {fileID: 100}
              m_Controller: {fileID: 9100000, guid: aaaa000000000000aaaa000000000000, type: 2}
              m_ApplyRootMotion: 0
            --- !u!1 &400
            GameObject:
              m_Name: EnemyB
              m_IsActive: 1
              m_Layer: 0
              m_TagString: Untagged
            --- !u!4 &500
            Transform:
              m_GameObject: {fileID: 400}
              m_LocalPosition: {x: 5, y: 0, z: 0}
              m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
              m_LocalScale: {x: 1, y: 1, z: 1}
              m_Father: {fileID: 0}
              m_Children: []
            --- !u!95 &600
            Animator:
              m_GameObject: {fileID: 400}
              m_Controller: {fileID: 9100000, guid: aaaa000000000000aaaa000000000000, type: 2}
              m_ApplyRootMotion: 1
        """)
        project = tmp_path / "TestProject"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        scene_file = assets / "Main.unity"
        scene_file.write_text(yaml_text, encoding="utf-8")

        ctrl_file = assets / "Shared.controller"
        ctrl_file.write_text(MINIMAL_CONTROLLER_YAML, encoding="utf-8")
        make_meta(ctrl_file.with_suffix(".controller.meta"),
                  "aaaa000000000000aaaa000000000000")

        guid_index = guid_resolver.build_guid_index(project)
        parsed = [scene_parser.parse_scene(scene_file)]

        result = convert_animations(parsed, guid_index, project)
        assert result.animators_found == 2
        assert result.animators_converted == 2
        assert len(result.config_modules) == 2
        names = [m[0] for m in result.config_modules]
        assert "EnemyA_AnimatorConfig" in names
        assert "EnemyB_AnimatorConfig" in names

    def test_animator_empty_controller_guid(self, tmp_path: Path) -> None:
        """Animator with zero GUID in m_Controller produces warning."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Broken
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
            --- !u!95 &300
            Animator:
              m_GameObject: {fileID: 100}
              m_Controller: {fileID: 0, guid: 00000000000000000000000000000000, type: 0}
        """)
        scene_file = tmp_path / "test.unity"
        scene_file.write_text(yaml_text, encoding="utf-8")

        parsed = [scene_parser.parse_scene(scene_file)]
        guid_index = guid_resolver.GuidIndex(project_root=tmp_path)

        result = convert_animations(parsed, guid_index, tmp_path)
        assert result.animators_found == 1
        assert result.animators_converted == 0
        assert any("empty" in w.lower() or "GUID" in w for w in result.warnings)

    def test_animator_with_non_dict_controller_ref(self, tmp_path: Path) -> None:
        """Animator with a non-dict m_Controller produces a warning."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!1 &100
            GameObject:
              m_Name: Odd
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
            --- !u!95 &300
            Animator:
              m_GameObject: {fileID: 100}
              m_Controller: 0
        """)
        scene_file = tmp_path / "test.unity"
        scene_file.write_text(yaml_text, encoding="utf-8")

        parsed = [scene_parser.parse_scene(scene_file)]
        guid_index = guid_resolver.GuidIndex(project_root=tmp_path)

        result = convert_animations(parsed, guid_index, tmp_path)
        assert result.animators_found == 1
        assert result.animators_converted == 0
        assert len(result.warnings) >= 1

    def test_controller_parse_failure_warns(self, tmp_path: Path) -> None:
        """Controller file that exists but is malformed produces a warning."""
        project = tmp_path / "TestProject"
        assets = project / "Assets"
        assets.mkdir(parents=True)

        scene_file = assets / "Main.unity"
        scene_file.write_text(SCENE_WITH_ANIMATOR_YAML, encoding="utf-8")

        ctrl_file = assets / "Bad.controller"
        ctrl_file.write_text("not valid yaml at all {{{{", encoding="utf-8")
        make_meta(ctrl_file.with_suffix(".controller.meta"),
                  "aabbccdd00112233aabbccdd00112233")

        guid_index = guid_resolver.build_guid_index(project)
        parsed = [scene_parser.parse_scene(scene_file)]

        result = convert_animations(parsed, guid_index, project)
        assert result.animators_found == 1
        assert result.animators_converted == 0
        assert any("Failed to parse" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Tests: _find_anim_file
# ---------------------------------------------------------------------------

class TestFindAnimFile:
    def test_finds_matching_anim(self, tmp_path: Path) -> None:
        anim = tmp_path / "Assets" / "Animations" / "Idle.anim"
        anim.parent.mkdir(parents=True)
        anim.write_text("dummy", encoding="utf-8")

        result = _find_anim_file(tmp_path, "Idle")
        assert result is not None
        assert result.name == "Idle.anim"

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        result = _find_anim_file(tmp_path, "NonExistent")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: AnimatorBridge.lua content validation
# ---------------------------------------------------------------------------

class TestAnimatorBridgeLua:
    """Verify the bridge Luau file has expected API surface."""

    @pytest.fixture(autouse=True)
    def _read_bridge(self) -> None:
        bridge_path = Path(__file__).parent.parent / "bridge" / "AnimatorBridge.lua"
        self.source = bridge_path.read_text(encoding="utf-8")

    def test_has_new_constructor(self) -> None:
        assert "function AnimatorBridge.new(" in self.source

    def test_has_set_float(self) -> None:
        assert "function AnimatorBridge:SetFloat(" in self.source

    def test_has_set_bool(self) -> None:
        assert "function AnimatorBridge:SetBool(" in self.source

    def test_has_set_trigger(self) -> None:
        assert "function AnimatorBridge:SetTrigger(" in self.source

    def test_has_update(self) -> None:
        assert "function AnimatorBridge:Update(" in self.source

    def test_has_destroy(self) -> None:
        assert "function AnimatorBridge:Destroy(" in self.source or \
               "function AnimatorBridge:Stop(" in self.source

    def test_returns_module(self) -> None:
        assert "return AnimatorBridge" in self.source

    def test_uses_animation_track(self) -> None:
        assert "AnimationTrack" in self.source or "LoadAnimation" in self.source


# ---------------------------------------------------------------------------
# Tests: TransformAnimator bridge module
# ---------------------------------------------------------------------------

class TestTransformAnimatorBridgeLua:
    """Verify that bridge/TransformAnimator.lua has the expected API surface."""

    @pytest.fixture(autouse=True)
    def _load_bridge(self) -> None:
        bridge_path = Path(__file__).parent.parent / "bridge" / "TransformAnimator.lua"
        assert bridge_path.exists(), "bridge/TransformAnimator.lua must exist"
        self.source = bridge_path.read_text(encoding="utf-8")

    def test_has_new_constructor(self) -> None:
        assert "function TransformAnimator.new(" in self.source

    def test_has_update(self) -> None:
        assert "function TransformAnimator:Update(" in self.source

    def test_has_destroy(self) -> None:
        assert "function TransformAnimator:Destroy(" in self.source

    def test_returns_module(self) -> None:
        assert "return TransformAnimator" in self.source

    def test_uses_heartbeat(self) -> None:
        assert "Heartbeat" in self.source

    def test_evaluates_keyframes(self) -> None:
        assert "evaluateCurve" in self.source

    def test_handles_loop(self) -> None:
        assert "duration" in self.source


# ---------------------------------------------------------------------------
# Tests: keyframe extraction
# ---------------------------------------------------------------------------

class TestExtractKeyframes:
    def test_extracts_xyz_keyframes(self) -> None:
        m_curve = [
            {"time": 0, "value": {"x": 1, "y": 2, "z": 3}},
            {"time": 1, "value": {"x": 4, "y": 5, "z": 6}},
        ]
        kfs = _extract_keyframes(m_curve)
        assert len(kfs) == 2
        assert kfs[0].time == 0
        assert kfs[0].value == (1.0, 2.0, 3.0)
        assert kfs[1].time == 1
        assert kfs[1].value == (4.0, 5.0, 6.0)

    def test_extracts_quaternion_keyframes(self) -> None:
        m_curve = [
            {"time": 0, "value": {"x": 0, "y": 0, "z": 0, "w": 1}},
        ]
        kfs = _extract_keyframes(m_curve)
        assert len(kfs) == 1
        assert kfs[0].value == (0.0, 0.0, 0.0, 1.0)

    def test_empty_list(self) -> None:
        assert _extract_keyframes([]) == []

    def test_non_list_returns_empty(self) -> None:
        assert _extract_keyframes("not a list") == []

    def test_malformed_entries_skipped(self) -> None:
        m_curve = [
            {"time": 0, "value": {"x": 1, "y": 2, "z": 3}},
            "bad entry",
            {"time": 1},  # missing value — uses default
        ]
        kfs = _extract_keyframes(m_curve)
        assert len(kfs) >= 1  # at least the good entry


# ---------------------------------------------------------------------------
# Tests: is_transform_only_anim
# ---------------------------------------------------------------------------

class TestIsTransformOnlyAnim:
    def test_self_targeting_curves_are_transform_only(self) -> None:
        clip = AnimationClipInfo(
            name="Spin",
            path=Path("Spin.anim"),
            duration=2.0,
            loop=True,
            transform_curves=[
                TransformCurve(path="", curve_type="euler", keyframes=[
                    AnimKeyframe(time=0, value=(0, 0, 0)),
                    AnimKeyframe(time=2, value=(0, 360, 0)),
                ]),
            ],
        )
        assert is_transform_only_anim(clip) is True

    def test_humanoid_bone_curves_are_not_transform_only(self) -> None:
        clip = AnimationClipInfo(
            name="Walk",
            path=Path("Walk.anim"),
            duration=1.0,
            transform_curves=[
                TransformCurve(path="Hips", curve_type="position", keyframes=[
                    AnimKeyframe(time=0, value=(0, 1, 0)),
                ]),
                TransformCurve(path="LeftUpperArm", curve_type="rotation", keyframes=[
                    AnimKeyframe(time=0, value=(0, 0, 0, 1)),
                ]),
            ],
        )
        assert is_transform_only_anim(clip) is False

    def test_no_curves_returns_false(self) -> None:
        clip = AnimationClipInfo(
            name="Empty",
            path=Path("Empty.anim"),
            transform_curves=[],
        )
        assert is_transform_only_anim(clip) is False

    def test_child_path_non_bone_is_transform_only(self) -> None:
        clip = AnimationClipInfo(
            name="ChildSpin",
            path=Path("ChildSpin.anim"),
            duration=1.0,
            transform_curves=[
                TransformCurve(path="Meshes/Fishbone", curve_type="euler", keyframes=[
                    AnimKeyframe(time=0, value=(0, 0, 0)),
                ]),
            ],
        )
        assert is_transform_only_anim(clip) is True


# ---------------------------------------------------------------------------
# Tests: generate_transform_anim_config
# ---------------------------------------------------------------------------

class TestGenerateTransformAnimConfig:
    def test_generates_valid_lua_table(self) -> None:
        clip = AnimationClipInfo(
            name="Fishbones",
            path=Path("Fishbones.anim"),
            duration=2.0,
            loop=True,
            transform_curves=[
                TransformCurve(path="", curve_type="position", keyframes=[
                    AnimKeyframe(time=0, value=(0, 0.5, 0)),
                    AnimKeyframe(time=1, value=(0, 0.4, 0)),
                    AnimKeyframe(time=2, value=(0, 0.5, 0)),
                ]),
                TransformCurve(path="", curve_type="euler", keyframes=[
                    AnimKeyframe(time=0, value=(0, 0, 33.458)),
                    AnimKeyframe(time=2, value=(0, 360, 33.458)),
                ]),
            ],
        )
        config = generate_transform_anim_config(clip)
        assert "return {" in config
        assert "loop = true" in config
        assert "duration = 2.0" in config
        assert "position" in config
        assert "euler" in config
        assert "Vector3.new(0, 0.5, 0)" in config
        assert "Vector3.new(0, 360, 33.458)" in config

    def test_includes_scale_curves(self) -> None:
        clip = AnimationClipInfo(
            name="PopIn",
            path=Path("PopIn.anim"),
            duration=0.5,
            loop=False,
            transform_curves=[
                TransformCurve(path="", curve_type="scale", keyframes=[
                    AnimKeyframe(time=0, value=(0.001, 0.001, 0.001)),
                    AnimKeyframe(time=0.5, value=(0.707, 0.707, 0.707)),
                ]),
            ],
        )
        config = generate_transform_anim_config(clip)
        assert "loop = false" in config
        assert "scale" in config
        assert "Vector3.new(0.001, 0.001, 0.001)" in config


# ---------------------------------------------------------------------------
# Tests: parse_anim_file keyframe extraction
# ---------------------------------------------------------------------------

class TestParseAnimFileKeyframes:
    def test_extracts_transform_curves_from_anim(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: Fishbones
              m_SampleRate: 60
              m_AnimationClipSettings:
                m_StartTime: 0
                m_StopTime: 2
                m_LoopTime: 1
              m_RotationCurves: []
              m_PositionCurves:
                - path: ""
                  curve:
                    m_Curve:
                      - time: 0
                        value: {x: 0, y: 0.5, z: 0}
                      - time: 1
                        value: {x: 0, y: 0.4, z: 0}
                      - time: 2
                        value: {x: 0, y: 0.5, z: 0}
              m_ScaleCurves: []
              m_FloatCurves: []
              m_EulerCurves:
                - path: ""
                  curve:
                    m_Curve:
                      - time: 0
                        value: {x: 0, y: 0, z: 33.458}
                      - time: 2
                        value: {x: 0, y: 360, z: 33.458}
        """)
        anim_file = tmp_path / "Fishbones.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert clip.name == "Fishbones"
        assert clip.duration == pytest.approx(2.0)
        assert clip.loop is True
        assert len(clip.transform_curves) == 2

        # Position curve
        pos_curves = [c for c in clip.transform_curves if c.curve_type == "position"]
        assert len(pos_curves) == 1
        assert pos_curves[0].path == ""
        assert len(pos_curves[0].keyframes) == 3
        assert pos_curves[0].keyframes[0].value == (0.0, 0.5, 0.0)
        assert pos_curves[0].keyframes[1].value == (0.0, 0.4, 0.0)

        # Euler curve
        euler_curves = [c for c in clip.transform_curves if c.curve_type == "euler"]
        assert len(euler_curves) == 1
        assert len(euler_curves[0].keyframes) == 2
        assert euler_curves[0].keyframes[1].value == (0.0, 360.0, 33.458)

    def test_is_transform_only(self, tmp_path: Path) -> None:
        """Fishbones-style anim (self-targeting) should be transform-only."""
        yaml_text = textwrap.dedent("""\
            %YAML 1.1
            %TAG !u! tag:unity3d.com,2011:
            --- !u!74 &7400000
            AnimationClip:
              m_Name: Spin
              m_SampleRate: 30
              m_AnimationClipSettings:
                m_StartTime: 0
                m_StopTime: 1
                m_LoopTime: 1
              m_RotationCurves: []
              m_PositionCurves: []
              m_ScaleCurves: []
              m_FloatCurves: []
              m_EulerCurves:
                - path: ""
                  curve:
                    m_Curve:
                      - time: 0
                        value: {x: 0, y: 0, z: 0}
                      - time: 1
                        value: {x: 0, y: 360, z: 0}
        """)
        anim_file = tmp_path / "Spin.anim"
        anim_file.write_text(yaml_text, encoding="utf-8")

        clip = parse_anim_file(anim_file)
        assert clip is not None
        assert is_transform_only_anim(clip) is True
