"""Tests for modules/animation_converter.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modules.animation_converter import (
    AnimationClipInfo,
    AnimationConversionResult,
    AnimatorControllerData,
    AnimatorInstance,
    AnimatorParameter,
    AnimatorState,
    BlendTree,
    BlendTreeEntry,
    StateTransition,
    TransitionCondition,
    UNITY_TO_R15_BONE_MAP,
    convert_animations,
    generate_animator_config,
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
