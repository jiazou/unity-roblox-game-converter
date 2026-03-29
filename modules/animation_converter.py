"""
animation_converter.py — Converts Unity Animator state machines to Roblox animation configs.

Parses Unity .controller (AnimatorController) and .anim (AnimationClip) files,
then generates Luau ModuleScript config tables that drive the AnimatorBridge.lua
runtime bridge.

Strategy A: Embedded state machine generation.
- Parse Animator components from scenes to find referenced .controller files
- Parse .controller YAML → state machine graph (states, transitions, parameters)
- Parse .anim YAML → clip metadata (name, duration, looping)
- Generate per-Animator Luau config tables consumed by bridge/AnimatorBridge.lua
- Bone name mapping: Unity Humanoid → Roblox R15

No module imports another module — all wiring happens in the orchestrators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from modules import guid_resolver, scene_parser
from modules.unity_yaml_utils import (
    parse_documents as _parse_documents,
    doc_body as _doc_body,
    ref_guid as _ref_guid,
)


# ---------------------------------------------------------------------------
# Unity Humanoid → Roblox R15 bone name mapping
# ---------------------------------------------------------------------------

UNITY_TO_R15_BONE_MAP: dict[str, str] = {
    "Hips": "HumanoidRootPart",
    "Spine": "LowerTorso",
    "Chest": "UpperTorso",
    "UpperChest": "UpperTorso",
    "Neck": "Head",          # Roblox has no separate Neck part
    "Head": "Head",
    "LeftShoulder": "LeftUpperArm",
    "LeftUpperArm": "LeftUpperArm",
    "LeftLowerArm": "LeftLowerArm",
    "LeftHand": "LeftHand",
    "RightShoulder": "RightUpperArm",
    "RightUpperArm": "RightUpperArm",
    "RightLowerArm": "RightLowerArm",
    "RightHand": "RightHand",
    "LeftUpperLeg": "LeftUpperLeg",
    "LeftLowerLeg": "LeftLowerLeg",
    "LeftFoot": "LeftFoot",
    "RightUpperLeg": "RightUpperLeg",
    "RightLowerLeg": "RightLowerLeg",
    "RightFoot": "RightFoot",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AnimKeyframe:
    """A single keyframe in a transform curve."""
    time: float
    value: tuple[float, ...]  # (x,y,z) for pos/euler/scale, (x,y,z,w) for quat


@dataclass
class TransformCurve:
    """A curve animating a single property (position, rotation, etc.) on a path."""
    path: str  # "" = self, "Child/Name" = relative child
    curve_type: str  # "position", "rotation", "euler", "scale"
    keyframes: list[AnimKeyframe] = field(default_factory=list)


@dataclass
class AnimationClipInfo:
    """Metadata extracted from a Unity .anim file."""
    name: str
    path: Path
    duration: float = 0.0
    sample_rate: float = 60.0
    loop: bool = False
    # bone_paths found in the clip (for mapping validation)
    bone_paths: list[str] = field(default_factory=list)
    # Full keyframe data for transform curves
    transform_curves: list[TransformCurve] = field(default_factory=list)


@dataclass
class AnimatorParameter:
    """A parameter from the AnimatorController."""
    name: str
    param_type: str  # "Float", "Int", "Bool", "Trigger"
    default_value: float | int | bool = 0


@dataclass
class TransitionCondition:
    """A single condition on a state machine transition."""
    param: str
    op: str       # ">", "<", "==", "!=", "trigger"
    value: float | int | bool = 0


@dataclass
class StateTransition:
    """A transition between states in the Animator state machine."""
    from_state: str     # "Any" for AnyState transitions
    to_state: str
    conditions: list[TransitionCondition] = field(default_factory=list)
    has_exit_time: bool = False
    exit_time: float = 1.0
    transition_duration: float = 0.25


@dataclass
class BlendTreeEntry:
    """A single clip entry in a 1D blend tree."""
    threshold: float
    clip_name: str


@dataclass
class BlendTree:
    """A 1D blend tree (most common type)."""
    name: str
    param: str
    entries: list[BlendTreeEntry] = field(default_factory=list)


@dataclass
class AnimatorState:
    """A state in the Animator state machine."""
    name: str
    clip_name: str | None = None
    speed: float = 1.0
    loop: bool = False
    blend_tree: BlendTree | None = None


@dataclass
class AnimatorControllerData:
    """Parsed data from a .controller file."""
    name: str
    path: Path
    parameters: list[AnimatorParameter] = field(default_factory=list)
    states: list[AnimatorState] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    default_state: str | None = None


@dataclass
class AnimatorInstance:
    """An Animator component on a GameObject with its resolved controller."""
    game_object_name: str
    controller: AnimatorControllerData
    apply_root_motion: bool = False
    clip_infos: dict[str, AnimationClipInfo] = field(default_factory=dict)


@dataclass
class AnimationConversionResult:
    """Result of converting all animation data in a project."""
    config_modules: list[tuple[str, str]] = field(default_factory=list)  # (name, luau_source)
    bridge_needed: bool = False
    warnings: list[str] = field(default_factory=list)
    animators_found: int = 0
    animators_converted: int = 0


# ---------------------------------------------------------------------------
# .anim file parsing
# ---------------------------------------------------------------------------

def _extract_keyframes(m_curve: Any) -> list[AnimKeyframe]:
    """Extract keyframe time/value pairs from a Unity m_Curve list."""
    if not isinstance(m_curve, list):
        return []
    keyframes: list[AnimKeyframe] = []
    for entry in m_curve:
        if not isinstance(entry, dict):
            continue
        time = float(entry.get("time", 0))
        value_raw = entry.get("value", {})
        if isinstance(value_raw, dict):
            x = float(value_raw.get("x", 0))
            y = float(value_raw.get("y", 0))
            z = float(value_raw.get("z", 0))
            w = value_raw.get("w")
            if w is not None:
                value = (x, y, z, float(w))
            else:
                value = (x, y, z)
        else:
            try:
                value = (float(value_raw),)
            except (TypeError, ValueError):
                continue
        keyframes.append(AnimKeyframe(time=time, value=value))
    return keyframes


def parse_anim_file(anim_path: Path) -> AnimationClipInfo | None:
    """Parse a Unity .anim file (Force Text YAML) and extract clip metadata.

    Returns None if the file cannot be parsed.
    """
    try:
        raw = anim_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    triples = _parse_documents(raw)
    for _cid, _fid, doc in triples:
        body = _doc_body(doc)
        clip_name = body.get("m_Name", anim_path.stem)

        # Animation clip settings
        settings = body.get("m_AnimationClipSettings", {})
        if not isinstance(settings, dict):
            settings = {}

        loop_time = bool(settings.get("m_LoopTime", 0))

        # Duration: stopTime - startTime
        start_time = float(settings.get("m_StartTime", 0))
        stop_time = float(settings.get("m_StopTime", 0))
        duration = stop_time - start_time if stop_time > start_time else 0.0

        sample_rate = float(body.get("m_SampleRate", 60))

        # Collect bone paths and keyframe data from curve bindings
        bone_paths: list[str] = []
        transform_curves: list[TransformCurve] = []

        _CURVE_TYPE_MAP = {
            "m_RotationCurves": "rotation",
            "m_PositionCurves": "position",
            "m_ScaleCurves": "scale",
            "m_EulerCurves": "euler",
        }

        for unity_key in ("m_RotationCurves", "m_PositionCurves", "m_ScaleCurves",
                           "m_FloatCurves", "m_EulerCurves"):
            curves = body.get(unity_key, [])
            if not isinstance(curves, list):
                continue
            for curve in curves:
                if not isinstance(curve, dict):
                    continue
                # YAML `path: ` (empty value) parses as Python None
                path = curve.get("path") or ""
                if path and path not in bone_paths:
                    bone_paths.append(path)

                # Extract keyframe data for transform curves
                if unity_key in _CURVE_TYPE_MAP:
                    curve_type = _CURVE_TYPE_MAP[unity_key]
                    keyframes = _extract_keyframes(curve.get("curve", {}).get("m_Curve", []))
                    if keyframes:
                        transform_curves.append(TransformCurve(
                            path=path,
                            curve_type=curve_type,
                            keyframes=keyframes,
                        ))

        return AnimationClipInfo(
            name=clip_name,
            path=anim_path,
            duration=duration,
            sample_rate=sample_rate,
            loop=loop_time,
            bone_paths=bone_paths,
            transform_curves=transform_curves,
        )

    return None


# ---------------------------------------------------------------------------
# .controller file parsing
# ---------------------------------------------------------------------------

# Unity AnimatorConditionMode enum values
_CONDITION_MODE_MAP: dict[int, str] = {
    1: ">",       # Greater
    2: "<",       # Less
    3: "==",      # Equals
    4: "!=",      # NotEqual
    6: "trigger",  # matches "If" mode for Trigger params
}

# Unity AnimatorControllerParameterType enum values
_PARAM_TYPE_MAP: dict[int, str] = {
    1: "Float",
    3: "Int",
    4: "Bool",
    9: "Trigger",
}


def _parse_state_machine(
    sm_body: dict[str, Any],
    all_docs: dict[str, dict],
    clip_name_by_fid: dict[str, str],
) -> tuple[list[AnimatorState], list[StateTransition], str | None]:
    """Parse an AnimatorStateMachine YAML body into states and transitions."""
    states: list[AnimatorState] = []
    transitions: list[StateTransition] = []
    default_state: str | None = None

    child_states = sm_body.get("m_ChildStates", [])
    if not isinstance(child_states, list):
        child_states = []

    state_fid_to_name: dict[str, str] = {}
    default_state_fid = None

    # Default state (index 0 or m_DefaultState reference)
    default_ref = sm_body.get("m_DefaultState", {})
    if isinstance(default_ref, dict):
        default_state_fid = str(default_ref.get("fileID", ""))

    # --- Pass 1: Build state name map and state objects ---
    # (must complete before parsing transitions so all destination names resolve)
    state_bodies: list[tuple[str, str, dict]] = []  # (state_fid, state_name, state_body)

    for idx, child in enumerate(child_states):
        if not isinstance(child, dict):
            continue
        state_data = child.get("state", {})
        if not isinstance(state_data, dict):
            continue
        state_fid = str(state_data.get("fileID", ""))
        if not state_fid:
            continue

        state_doc = all_docs.get(state_fid)
        if not state_doc:
            continue
        state_body = _doc_body(state_doc)

        state_name = state_body.get("m_Name", f"State_{idx}")
        state_fid_to_name[state_fid] = state_name

        if state_fid == default_state_fid:
            default_state = state_name
        elif idx == 0 and default_state is None:
            default_state = state_name

        # Resolve the motion (clip or blend tree)
        motion_ref = state_body.get("m_Motion", {})
        clip_name = None
        blend_tree = None
        speed = float(state_body.get("m_Speed", 1.0))

        if isinstance(motion_ref, dict):
            motion_fid = str(motion_ref.get("fileID", ""))
            if motion_fid in clip_name_by_fid:
                clip_name = clip_name_by_fid[motion_fid]
            elif motion_fid in all_docs:
                bt_doc = all_docs[motion_fid]
                bt_body = _doc_body(bt_doc)
                if "m_Childs" in bt_body or "m_BlendType" in bt_body:
                    blend_tree = _parse_blend_tree(bt_body, clip_name_by_fid, all_docs)

        states.append(AnimatorState(
            name=state_name,
            clip_name=clip_name,
            speed=speed,
            loop=False,
            blend_tree=blend_tree,
        ))

        state_bodies.append((state_fid, state_name, state_body))

    # --- Pass 2: Parse transitions (all state names are now known) ---
    for _state_fid, state_name, state_body in state_bodies:
        state_transitions = state_body.get("m_Transitions", [])
        if isinstance(state_transitions, list):
            for tr_ref in state_transitions:
                if not isinstance(tr_ref, dict):
                    continue
                tr_fid = str(tr_ref.get("fileID", ""))
                if tr_fid in all_docs:
                    tr_doc = all_docs[tr_fid]
                    tr_body = _doc_body(tr_doc)
                    tr = _parse_transition(tr_body, state_name, state_fid_to_name, all_docs)
                    if tr:
                        transitions.append(tr)

    # Parse AnyState transitions
    any_transitions = sm_body.get("m_AnyStateTransitions", [])
    if isinstance(any_transitions, list):
        for tr_ref in any_transitions:
            if not isinstance(tr_ref, dict):
                continue
            tr_fid = str(tr_ref.get("fileID", ""))
            if tr_fid in all_docs:
                tr_doc = all_docs[tr_fid]
                tr_body = _doc_body(tr_doc)
                tr = _parse_transition(tr_body, "Any", state_fid_to_name, all_docs)
                if tr:
                    transitions.append(tr)

    return states, transitions, default_state


def _parse_blend_tree(
    bt_body: dict[str, Any],
    clip_name_by_fid: dict[str, str],
    all_docs: dict[str, dict],
) -> BlendTree | None:
    """Parse a BlendTree YAML body into a BlendTree data structure.

    Currently supports 1D blend trees only.
    """
    blend_type = int(bt_body.get("m_BlendType", 0))
    if blend_type != 0:
        # 0 = 1D, 1 = 2D Simple Directional, etc.
        # Only 1D is supported for now
        return None

    name = bt_body.get("m_Name", "BlendTree")
    param = bt_body.get("m_BlendParameter", "")

    children = bt_body.get("m_Childs", [])
    if not isinstance(children, list):
        return None

    entries: list[BlendTreeEntry] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        threshold = float(child.get("m_Threshold", 0))
        motion_ref = child.get("m_Motion", {})
        if isinstance(motion_ref, dict):
            motion_fid = str(motion_ref.get("fileID", ""))
            clip_name = clip_name_by_fid.get(motion_fid)
            if clip_name:
                entries.append(BlendTreeEntry(threshold=threshold, clip_name=clip_name))

    if not entries:
        return None

    return BlendTree(name=name, param=param, entries=entries)


def _parse_transition(
    tr_body: dict[str, Any],
    from_state: str,
    state_fid_to_name: dict[str, str],
    all_docs: dict[str, dict],
) -> StateTransition | None:
    """Parse an AnimatorStateTransition YAML body."""
    # Destination state
    dst_ref = tr_body.get("m_DstState", {})
    if not isinstance(dst_ref, dict):
        return None
    dst_fid = str(dst_ref.get("fileID", ""))
    to_state = state_fid_to_name.get(dst_fid)
    if not to_state:
        return None

    has_exit_time = bool(tr_body.get("m_HasExitTime", 0))
    exit_time = float(tr_body.get("m_ExitTime", 1.0))
    duration = float(tr_body.get("m_TransitionDuration", 0.25))

    # Parse conditions
    conditions: list[TransitionCondition] = []
    raw_conditions = tr_body.get("m_Conditions", [])
    if isinstance(raw_conditions, list):
        for cond in raw_conditions:
            if not isinstance(cond, dict):
                continue
            mode = int(cond.get("m_ConditionMode", 1))
            param_name = cond.get("m_ConditionEvent", "")
            threshold = cond.get("m_EventTreshold", 0)  # Unity typo: "Treshold"

            op = _CONDITION_MODE_MAP.get(mode, ">")
            conditions.append(TransitionCondition(
                param=param_name,
                op=op,
                value=threshold,
            ))

    return StateTransition(
        from_state=from_state,
        to_state=to_state,
        conditions=conditions,
        has_exit_time=has_exit_time,
        exit_time=exit_time,
        transition_duration=duration,
    )


def parse_controller_file(controller_path: Path) -> AnimatorControllerData | None:
    """Parse a Unity .controller file (Force Text YAML) and extract the state machine.

    Returns None if the file cannot be parsed.
    """
    try:
        raw = controller_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    triples = _parse_documents(raw)
    if not triples:
        return None

    # Build lookup tables
    all_docs: dict[str, dict] = {}
    clip_name_by_fid: dict[str, str] = {}
    controller_body: dict[str, Any] | None = None

    for cid, fid, doc in triples:
        all_docs[fid] = doc
        body = _doc_body(doc)

        # classID 91 = AnimatorController
        if cid == 91:
            controller_body = body
        # classID 74 = AnimationClip (embedded reference)
        elif cid == 74:
            clip_name_by_fid[fid] = body.get("m_Name", f"Clip_{fid}")

    if controller_body is None:
        return None

    name = controller_body.get("m_Name", controller_path.stem)

    # Parse parameters
    parameters: list[AnimatorParameter] = []
    raw_params = controller_body.get("m_AnimatorParameters", [])
    if isinstance(raw_params, list):
        for p in raw_params:
            if not isinstance(p, dict):
                continue
            p_name = p.get("m_Name", "")
            p_type_int = int(p.get("m_Type", 1))
            p_type = _PARAM_TYPE_MAP.get(p_type_int, "Float")
            p_default = p.get("m_DefaultFloat", 0) if p_type == "Float" else \
                        p.get("m_DefaultInt", 0) if p_type == "Int" else \
                        bool(p.get("m_DefaultBool", 0)) if p_type == "Bool" else 0
            parameters.append(AnimatorParameter(
                name=p_name, param_type=p_type, default_value=p_default
            ))

    # Parse state machine layers (use base layer — index 0)
    layers = controller_body.get("m_AnimatorLayers", [])
    states: list[AnimatorState] = []
    transitions: list[StateTransition] = []
    default_state: str | None = None

    if isinstance(layers, list) and layers:
        layer = layers[0]
        if isinstance(layer, dict):
            sm_ref = layer.get("m_StateMachine", {})
            if isinstance(sm_ref, dict):
                sm_fid = str(sm_ref.get("fileID", ""))
                sm_doc = all_docs.get(sm_fid)
                if sm_doc:
                    sm_body = _doc_body(sm_doc)
                    states, transitions, default_state = _parse_state_machine(
                        sm_body, all_docs, clip_name_by_fid
                    )

    return AnimatorControllerData(
        name=name,
        path=controller_path,
        parameters=parameters,
        states=states,
        transitions=transitions,
        default_state=default_state,
    )


# ---------------------------------------------------------------------------
# Luau config table generation
# ---------------------------------------------------------------------------

def _lua_value(v: float | int | bool) -> str:
    """Convert a Python value to a Lua literal."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v}"
    return str(v)


def _lua_string(s: str) -> str:
    """Escape a string for Lua."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def generate_animator_config(
    instance: AnimatorInstance,
) -> str:
    """Generate a Luau ModuleScript source containing the animator config table.

    The config is consumed by bridge/AnimatorBridge.lua at runtime.
    """
    ctrl = instance.controller
    lines: list[str] = []
    lines.append(f"-- Auto-generated animator config for {instance.game_object_name}")
    lines.append(f"-- Source controller: {ctrl.name}")
    lines.append("")
    lines.append("return {")

    # Parameters
    lines.append("\tparameters = {")
    for p in ctrl.parameters:
        default = _lua_value(p.default_value)
        lines.append(f"\t\t{p.name} = {{ type = {_lua_string(p.param_type)}, default = {default} }},")
    lines.append("\t},")
    lines.append("")

    # States
    lines.append("\tstates = {")
    for state in ctrl.states:
        if state.blend_tree:
            lines.append(f"\t\t{state.name} = {{ blendTree = {_lua_string(state.blend_tree.name)}, speed = {_lua_value(state.speed)}, loop = {_lua_value(state.loop)} }},")
        else:
            clip_ref = _lua_string(state.clip_name) if state.clip_name else "nil"
            # Check if we have clip info for loop setting
            loop = state.loop
            if state.clip_name and state.clip_name in instance.clip_infos:
                loop = instance.clip_infos[state.clip_name].loop
            lines.append(f"\t\t{state.name} = {{ clip = {clip_ref}, speed = {_lua_value(state.speed)}, loop = {_lua_value(loop)} }},")
    lines.append("\t},")
    lines.append("")

    # Transitions
    lines.append("\ttransitions = {")
    for tr in ctrl.transitions:
        conds = "{"
        for i, c in enumerate(tr.conditions):
            if i > 0:
                conds += ", "
            conds += f"{{ param = {_lua_string(c.param)}, op = {_lua_string(c.op)}, value = {_lua_value(c.value)} }}"
        conds += "}"

        exit_str = ""
        if tr.has_exit_time:
            exit_str = f", hasExitTime = true, exitTime = {_lua_value(tr.exit_time)}"

        lines.append(
            f"\t\t{{ from = {_lua_string(tr.from_state)}, to = {_lua_string(tr.to_state)}, "
            f"conditions = {conds}, duration = {_lua_value(tr.transition_duration)}{exit_str} }},"
        )
    lines.append("\t},")
    lines.append("")

    # Blend trees
    blend_trees = [s.blend_tree for s in ctrl.states if s.blend_tree]
    if blend_trees:
        lines.append("\tblendTrees = {")
        for bt in blend_trees:
            lines.append(f"\t\t{bt.name} = {{")
            lines.append(f"\t\t\tparam = {_lua_string(bt.param)},")
            lines.append("\t\t\tclips = {")
            for entry in bt.entries:
                lines.append(f"\t\t\t\t{{ threshold = {_lua_value(entry.threshold)}, clip = {_lua_string(entry.clip_name)} }},")
            lines.append("\t\t\t},")
            lines.append("\t\t},")
        lines.append("\t},")
        lines.append("")

    # Default state
    if ctrl.default_state:
        lines.append(f"\tdefaultState = {_lua_string(ctrl.default_state)},")

    # Root motion flag
    if instance.apply_root_motion:
        lines.append(f"\tapplyRootMotion = true,")

    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main conversion entry point
# ---------------------------------------------------------------------------

def convert_animations(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_index: guid_resolver.GuidIndex,
    project_root: Path,
) -> AnimationConversionResult:
    """Convert all Animator components found in parsed scenes.

    Resolves Animator → .controller → states/transitions/clips, then
    generates Luau config ModuleScripts for each Animator instance.

    Args:
        parsed_scenes: Parsed Unity scene data.
        guid_index: GUID resolution index for the Unity project.
        project_root: Root path of the Unity project.

    Returns:
        AnimationConversionResult with generated config modules and warnings.
    """
    result = AnimationConversionResult()

    # Collect all Animator components across scenes
    animator_instances: list[tuple[str, dict[str, Any]]] = []  # (go_name, properties)
    for scene in parsed_scenes:
        for node in scene.all_nodes.values():
            for comp in node.components:
                if comp.component_type == "Animator":
                    animator_instances.append((node.name, comp.properties))

    result.animators_found = len(animator_instances)
    if not animator_instances:
        return result

    # Cache parsed controllers and clips to avoid re-parsing
    controller_cache: dict[str, AnimatorControllerData | None] = {}
    clip_cache: dict[str, AnimationClipInfo | None] = {}

    for go_name, props in animator_instances:
        # Resolve the controller GUID
        ctrl_ref = props.get("m_Controller", {})
        if not isinstance(ctrl_ref, dict):
            result.warnings.append(f"{go_name}: Animator has no controller reference")
            continue
        ctrl_guid = _ref_guid(ctrl_ref)
        if not ctrl_guid:
            result.warnings.append(f"{go_name}: Animator controller GUID is empty")
            continue

        ctrl_path = guid_index.resolve(ctrl_guid)
        if not ctrl_path:
            result.warnings.append(f"{go_name}: Cannot resolve controller GUID {ctrl_guid}")
            continue

        # Parse controller (cached)
        ctrl_key = str(ctrl_path)
        if ctrl_key not in controller_cache:
            controller_cache[ctrl_key] = parse_controller_file(ctrl_path)
        controller = controller_cache[ctrl_key]
        if not controller:
            result.warnings.append(f"{go_name}: Failed to parse controller {ctrl_path.name}")
            continue

        # Resolve animation clips referenced by states
        clip_infos: dict[str, AnimationClipInfo] = {}
        for state in controller.states:
            clip_name = state.clip_name
            if not clip_name:
                continue
            # Try to find the .anim file by name in the project
            if clip_name not in clip_cache:
                anim_path = _find_anim_file(project_root, clip_name)
                clip_cache[clip_name] = parse_anim_file(anim_path) if anim_path else None
            clip_info = clip_cache[clip_name]
            if clip_info:
                clip_infos[clip_name] = clip_info

        # Also resolve blend tree clips
        for state in controller.states:
            if state.blend_tree:
                for entry in state.blend_tree.entries:
                    if entry.clip_name not in clip_cache:
                        anim_path = _find_anim_file(project_root, entry.clip_name)
                        clip_cache[entry.clip_name] = parse_anim_file(anim_path) if anim_path else None
                    clip_info = clip_cache.get(entry.clip_name)
                    if clip_info:
                        clip_infos[entry.clip_name] = clip_info

        apply_root_motion = bool(props.get("m_ApplyRootMotion", 0))

        instance = AnimatorInstance(
            game_object_name=go_name,
            controller=controller,
            apply_root_motion=apply_root_motion,
            clip_infos=clip_infos,
        )

        # Generate config
        config_source = generate_animator_config(instance)
        module_name = f"{go_name}_AnimatorConfig"
        result.config_modules.append((module_name, config_source))
        result.animators_converted += 1

    result.bridge_needed = result.animators_converted > 0
    return result


def _find_anim_file(project_root: Path, clip_name: str) -> Path | None:
    """Search the Unity project for an .anim file matching the clip name."""
    # Direct name match
    matches = list(project_root.rglob(f"{clip_name}.anim"))
    if matches:
        return matches[0]
    return None


# ---------------------------------------------------------------------------
# Transform animation support (Legacy Animation → TransformAnimator configs)
# ---------------------------------------------------------------------------

def is_transform_only_anim(clip: AnimationClipInfo) -> bool:
    """Return True when the clip animates only transforms (not humanoid bones).

    Transform-only animations (spin, bob, tilt) drive position/rotation/scale
    on the object itself or simple children, with no humanoid bone references.
    These are converted to TransformAnimator configs instead of AnimatorBridge.
    """
    if not clip.transform_curves:
        return False

    humanoid_bone_names = set(UNITY_TO_R15_BONE_MAP.keys())

    for curve in clip.transform_curves:
        # Check if any path segment matches a humanoid bone name
        path_parts = curve.path.split("/") if curve.path else [""]
        for part in path_parts:
            # Strip common prefixes like "Armature|"
            clean = part.split("|")[-1] if "|" in part else part
            if clean in humanoid_bone_names:
                return False

    return True


def generate_transform_anim_config(clip: AnimationClipInfo) -> str:
    """Generate a Luau ModuleScript config table for TransformAnimator.lua.

    Converts parsed .anim keyframe data into a Luau table consumed by
    bridge/TransformAnimator.lua at runtime.
    """
    lines: list[str] = []
    lines.append(f"-- Auto-generated transform animation config for {clip.name}")
    lines.append(f"-- Source: {clip.path.name}")
    lines.append("")
    lines.append("return {")
    lines.append(f"\tloop = {_lua_value(clip.loop)},")
    lines.append(f"\tduration = {_lua_value(clip.duration)},")
    lines.append("\tcurves = {")

    # Group curves by type (only self-targeting curves, path="" or first child)
    curves_by_type: dict[str, list[TransformCurve]] = {}
    for curve in clip.transform_curves:
        ctype = curve.curve_type
        if ctype not in curves_by_type:
            curves_by_type[ctype] = []
        curves_by_type[ctype].append(curve)

    for ctype in ("position", "euler", "rotation", "scale"):
        curves = curves_by_type.get(ctype)
        if not curves:
            continue

        lines.append(f"\t\t{ctype} = {{")
        for curve in curves:
            for kf in curve.keyframes:
                if len(kf.value) >= 3:
                    x, y, z = kf.value[0], kf.value[1], kf.value[2]
                    lines.append(f"\t\t\t{{ time = {kf.time}, value = Vector3.new({x}, {y}, {z}) }},")
                elif len(kf.value) == 1:
                    v = kf.value[0]
                    lines.append(f"\t\t\t{{ time = {kf.time}, value = Vector3.new({v}, {v}, {v}) }},")
        lines.append("\t\t},")

    lines.append("\t},")
    lines.append("}")
    return "\n".join(lines)


@dataclass
class TransformAnimationResult:
    """Result of converting Legacy Animation components to TransformAnimator configs."""
    config_modules: list[tuple[str, str]] = field(default_factory=list)
    bridge_needed: bool = False
    warnings: list[str] = field(default_factory=list)
    anims_found: int = 0
    anims_converted: int = 0


def convert_transform_animations(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_index: guid_resolver.GuidIndex,
    project_root: Path,
    prefab_library: Any = None,
) -> TransformAnimationResult:
    """Convert Legacy Animation components to TransformAnimator configs.

    Scans scenes AND prefabs for Animation components (classID 111), resolves
    their referenced .anim files, classifies them as transform-only, and
    generates Luau config ModuleScripts for TransformAnimator.lua.

    Args:
        parsed_scenes: Parsed Unity scene data.
        guid_index: GUID resolution index for the Unity project.
        project_root: Root path of the Unity project.
        prefab_library: Optional parsed prefab library (from prefab_parser).

    Returns:
        TransformAnimationResult with generated config modules and warnings.
    """
    result = TransformAnimationResult()

    # Collect all Animation components (Legacy Animation, classID 111)
    # from both scenes and prefabs
    anim_instances: list[tuple[str, dict[str, Any]]] = []
    seen_names: set[str] = set()

    for scene in parsed_scenes:
        for node in scene.all_nodes.values():
            for comp in node.components:
                if comp.component_type == "Animation":
                    anim_instances.append((node.name, comp.properties))
                    seen_names.add(node.name)

    # Also scan prefab nodes (PrefabComponent has same interface)
    if prefab_library is not None:
        prefabs = getattr(prefab_library, "prefabs", [])
        for pf in prefabs:
            for node in pf.all_nodes.values():
                for comp in node.components:
                    if comp.component_type == "Animation":
                        key = f"{pf.name}/{node.name}"
                        if key not in seen_names:
                            anim_instances.append((node.name, comp.properties))
                            seen_names.add(key)

    result.anims_found = len(anim_instances)
    if not anim_instances:
        return result

    clip_cache: dict[str, AnimationClipInfo | None] = {}

    for go_name, props in anim_instances:
        # Resolve animation clip references
        # Unity Animation component stores clips in m_Animation (default clip)
        # and m_Animations (array of additional clips)
        clip_guids: list[str] = []

        # Default clip
        default_clip = props.get("m_Animation", {})
        if isinstance(default_clip, dict):
            guid = _ref_guid(default_clip)
            if guid:
                clip_guids.append(guid)

        # Additional clips array
        animations_arr = props.get("m_Animations", [])
        if isinstance(animations_arr, list):
            for anim_ref in animations_arr:
                if isinstance(anim_ref, dict):
                    guid = _ref_guid(anim_ref)
                    if guid:
                        clip_guids.append(guid)

        if not clip_guids:
            # Try searching by name as fallback
            anim_path = _find_anim_file(project_root, go_name)
            if anim_path:
                cache_key = str(anim_path)
                if cache_key not in clip_cache:
                    clip_cache[cache_key] = parse_anim_file(anim_path)
                clip = clip_cache[cache_key]
                if clip and is_transform_only_anim(clip):
                    config_source = generate_transform_anim_config(clip)
                    module_name = f"{go_name}_TransformAnimConfig"
                    result.config_modules.append((module_name, config_source))
                    result.anims_converted += 1
                elif clip:
                    result.warnings.append(f"{go_name}: Animation clip is not transform-only (may use FloatCurves or bones)")
            else:
                result.warnings.append(f"{go_name}: Animation component has no clip references")
            continue

        for guid in clip_guids:
            clip_path = guid_index.resolve(guid)
            if not clip_path:
                result.warnings.append(f"{go_name}: Cannot resolve animation clip GUID {guid}")
                continue

            cache_key = str(clip_path)
            if cache_key not in clip_cache:
                clip_cache[cache_key] = parse_anim_file(clip_path)
            clip = clip_cache[cache_key]
            if not clip:
                result.warnings.append(f"{go_name}: Failed to parse {clip_path.name}")
                continue

            if is_transform_only_anim(clip):
                config_source = generate_transform_anim_config(clip)
                module_name = f"{go_name}_{clip.name}_TransformAnimConfig"
                result.config_modules.append((module_name, config_source))
                result.anims_converted += 1
            else:
                if clip.transform_curves:
                    result.warnings.append(
                        f"{go_name}: {clip.name} has humanoid bone references, skipping "
                        "(use AnimatorBridge for skeletal animations)"
                    )
                else:
                    result.warnings.append(
                        f"{go_name}: {clip.name} has no transform curves "
                        "(may use FloatCurves, embedded FBX animation, or be UI-only)"
                    )

    # Scan all standalone .anim files in the project that weren't already
    # processed via Animation components. This catches clips like Fishbones.anim
    # that exist in the project but aren't referenced by any Animation or
    # Animator component (applied via script at runtime in Unity).
    converted_clip_paths: set[str] = set(clip_cache.keys())
    for anim_path in project_root.rglob("*.anim"):
        cache_key = str(anim_path)
        if cache_key in converted_clip_paths:
            continue
        if cache_key not in clip_cache:
            clip_cache[cache_key] = parse_anim_file(anim_path)
        clip = clip_cache[cache_key]
        if not clip:
            continue
        if is_transform_only_anim(clip):
            config_source = generate_transform_anim_config(clip)
            module_name = f"{clip.name}_TransformAnimConfig"
            result.config_modules.append((module_name, config_source))
            result.anims_converted += 1
            result.anims_found += 1

    result.bridge_needed = result.anims_converted > 0
    return result


# ---------------------------------------------------------------------------
# FBX root motion extraction (for skinned meshes stripped of skeleton data)
# ---------------------------------------------------------------------------

@dataclass
class FbxRootMotion:
    """Root bone (Hips) motion extracted from an animation FBX file."""
    duration: float
    position_keyframes: list[AnimKeyframe] = field(default_factory=list)
    euler_keyframes: list[AnimKeyframe] = field(default_factory=list)


def _quat_to_euler(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    """Convert quaternion (x, y, z, w) to Euler angles (degrees) in XYZ order."""
    import math
    # Roll (X)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    rx = math.atan2(sinr_cosp, cosr_cosp)
    # Pitch (Y)
    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    ry = math.asin(sinp)
    # Yaw (Z)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    rz = math.atan2(siny_cosp, cosy_cosp)
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def extract_fbx_root_motion(fbx_path: Path) -> FbxRootMotion | None:
    """Extract root bone (Hips) motion from an animation FBX file.

    Uses assimp CLI to convert FBX → glTF, then reads the Hips bone's
    translation and rotation keyframes from the glTF binary buffer.
    Positions are converted from FBX centimetres to Roblox studs (÷100)
    and made relative to the first keyframe.

    Returns None if extraction fails or no Hips bone is found.
    """
    import base64
    import json
    import shutil
    import struct
    import subprocess
    import tempfile

    assimp_cli = shutil.which("assimp")
    if not assimp_cli:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        gltf_path = Path(tmpdir) / "anim.gltf"
        result = subprocess.run(
            [assimp_cli, "export", str(fbx_path), str(gltf_path)],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not gltf_path.exists():
            return None

        gltf_data = json.loads(gltf_path.read_text())

        animations = gltf_data.get("animations", [])
        if not animations:
            return None

        anim = animations[0]
        nodes = gltf_data.get("nodes", [])
        accessors = gltf_data.get("accessors", [])
        buffer_views = gltf_data.get("bufferViews", [])

        # Read binary buffer
        buf_uri = gltf_data["buffers"][0]["uri"]
        if buf_uri.startswith("data:"):
            buf_data = base64.b64decode(buf_uri.split(",", 1)[1])
        else:
            buf_file = Path(tmpdir) / buf_uri
            buf_data = buf_file.read_bytes()

        def _read_accessor(acc_idx: int) -> list:
            acc = accessors[acc_idx]
            bv = buffer_views[acc["bufferView"]]
            offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            count = acc["count"]
            acc_type = acc["type"]
            values = []
            for i in range(count):
                if acc_type == "SCALAR":
                    pos = offset + i * 4
                    values.append(struct.unpack_from("<f", buf_data, pos)[0])
                elif acc_type == "VEC3":
                    pos = offset + i * 12
                    values.append(struct.unpack_from("<3f", buf_data, pos))
                elif acc_type == "VEC4":
                    pos = offset + i * 16
                    values.append(struct.unpack_from("<4f", buf_data, pos))
            return values

        # Find Hips translation and rotation channels
        # Assimp splits FBX transforms into separate nodes:
        #   Hips_$AssimpFbx$_Translation (translation channel)
        #   Hips_$AssimpFbx$_Rotation (rotation channel)
        trans_times: list[float] = []
        trans_values: list[tuple[float, ...]] = []
        rot_times: list[float] = []
        rot_values: list[tuple[float, ...]] = []
        duration = 0.0

        for ch in anim.get("channels", []):
            target = ch.get("target", {})
            node_idx = target.get("node")
            if node_idx is None:
                continue
            node_name = nodes[node_idx].get("name", "")
            sampler = anim["samplers"][ch["sampler"]]

            # Track max duration from any sampler
            input_acc = accessors[sampler["input"]]
            if input_acc.get("max"):
                duration = max(duration, input_acc["max"][0])

            if "Hips" not in node_name:
                continue

            path = target.get("path", "")

            if "Translation" in node_name and path == "translation":
                trans_times = _read_accessor(sampler["input"])
                trans_values = _read_accessor(sampler["output"])
            elif "Rotation" in node_name and path == "rotation":
                rot_times = _read_accessor(sampler["input"])
                rot_values = _read_accessor(sampler["output"])

        if not trans_values and not rot_values:
            return None

        motion = FbxRootMotion(duration=duration)

        # Convert translation: FBX cm → studs, relative to first frame
        if trans_values:
            base_x, base_y, base_z = trans_values[0]
            for i, t in enumerate(trans_times):
                x, y, z = trans_values[i]
                motion.position_keyframes.append(AnimKeyframe(
                    time=t,
                    value=(
                        (x - base_x) * 0.01,
                        (y - base_y) * 0.01,
                        (z - base_z) * 0.01,
                    ),
                ))

        # Convert rotation: quaternion → euler degrees, relative to first frame
        if rot_values:
            base_euler = _quat_to_euler(*rot_values[0])
            for i, t in enumerate(rot_times):
                euler = _quat_to_euler(*rot_values[i])
                motion.euler_keyframes.append(AnimKeyframe(
                    time=t,
                    value=(
                        euler[0] - base_euler[0],
                        euler[1] - base_euler[1],
                        euler[2] - base_euler[2],
                    ),
                ))

        return motion


def generate_root_motion_config(motion: FbxRootMotion, name: str) -> str:
    """Generate a Luau TransformAnimator config from extracted FBX root motion.

    Output format matches bridge/TransformAnimator.lua expectations.
    """
    lines: list[str] = []
    lines.append(f"-- Auto-generated root motion config for {name}")
    lines.append("-- Extracted from FBX Hips bone keyframes")
    lines.append("")
    lines.append("return {")
    lines.append("\tloop = true,")
    lines.append(f"\tduration = {motion.duration:.6f},")
    lines.append("\tcurves = {")

    if motion.position_keyframes:
        lines.append("\t\tposition = {")
        for kf in motion.position_keyframes:
            x, y, z = kf.value
            lines.append(f"\t\t\t{{ time = {kf.time:.6f}, value = Vector3.new({x:.6f}, {y:.6f}, {z:.6f}) }},")
        lines.append("\t\t},")

    if motion.euler_keyframes:
        lines.append("\t\teuler = {")
        for kf in motion.euler_keyframes:
            x, y, z = kf.value
            lines.append(f"\t\t\t{{ time = {kf.time:.6f}, value = Vector3.new({x:.4f}, {y:.4f}, {z:.4f}) }},")
        lines.append("\t\t},")

    lines.append("\t},")
    lines.append("}")
    return "\n".join(lines)
