"""
conversion_helpers.py — Data conversion helpers for the Unity → Roblox pipeline.

These functions transform parsed Unity data structures into Roblox-ready
objects. They are extracted from converter.py to keep the CLI orchestration
separate from the conversion logic and to make these functions independently
testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules import (
    code_transpiler,
    guid_resolver,
    material_mapper,
    mesh_decimator,
    prefab_parser,
    report_generator,
    scene_parser,
    rbxl_writer,
)


# ---------------------------------------------------------------------------
# Component conversion tracking
# ---------------------------------------------------------------------------

# Components that node_to_part actually converts to Roblox equivalents
_CONVERTED_COMPONENTS: frozenset[str] = frozenset({
    "Transform", "RectTransform",
    "MeshFilter", "MeshRenderer", "SkinnedMeshRenderer",
    "BoxCollider", "SphereCollider", "CapsuleCollider", "MeshCollider",
    "Rigidbody",
    "Light",
    "AudioSource",
    "ParticleSystem",
    "Camera",
    "MonoBehaviour",
    "Canvas", "CanvasRenderer", "CanvasGroup",
})

# Suggestions for unconverted components — what users can do about them
_COMPONENT_SUGGESTIONS: dict[str, str] = {
    "Animator": "Port animation state machine manually via Roblox AnimationController",
    "CharacterController": "Replace with Humanoid or custom character controller in Luau",
    "NavMeshAgent": "Use PathfindingService for AI navigation in Roblox",
    "NavMeshObstacle": "Use PathfindingService modifiers for obstacles",
    "Terrain": "Recreate terrain using Roblox Terrain editor or Terrain:FillRegion()",
    "TerrainCollider": "Roblox Terrain has built-in collision",
    "LineRenderer": "Use Beam instances or draw lines with Parts",
    "TrailRenderer": "Use Trail instances attached to Parts",
    "SpriteRenderer": "Use Decal on a Part or ImageLabel in a SurfaceGui",
    "Rigidbody2D": "Roblox has no 2D physics — rewrite as 3D or use custom constraints",
    "BoxCollider2D": "Replace with 3D BoxCollider or use custom 2D collision",
    "CircleCollider2D": "Replace with 3D SphereCollider or use custom 2D collision",
    "PolygonCollider2D": "Replace with 3D MeshCollider or use custom 2D collision",
    "HingeJoint": "Use HingeConstraint in Roblox",
    "FixedJoint": "Use WeldConstraint or RigidConstraint in Roblox",
    "SpringJoint": "Use SpringConstraint in Roblox",
    "ConfigurableJoint": "Decompose into Roblox constraint primitives (Hinge + Spring + etc.)",
    "Cloth": "No cloth simulation in Roblox — use animated MeshParts or skip",
    "WindZone": "No wind simulation in Roblox — fake with particle drift or skip",
    "ReflectionProbe": "Roblox handles reflections automatically via Lighting",
    "LightProbeGroup": "Roblox handles ambient lighting via Lighting service",
    "AudioListener": "Roblox positions audio listener at the camera automatically",
    "VideoPlayer": "Use VideoFrame in Roblox SurfaceGui",
    "PlayableDirector": "Port Timeline sequences as scripted cutscenes in Luau",
    "LODGroup": "Roblox has no LOD system — use the highest-detail mesh",
}


@dataclass
class ComponentWarning:
    """A warning about a component that was recognized but not converted."""
    game_object: str
    component_type: str
    suggestion: str


def _collect_component_warnings(
    node: scene_parser.SceneNode,
    warnings: list[ComponentWarning],
) -> None:
    """Check a node's components and record warnings for unconverted ones."""
    for comp in node.components:
        if comp.component_type not in _CONVERTED_COMPONENTS:
            suggestion = _COMPONENT_SUGGESTIONS.get(
                comp.component_type,
                "No automatic conversion available — port manually",
            )
            warnings.append(ComponentWarning(
                game_object=node.name,
                component_type=comp.component_type,
                suggestion=suggestion,
            ))


def _parse_color3(color_data: Any, normalize_255: bool = False) -> tuple[float, float, float]:
    """Extract an (r, g, b) tuple from a Unity color dict, defaulting to white."""
    if not isinstance(color_data, dict):
        return (1.0, 1.0, 1.0)
    channels = []
    for key in ("r", "g", "b"):
        v = float(color_data.get(key, 1.0))
        if normalize_255 and v > 1:
            v /= 255.0
        channels.append(v)
    return (channels[0], channels[1], channels[2])

def roblox_def_to_surface_appearance(
    rdef: material_mapper.RobloxMaterialDef,
) -> rbxl_writer.RbxSurfaceAppearance:
    """Map a RobloxMaterialDef to an RbxSurfaceAppearance for the rbxl writer."""
    return rbxl_writer.RbxSurfaceAppearance(
        color_map=rdef.color_map,
        normal_map=rdef.normal_map,
        metalness_map=rdef.metalness_map,
        roughness_map=rdef.roughness_map,
        emissive_mask=rdef.emissive_mask,
        emissive_strength=rdef.emissive_strength,
        emissive_tint=rdef.emissive_tint,
        color_tint=rdef.color_tint,
        alpha_mode=rdef.alpha_mode,
    )


# ---------------------------------------------------------------------------
# Component conversion helpers (extracted from _node_to_part)
# ---------------------------------------------------------------------------

def apply_collider_properties(
    part: rbxl_writer.RbxPartEntry,
    components: list[scene_parser.ComponentData],
) -> None:
    """Apply physics collider and rigidbody properties to a part."""
    for comp in components:
        if comp.component_type == "BoxCollider":
            is_trigger = bool(comp.properties.get("m_IsTrigger", 0))
            if is_trigger:
                part.transparency = 1.0
                part.can_collide = False
            else:
                part.anchored = False
            size = comp.properties.get("m_Size", {})
            if isinstance(size, dict):
                sx = float(size.get("x", 4.0))
                sy = float(size.get("y", 1.0))
                sz = float(size.get("z", 4.0))
                part.size = (sx, sy, sz)
        elif comp.component_type == "SphereCollider":
            is_trigger = bool(comp.properties.get("m_IsTrigger", 0))
            if is_trigger:
                part.transparency = 1.0
                part.can_collide = False
            else:
                part.anchored = False
            radius = float(comp.properties.get("m_Radius", 0.5))
            diameter = radius * 2
            part.size = (diameter, diameter, diameter)
        elif comp.component_type == "CapsuleCollider":
            is_trigger = bool(comp.properties.get("m_IsTrigger", 0))
            if is_trigger:
                part.transparency = 1.0
                part.can_collide = False
            else:
                part.anchored = False
            radius = float(comp.properties.get("m_Radius", 0.5))
            height = float(comp.properties.get("m_Height", 2.0))
            diameter = radius * 2
            part.size = (diameter, height, diameter)
        elif comp.component_type == "Rigidbody":
            is_kinematic = comp.properties.get("m_IsKinematic", 0)
            part.anchored = bool(is_kinematic)


def convert_light_components(
    part: rbxl_writer.RbxPartEntry,
    components: list[scene_parser.ComponentData],
    directional_lights: list[dict] | None = None,
) -> None:
    """Convert Unity Light components to Roblox light child tuples.

    Directional lights (type 1) are collected separately since they map to
    Roblox's global Lighting service, not a per-part child.
    """
    for comp in components:
        if comp.component_type != "Light":
            continue
        props = comp.properties
        light_type = int(props.get("m_Type", 2))
        color = _parse_color3(props.get("m_Color", {}))
        intensity = float(props.get("m_Intensity", 1.0))
        range_val = float(props.get("m_Range", 10.0))
        shadows = int(props.get("m_Shadows", {}).get("m_Type", 0) if isinstance(props.get("m_Shadows"), dict) else props.get("m_Shadows", 0))
        spot_angle = float(props.get("m_SpotAngle", 30.0))

        if light_type == 0:  # Spot
            part.light_children.append(("SpotLight", color, intensity, range_val, bool(shadows), spot_angle))
        elif light_type == 1:  # Directional → global Lighting
            if directional_lights is not None:
                directional_lights.append({
                    "color": color,
                    "intensity": intensity,
                    "shadows": bool(shadows),
                })
        elif light_type == 2:  # Point
            part.light_children.append(("PointLight", color, intensity, range_val, bool(shadows), 0.0))


def convert_audio_components(
    part: rbxl_writer.RbxPartEntry,
    node_name: str,
    components: list[scene_parser.ComponentData],
    guid_index: guid_resolver.GuidIndex | None,
) -> None:
    """Convert Unity AudioSource components to Roblox sound child tuples."""
    for comp in components:
        if comp.component_type != "AudioSource":
            continue
        props = comp.properties
        clip_ref = props.get("m_audioClip", {})
        clip_guid = clip_ref.get("guid", "") if isinstance(clip_ref, dict) else ""
        clip_path = ""
        if clip_guid and guid_index:
            resolved = guid_index.resolve(clip_guid)
            clip_path = str(resolved) if resolved else clip_guid

        volume = float(props.get("m_Volume", 1.0))
        pitch = float(props.get("m_Pitch", 1.0))
        # Unity YAML uses "Loop" (no m_ prefix) for AudioSource
        loop = bool(props.get("Loop", props.get("m_Loop", 0)))
        play_on_awake = bool(props.get("m_PlayOnAwake", 1))
        # Unity YAML uses "MinDistance"/"MaxDistance" (no m_ prefix)
        min_dist = float(props.get("MinDistance", props.get("m_MinDistance", 1.0)))
        max_dist = float(props.get("MaxDistance", props.get("m_MaxDistance", 500.0)))

        part.sound_children.append((
            node_name + "_Sound",
            clip_path,
            volume,
            loop,
            pitch,
            play_on_awake,
            min_dist,
            max_dist,
        ))


def convert_particle_components(
    part: rbxl_writer.RbxPartEntry,
    node_name: str,
    components: list[scene_parser.ComponentData],
) -> None:
    """Convert Unity ParticleSystem components to Roblox particle emitter tuples."""
    for comp in components:
        if comp.component_type != "ParticleSystem":
            continue
        props = comp.properties
        initial_module = props.get("InitialModule", {})
        emission_module = props.get("EmissionModule", {})

        def _scalar_or_default(mm: Any, default: float) -> float:
            if isinstance(mm, dict):
                return float(mm.get("scalar", mm.get("value", default)))
            try:
                return float(mm)
            except (TypeError, ValueError):
                return default

        lifetime = _scalar_or_default(initial_module.get("startLifetime", {}), 5.0)
        speed = _scalar_or_default(initial_module.get("startSpeed", {}), 5.0)
        size = _scalar_or_default(initial_module.get("startSize", {}), 1.0)
        rate = _scalar_or_default(emission_module.get("rateOverTime", {}), 10.0)

        start_color = initial_module.get("startColor", {})
        color_data = start_color.get("maxColor", {}) if isinstance(start_color, dict) else {}
        p_color = _parse_color3(color_data, normalize_255=True)

        part.particle_children.append((
            node_name + "_Particles",
            rate, lifetime, lifetime,
            speed, speed,
            size, p_color,
            None,   # texture
            0.0,    # light_emission
            0.0,    # transparency
        ))


def apply_materials(
    part: rbxl_writer.RbxPartEntry,
    node: scene_parser.SceneNode,
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None,
    guid_to_companion_scripts: dict[str, list[str]] | None,
    multi_material_warnings: list[str] | None = None,
) -> None:
    """Attach material data and companion scripts to a part from a scene node.

    Roblox supports only one material per MeshPart. When a Unity renderer has
    multiple materials (common in complex games), the first resolved material
    is applied and a warning is logged for the additional materials. This
    allows downstream tools / reports to flag meshes that need manual splitting.
    """
    if not guid_to_roblox_def:
        return
    for comp in node.components:
        if comp.component_type not in ("MeshRenderer", "SkinnedMeshRenderer"):
            continue
        # Skip disabled renderers — they should not be visible
        if not bool(comp.properties.get("m_Enabled", 1)):
            part.transparency = 1.0
            return
        mat_refs = comp.properties.get("m_Materials", []) or []
        resolved_guids: list[str] = []
        for mat_ref in mat_refs:
            if isinstance(mat_ref, dict):
                guid = mat_ref.get("guid", "")
                if guid and guid in guid_to_roblox_def:
                    resolved_guids.append(guid)

        if not resolved_guids:
            continue

        # Apply the first material (Roblox limitation: one material per MeshPart)
        rdef = guid_to_roblox_def[resolved_guids[0]]
        part.surface_appearance = roblox_def_to_surface_appearance(rdef)
        if rdef.base_part_color:
            part.color3 = rdef.base_part_color
        if rdef.base_part_transparency > 0:
            part.transparency = rdef.base_part_transparency
        if guid_to_companion_scripts:
            for i, src in enumerate(guid_to_companion_scripts.get(resolved_guids[0], ())):
                suffix = f"_{i+1}" if i > 0 else ""
                part.scripts.append(rbxl_writer.RbxScriptEntry(
                    name=f"{node.name}_MaterialEffect{suffix}",
                    luau_source=src,
                    script_type="LocalScript",
                ))

        # Warn about additional materials that cannot be applied
        if len(resolved_guids) > 1 and multi_material_warnings is not None:
            multi_material_warnings.append(
                f"'{node.name}' has {len(resolved_guids)} materials but Roblox "
                f"supports only 1 per MeshPart. The mesh needs to be split in a "
                f"3D tool (e.g. Blender) for full material fidelity."
            )
        break  # only process first renderer component


# ---------------------------------------------------------------------------
# SceneNode → RbxPartEntry conversion
# ---------------------------------------------------------------------------

# Known Unity built-in primitive mesh GUIDs (from Unity's default resources)
_UNITY_PRIMITIVE_GUIDS: dict[str, str] = {
    # fileID values used for Unity built-in meshes in MeshFilter references
    # Cube → Block, Sphere → Ball, Cylinder → Cylinder
}
# Unity built-in mesh names → Roblox Part shapes
_UNITY_PRIMITIVE_NAMES: dict[str, str] = {
    "Cube": "Block",
    "Sphere": "Ball",
    "Cylinder": "Cylinder",
    "Capsule": "Cylinder",  # closest approximation
    "Plane": "Block",       # flat block
}


def _detect_primitive_shape(node: scene_parser.SceneNode) -> str | None:
    """Detect if a node uses a Unity built-in primitive and return Roblox shape."""
    for comp in node.components:
        if comp.component_type == "MeshFilter":
            mesh_ref = comp.properties.get("m_Mesh", {})
            if isinstance(mesh_ref, dict):
                # Built-in meshes have guid 0000000000000000e000000000000000
                guid = mesh_ref.get("guid", "")
                if guid == "0000000000000000e000000000000000":
                    # fileID identifies which built-in primitive
                    file_id = mesh_ref.get("fileID", 0)
                    _BUILTIN_MESH_IDS = {
                        10202: "Block",     # Cube
                        10207: "Ball",      # Sphere
                        10206: "Cylinder",  # Cylinder
                        10208: "Cylinder",  # Capsule → Cylinder
                        10209: "Block",     # Plane → flat Block
                        10210: "Block",     # Quad → flat Block
                    }
                    shape = _BUILTIN_MESH_IDS.get(file_id)
                    if shape:
                        return shape
    # Fallback: check node name for common primitive names
    name_lower = node.name.lower().rstrip("0123456789 ()_")
    return _UNITY_PRIMITIVE_NAMES.get(name_lower.capitalize())


def _quat_multiply(q1: tuple, q2: tuple) -> tuple:
    """Multiply two quaternions (x, y, z, w)."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
    )


def _quat_rotate(q: tuple, v: tuple) -> tuple:
    """Rotate a vector by a quaternion (x, y, z, w)."""
    x, y, z, w = q
    vx, vy, vz = v
    # q * v * q_conjugate
    t = (
        2.0 * (y*vz - z*vy),
        2.0 * (z*vx - x*vz),
        2.0 * (x*vy - y*vx),
    )
    return (
        vx + w*t[0] + y*t[2] - z*t[1],
        vy + w*t[1] + z*t[0] - x*t[2],
        vz + w*t[2] + x*t[1] - y*t[0],
    )


def _compute_world_transform(
    local_pos: tuple, local_rot: tuple,
    parent_pos: tuple, parent_rot: tuple,
) -> tuple[tuple, tuple]:
    """world_pos = parent_pos + parent_rot * local_pos; world_rot = parent_rot * local_rot."""
    rotated = _quat_rotate(parent_rot, local_pos)
    world_pos = (
        parent_pos[0] + rotated[0],
        parent_pos[1] + rotated[1],
        parent_pos[2] + rotated[2],
    )
    world_rot = _quat_multiply(parent_rot, local_rot)
    return world_pos, world_rot


def node_to_part(
    node: scene_parser.SceneNode,
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None,
    guid_to_companion_scripts: dict[str, list[str]] | None,
    guid_index: guid_resolver.GuidIndex | None,
    mesh_path_remap: dict[str, str] | None = None,
    directional_lights: list[dict] | None = None,
    component_warnings: list[ComponentWarning] | None = None,
    parent_world_pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
    parent_world_rot: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
) -> rbxl_writer.RbxPartEntry:
    """Convert a SceneNode tree to an RbxPartEntry tree (recursive)."""
    if component_warnings is not None:
        _collect_component_warnings(node, component_warnings)

    world_pos, world_rot = _compute_world_transform(
        node.position, node.rotation, parent_world_pos, parent_world_rot,
    )

    base_size = (1.0, 1.0, 1.0)
    scaled_size = (
        base_size[0] * abs(node.scale[0]),
        base_size[1] * abs(node.scale[1]),
        base_size[2] * abs(node.scale[2]),
    )
    part = rbxl_writer.RbxPartEntry(
        name=node.name,
        position=world_pos,
        rotation=world_rot,
        size=scaled_size,
        anchored=True,
    )

    # Detect Unity built-in primitive → Roblox shape
    shape = _detect_primitive_shape(node)
    if shape and not node.mesh_guid:
        part.shape = shape

    # Set mesh_id from the node's mesh GUID via the GUID index.
    if node.mesh_guid and guid_index:
        mesh_path = guid_index.resolve(node.mesh_guid)
        if mesh_path:
            mesh_str = str(mesh_path)
            if mesh_path_remap and mesh_str in mesh_path_remap:
                mesh_str = mesh_path_remap[mesh_str]
            part.mesh_id = mesh_str
            # Try to derive part size from mesh bounding box
            mesh_bounds = _get_mesh_bounds(mesh_str)
            if mesh_bounds:
                part.size = (
                    mesh_bounds[0] * abs(node.scale[0]),
                    mesh_bounds[1] * abs(node.scale[1]),
                    mesh_bounds[2] * abs(node.scale[2]),
                )

    # Apply component conversions
    apply_collider_properties(part, node.components)
    convert_light_components(part, node.components, directional_lights)
    convert_audio_components(part, node.name, node.components, guid_index)
    convert_particle_components(part, node.name, node.components)
    apply_materials(part, node, guid_to_roblox_def, guid_to_companion_scripts)

    # No renderer = invisible (Unity default; Roblox needs explicit Transparency=1)
    comp_types = {c.component_type for c in node.components}
    has_renderer = bool(comp_types & {"MeshRenderer", "SkinnedMeshRenderer", "SpriteRenderer"})
    has_mesh = node.mesh_guid is not None or part.shape is not None
    if not has_renderer and not has_mesh:
        part.transparency = 1.0
        part.can_collide = False

    # Inactive GameObjects → invisible
    if not node.active:
        part.transparency = 1.0
        part.can_collide = False

    # Recurse into children to preserve hierarchy (skip nested UI subtrees)
    for child in node.children:
        if _is_ui_subtree(child):
            continue
        part.children.append(node_to_part(
            child, guid_to_roblox_def, guid_to_companion_scripts, guid_index,
            mesh_path_remap, directional_lights, component_warnings,
            parent_world_pos=world_pos, parent_world_rot=world_rot,
        ))

    return part


# ---------------------------------------------------------------------------
# Prefab → SceneNode conversion
# ---------------------------------------------------------------------------

def prefab_node_to_scene_node(
    pnode: prefab_parser.PrefabNode,
) -> scene_parser.SceneNode:
    """Convert a PrefabNode tree into a SceneNode tree (recursive)."""
    snode = scene_parser.SceneNode(
        name=pnode.name,
        file_id=pnode.file_id,
        active=pnode.active,
        layer=0,
        tag="Untagged",
        position=pnode.position,
        rotation=pnode.rotation,
        scale=pnode.scale,
        mesh_guid=pnode.mesh_guid,
        mesh_file_id=pnode.mesh_file_id,
        from_prefab_instance=True,
    )
    for pc in pnode.components:
        snode.components.append(scene_parser.ComponentData(
            component_type=pc.component_type,
            file_id=pc.file_id,
            properties=pc.properties,
        ))
    for child in pnode.children:
        snode.children.append(prefab_node_to_scene_node(child))
    return snode


# ---------------------------------------------------------------------------
# PrefabInstance modification application
# ---------------------------------------------------------------------------

def apply_prefab_modifications(
    node: scene_parser.SceneNode,
    modifications: list[dict],
) -> None:
    """
    Apply PrefabInstance m_Modifications to a resolved prefab node tree.

    Unity m_Modifications is a list of dicts, each with:
      - target: {fileID, guid}
      - propertyPath: str
      - value: str
    """
    fid_to_node: dict[str, scene_parser.SceneNode] = {}

    def _index(n: scene_parser.SceneNode) -> None:
        fid_to_node[n.file_id] = n
        for comp in n.components:
            fid_to_node[comp.file_id] = n
        for child in n.children:
            _index(child)

    _index(node)

    for mod in modifications:
        if not isinstance(mod, dict):
            continue
        target = mod.get("target", {})
        target_fid = str(target.get("fileID", "")) if isinstance(target, dict) else ""
        prop_path = mod.get("propertyPath", "")
        value = mod.get("value", "")

        target_node = fid_to_node.get(target_fid)
        if not target_node:
            continue

        try:
            fval = float(value)
        except (ValueError, TypeError):
            fval = None

        if prop_path == "m_LocalPosition.x" and fval is not None:
            target_node.position = (fval, target_node.position[1], target_node.position[2])
        elif prop_path == "m_LocalPosition.y" and fval is not None:
            target_node.position = (target_node.position[0], fval, target_node.position[2])
        elif prop_path == "m_LocalPosition.z" and fval is not None:
            target_node.position = (target_node.position[0], target_node.position[1], fval)
        elif prop_path == "m_LocalRotation.x" and fval is not None:
            target_node.rotation = (fval, target_node.rotation[1], target_node.rotation[2], target_node.rotation[3])
        elif prop_path == "m_LocalRotation.y" and fval is not None:
            target_node.rotation = (target_node.rotation[0], fval, target_node.rotation[2], target_node.rotation[3])
        elif prop_path == "m_LocalRotation.z" and fval is not None:
            target_node.rotation = (target_node.rotation[0], target_node.rotation[1], fval, target_node.rotation[3])
        elif prop_path == "m_LocalRotation.w" and fval is not None:
            target_node.rotation = (target_node.rotation[0], target_node.rotation[1], target_node.rotation[2], fval)
        elif prop_path == "m_LocalScale.x" and fval is not None:
            target_node.scale = (fval, target_node.scale[1], target_node.scale[2])
        elif prop_path == "m_LocalScale.y" and fval is not None:
            target_node.scale = (target_node.scale[0], fval, target_node.scale[2])
        elif prop_path == "m_LocalScale.z" and fval is not None:
            target_node.scale = (target_node.scale[0], target_node.scale[1], fval)
        elif prop_path == "m_Name":
            target_node.name = str(value)
        elif prop_path == "m_IsActive":
            target_node.active = str(value) == "1"


# ---------------------------------------------------------------------------
# Serialized field reference extraction (MonoBehaviour → prefab wiring)
# ---------------------------------------------------------------------------

# Unity internal MonoBehaviour properties that should NOT be treated as
# user-defined serialized fields.
_MONO_INTERNAL_PROPS: set[str] = {
    "m_ObjectHideFlags", "m_CorrespondingSourceObject", "m_PrefabInstance",
    "m_PrefabAsset", "m_GameObject", "m_Enabled", "m_EditorHideFlags",
    "m_Script", "m_Name", "m_EditorClassIdentifier",
}


def _is_object_ref(value: Any) -> bool:
    """Check if a YAML value is a Unity object reference dict."""
    if not isinstance(value, dict):
        return False
    guid = value.get("guid", "")
    return bool(guid) and guid != "0" * 32


_AUDIO_EXTENSIONS: set[str] = {".ogg", ".wav", ".mp3"}


def _process_mono_properties(
    props: dict[str, Any],
    guid_index: guid_resolver.GuidIndex,
    result: dict[Path, dict[str, str]],
) -> None:
    """Extract prefab and audio asset references from a MonoBehaviour's properties."""
    script_ref = props.get("m_Script", {})
    if not isinstance(script_ref, dict):
        return
    script_guid = script_ref.get("guid", "")
    if not script_guid:
        return
    script_path = guid_index.resolve(script_guid)
    if not script_path or script_path.suffix != ".cs":
        return

    for key, value in props.items():
        if key in _MONO_INTERNAL_PROPS or key.startswith("m_"):
            continue
        if not _is_object_ref(value):
            continue

        ref_guid = value["guid"]
        ref_path = guid_index.resolve(ref_guid)
        if not ref_path:
            continue

        if ref_path.suffix == ".prefab":
            # Prefab reference → ReplicatedStorage.Templates:WaitForChild()
            asset_name = ref_path.stem
            refs = result.setdefault(script_path, {})
            if key not in refs:
                refs[key] = asset_name
        elif ref_path.suffix in _AUDIO_EXTENSIONS:
            # AudioClip reference → audio:<filename> (prefixed to distinguish)
            refs = result.setdefault(script_path, {})
            if key not in refs:
                refs[key] = f"audio:{ref_path.name}"


def extract_serialized_field_refs(
    parsed_scenes: list[scene_parser.ParsedScene],
    prefab_lib: prefab_parser.PrefabLibrary,
    guid_index: guid_resolver.GuidIndex,
) -> dict[Path, dict[str, str]]:
    """
    Extract serialized GameObject/prefab references from MonoBehaviour components.

    Walks all scene nodes and prefab template nodes, finds MonoBehaviour
    components, resolves their ``m_Script`` GUID to a ``.cs`` file path, then
    maps each serialized field (whose value is an object reference pointing to a
    ``.prefab`` asset) to the prefab's name.

    Returns:
        ``{script_cs_path: {field_name: prefab_asset_name}}`` mapping, suitable
        for passing to ``code_transpiler.transpile_scripts()``.
    """
    result: dict[Path, dict[str, str]] = {}

    # Process scene MonoBehaviour components
    for scene in parsed_scenes:
        for node in scene.all_nodes.values():
            for comp in node.components:
                if comp.component_type == "MonoBehaviour":
                    _process_mono_properties(comp.properties, guid_index, result)

    # Process prefab template MonoBehaviour components
    def _walk_prefab(pnode: prefab_parser.PrefabNode) -> None:
        for comp in pnode.components:
            if comp.component_type == "MonoBehaviour":
                _process_mono_properties(comp.properties, guid_index, result)
        for child in pnode.children:
            _walk_prefab(child)

    for template in prefab_lib.prefabs:
        if template.root is not None:
            _walk_prefab(template.root)

    return result


# ---------------------------------------------------------------------------
# Prefab instance resolution
# ---------------------------------------------------------------------------

def generate_prefab_packages(
    prefab_lib: prefab_parser.PrefabLibrary,
    output_dir: Path,
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None = None,
    guid_to_companion_scripts: dict[str, list[str]] | None = None,
    guid_index: guid_resolver.GuidIndex | None = None,
    mesh_path_remap: dict[str, str] | None = None,
) -> rbxl_writer.RbxPackageResult:
    """
    Convert each PrefabTemplate into a standalone .rbxm (Roblox model) file.

    Each prefab becomes its own package file under *output_dir*/packages/,
    enabling reuse via the Roblox Toolbox or as linked Packages.

    Args:
        prefab_lib: Parsed prefab library from prefab_parser.
        output_dir: Base output directory; packages are written to output_dir/packages/.
        guid_to_roblox_def: Material GUID → RobloxMaterialDef mapping.
        guid_to_companion_scripts: Material GUID → companion Luau scripts.
        guid_index: GUID index for resolving mesh/asset references.
        mesh_path_remap: Original mesh path → decimated mesh path remap.

    Returns:
        RbxPackageResult with an entry for each prefab written.
    """
    packages_dir = output_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    result = rbxl_writer.RbxPackageResult()

    for template in prefab_lib.prefabs:
        if template.root is None:
            result.warnings.append(f"Skipped prefab '{template.name}': no root node")
            continue

        # Convert prefab node tree → scene node tree → RbxPartEntry tree
        root_scene_node = prefab_node_to_scene_node(template.root)
        directional_lights: list[dict] = []
        root_part = node_to_part(
            root_scene_node,
            guid_to_roblox_def,
            guid_to_companion_scripts,
            guid_index,
            mesh_path_remap,
            directional_lights,
        )

        # Store the template for embedding in ReplicatedStorage.Templates inside the .rbxl
        result.server_storage_templates.append((template.name, root_part))

        # Also write a standalone .rbxm file for Toolbox / manual import
        rbxm_path = packages_dir / f"{template.name}.rbxm"
        entry = rbxl_writer.write_rbxm(
            parts=[root_part],
            scripts=[],
            output_path=rbxm_path,
            model_name=template.name,
        )
        result.packages.append(entry)

    result.total_packages = len(result.packages)
    return result


_MESH_EXTENSIONS: set[str] = {".fbx", ".obj", ".dae"}


def _create_fbx_scene_node(
    asset_path: Path,
    guid: str,
    modifications: list[dict],
) -> scene_parser.SceneNode:
    """Create a SceneNode for a directly-placed FBX/OBJ/DAE model.

    Unity allows dragging mesh files (FBX/OBJ/DAE) directly into a scene.
    The scene stores them as PrefabInstance documents referencing the mesh
    file's GUID instead of a .prefab GUID.  This function creates a minimal
    SceneNode with the correct mesh reference so the model appears in the
    converted output.

    Unity's FBX import uses well-known fileIDs: 100000 for the root
    GameObject and 400000 for its Transform component.  We set these on the
    node so that apply_prefab_modifications() can match the modification
    targets correctly (position, rotation, scale, name).
    """
    name = asset_path.stem
    node = scene_parser.SceneNode(
        name=name,
        file_id="100000",  # Unity FBX root GameObject fileID
        active=True,
        layer=0,
        tag="Untagged",
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        scale=(1.0, 1.0, 1.0),
        mesh_guid=guid,
        from_prefab_instance=True,
    )
    # Add a Transform component with the standard FBX Transform fileID so
    # that apply_prefab_modifications can match m_LocalPosition etc.
    node.components.append(scene_parser.ComponentData(
        component_type="Transform",
        file_id="400000",
        properties={},
    ))
    # Apply position/rotation/scale modifications from the PrefabInstance
    apply_prefab_modifications(node, modifications)
    return node


def resolve_prefab_instances(
    parsed_scenes: list[scene_parser.ParsedScene],
    prefab_lib: prefab_parser.PrefabLibrary,
    guid_index: guid_resolver.GuidIndex,
) -> int:
    """
    Resolve PrefabInstance documents in parsed scenes.

    Handles both .prefab-based instances and direct FBX/OBJ/DAE model
    instances (where Unity stores a mesh file reference as a PrefabInstance).

    Returns the number of prefab instances resolved.
    """
    guid_to_prefab: dict[str, prefab_parser.PrefabTemplate] = {}
    for template in prefab_lib.prefabs:
        prefab_guid = guid_index.guid_for_path(template.prefab_path.resolve())
        if prefab_guid:
            guid_to_prefab[prefab_guid] = template

    resolved = 0
    for scene in parsed_scenes:
        # Build a component fileID → node index so we can resolve
        # transform_parent_file_id (which references Transform components,
        # not GameObjects).
        comp_fid_to_node: dict[str, scene_parser.SceneNode] = {}
        for node in scene.all_nodes.values():
            for comp in node.components:
                comp_fid_to_node[comp.file_id] = node

        for pi in scene.prefab_instances:
            template = guid_to_prefab.get(pi.source_prefab_guid)

            if template is not None and template.root is not None:
                # Standard .prefab resolution
                root_node = prefab_node_to_scene_node(template.root)
                root_node.source_prefab_name = template.name
                apply_prefab_modifications(root_node, pi.modifications)

                scene.referenced_material_guids |= template.referenced_material_guids
                scene.referenced_mesh_guids |= template.referenced_mesh_guids
            else:
                # Fallback: check if source GUID points to a mesh file
                # (FBX/OBJ/DAE placed directly in scene as PrefabInstance)
                asset_path = guid_index.resolve(pi.source_prefab_guid)
                if not asset_path or asset_path.suffix.lower() not in _MESH_EXTENSIONS:
                    continue

                root_node = _create_fbx_scene_node(
                    asset_path, pi.source_prefab_guid, pi.modifications,
                )
                scene.referenced_mesh_guids.add(pi.source_prefab_guid)

            # Look up parent node: transform_parent_file_id may reference a
            # Transform component rather than a GameObject, so check both.
            parent_fid = pi.transform_parent_file_id
            parent_node = None
            if parent_fid:
                parent_node = (
                    scene.all_nodes.get(parent_fid)
                    or comp_fid_to_node.get(parent_fid)
                )
            if parent_node:
                parent_node.children.append(root_node)
            else:
                scene.roots.append(root_node)

            resolved += 1

    return resolved


# ---------------------------------------------------------------------------
# Mesh bounding box extraction
# ---------------------------------------------------------------------------

def _get_fbx_bounds(filepath: str | Path) -> tuple[float, float, float] | None:
    """Extract bounding box from a binary FBX file by parsing vertex arrays.

    FBX stores vertices in centimeters.  We apply a 0.01 scale factor to
    convert to Unity metres (matching Unity's default FBX import behaviour
    with ``useFileScale=1``).
    """
    import struct
    import zlib

    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except OSError:
        return None

    if not data.startswith(b"Kaydara FBX Binary"):
        return None

    min_xyz = [float("inf")] * 3
    max_xyz = [float("-inf")] * 3
    found = False
    idx = 0

    while True:
        idx = data.find(b"Vertices", idx)
        if idx < 0:
            break
        search_start = idx + 8
        for offset in range(search_start, min(search_start + 100, len(data))):
            if data[offset : offset + 1] == b"d":  # double array
                arr_len = struct.unpack_from("<I", data, offset + 1)[0]
                encoding = struct.unpack_from("<I", data, offset + 5)[0]
                comp_len = struct.unpack_from("<I", data, offset + 9)[0]
                if arr_len < 3 or arr_len % 3 != 0:
                    break
                if encoding == 0:
                    raw = data[offset + 13 :]
                elif encoding == 1:
                    try:
                        raw = zlib.decompress(data[offset + 13 : offset + 13 + comp_len])
                    except zlib.error:
                        break
                else:
                    break
                for i in range(0, arr_len, 3):
                    x, y, z = struct.unpack_from("<ddd", raw, i * 8)
                    min_xyz[0] = min(min_xyz[0], x)
                    min_xyz[1] = min(min_xyz[1], y)
                    min_xyz[2] = min(min_xyz[2], z)
                    max_xyz[0] = max(max_xyz[0], x)
                    max_xyz[1] = max(max_xyz[1], y)
                    max_xyz[2] = max(max_xyz[2], z)
                found = True
                break
        idx += 8

    if not found:
        return None

    # FBX centimetres → Unity metres
    scale = 0.01
    return (
        (max_xyz[0] - min_xyz[0]) * scale,
        (max_xyz[1] - min_xyz[1]) * scale,
        (max_xyz[2] - min_xyz[2]) * scale,
    )


def _get_mesh_bounds(mesh_path: str | Path) -> tuple[float, float, float] | None:
    """Read a mesh file and return its bounding box size (x, y, z).

    Uses trimesh for OBJ/DAE/PLY and a binary parser for FBX files.
    """
    mesh_path = Path(mesh_path)

    # Binary FBX parser (trimesh does not support FBX)
    if mesh_path.suffix.lower() == ".fbx":
        return _get_fbx_bounds(mesh_path)

    try:
        import trimesh
        mesh = trimesh.load(str(mesh_path), force="mesh")
        if mesh is None or not hasattr(mesh, "bounds"):
            return None
        bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        size = bounds[1] - bounds[0]
        return (float(size[0]), float(size[1]), float(size[2]))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Scene nodes → parts batch conversion
# ---------------------------------------------------------------------------

def directional_lights_to_lighting(
    dir_lights: list[dict],
) -> rbxl_writer.RbxLightingConfig | None:
    """Build a RbxLightingConfig from collected directional light data.

    Uses the first (primary) directional light for Brightness and ColorShift_Top.
    """
    if not dir_lights:
        return None
    primary = dir_lights[0]
    color = primary["color"]
    intensity = primary["intensity"]
    return rbxl_writer.RbxLightingConfig(
        brightness=min(intensity * 2.0, 10.0),
        ambient=(0.5, 0.5, 0.5),
        color_shift_top=color,
        outdoor_ambient=(
            min(color[0] * 0.5, 1.0),
            min(color[1] * 0.5, 1.0),
            min(color[2] * 0.5, 1.0),
        ),
    )


def _extract_camera_from_scenes(
    parsed_scenes: list[scene_parser.ParsedScene],
    all_nodes: dict[str, scene_parser.SceneNode],
) -> rbxl_writer.RbxCameraConfig | None:
    """Find the first Camera component tagged 'MainCamera' and extract its config."""
    for parsed in parsed_scenes:
        for node in parsed.all_nodes.values():
            for comp in node.components:
                if comp.component_type != "Camera":
                    continue
                # Prefer MainCamera, but accept any camera
                if node.tag == "MainCamera" or not any(
                    n.tag == "MainCamera" for n in parsed.all_nodes.values()
                    if any(c.component_type == "Camera" for c in n.components)
                ):
                    props = comp.properties
                    fov = float(props.get("field of view", props.get("m_FieldOfView",
                                props.get("fieldOfView", 60.0))))
                    near = float(props.get("near clip plane", props.get("m_NearClipPlane", 0.3)))
                    far = float(props.get("far clip plane", props.get("m_FarClipPlane", 1000.0)))
                    return rbxl_writer.RbxCameraConfig(
                        position=node.position,
                        rotation=node.rotation,
                        field_of_view=fov,
                        near_clip=near,
                        far_clip=far,
                    )
    return None


def _extract_skybox_from_scenes(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_index: guid_resolver.GuidIndex | None,
) -> rbxl_writer.RbxSkyboxConfig | None:
    """Extract 6-sided skybox textures from RenderSettings → skybox material."""
    for parsed in parsed_scenes:
        if not parsed.skybox_material_guid or not guid_index:
            continue
        mat_path = guid_index.resolve(parsed.skybox_material_guid)
        if not mat_path or not mat_path.exists():
            continue
        # Parse the skybox .mat for _FrontTex, _BackTex, etc.
        try:
            from modules.material_mapper import _clean_unity_yaml
            import yaml
            raw = mat_path.read_text(encoding="utf-8", errors="replace")
            cleaned = _clean_unity_yaml(raw)
            data = yaml.safe_load(cleaned)
            if not data or "Material" not in data:
                continue
            mat = data["Material"]
            saved = mat.get("m_SavedProperties", {})
            tex_envs_raw = saved.get("m_TexEnvs", []) or []
            # Build tex name → texture ref lookup
            tex_map: dict[str, dict] = {}
            for entry in tex_envs_raw:
                if isinstance(entry, dict):
                    for k, v in entry.items():
                        tex_map[k] = v
            # Skybox face names used by Unity
            _FACE_MAP = {
                "_FrontTex": "front", "_BackTex": "back",
                "_LeftTex": "left", "_RightTex": "right",
                "_UpTex": "up", "_DownTex": "down",
            }
            config = rbxl_writer.RbxSkyboxConfig()
            found_any = False
            for unity_name, rbx_attr in _FACE_MAP.items():
                if unity_name in tex_map:
                    tex_ref = tex_map[unity_name].get("m_Texture", {})
                    if isinstance(tex_ref, dict):
                        tex_guid = tex_ref.get("guid", "")
                        if tex_guid and tex_guid != "0000000000000000f000000000000000":
                            tex_path = guid_index.resolve(tex_guid)
                            if tex_path:
                                setattr(config, rbx_attr, str(tex_path))
                                found_any = True
            if found_any:
                return config
        except Exception:
            continue
    return None


def _detect_unlit_game(
    mat_results: list | None,
) -> bool:
    """Detect if the game is predominantly unlit (all/most materials use unlit shaders)."""
    if not mat_results:
        return False
    unlit_categories = {"urp_unlit", "custom_unlit", "custom_unlit_alpha"}
    total = len(mat_results)
    if total == 0:
        return False
    unlit_count = sum(
        1 for r in mat_results
        if hasattr(r, "pipeline") and r.pipeline == "CUSTOM"
        or (hasattr(r, "shader_name") and "unlit" in r.shader_name.lower())
    )
    return unlit_count / total > 0.7


def _is_ui_subtree(node: scene_parser.SceneNode) -> bool:
    """Return True if the node is a UI root (Canvas) or a container whose
    children are predominantly RectTransform-based UI elements."""
    comp_types = {c.component_type for c in node.components}
    if "Canvas" in comp_types:
        return True
    if node.children:
        rect_count = sum(
            1 for child in node.children
            if any(c.component_type == "RectTransform" for c in child.components)
        )
        if rect_count > len(node.children) * 0.5:
            return True
    return False


_SYSTEM_COMPONENT_TYPES: set[str] = {"Camera", "Light"}


def _is_system_node(node: scene_parser.SceneNode) -> bool:
    """Return True if the node is a Unity system object with no visual output."""
    comp_types = {c.component_type for c in node.components}
    if comp_types & _SYSTEM_COMPONENT_TYPES:
        return True
    if node.name == "EventSystem":
        return True
    return False


def scene_nodes_to_parts(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None = None,
    guid_to_companion_scripts: dict[str, list[str]] | None = None,
    guid_index: guid_resolver.GuidIndex | None = None,
    mesh_path_remap: dict[str, str] | None = None,
    mat_results: list | None = None,
) -> tuple[
    list[rbxl_writer.RbxPartEntry],
    rbxl_writer.RbxLightingConfig | None,
    rbxl_writer.RbxCameraConfig | None,
    rbxl_writer.RbxSkyboxConfig | None,
    list[ComponentWarning],
]:
    """Convert parsed Unity scene nodes into RbxPartEntry objects.

    UI subtrees (Canvas/RectTransform hierarchies) and system nodes
    (Camera, Light, EventSystem) are filtered out — they are handled
    separately by ui_translator and lighting/camera extraction.

    Returns:
        Tuple of (parts, lighting_config, camera_config, skybox_config,
        component_warnings).
    """
    parts: list[rbxl_writer.RbxPartEntry] = []
    directional_lights: list[dict] = []
    component_warnings: list[ComponentWarning] = []
    for parsed in parsed_scenes:
        for node in parsed.roots:
            if _is_ui_subtree(node):
                continue
            if _is_system_node(node):
                # Still extract directional light data from skipped system nodes.
                convert_light_components(
                    rbxl_writer.RbxPartEntry(name=node.name),
                    node.components, directional_lights,
                )
                continue
            parts.append(node_to_part(
                node, guid_to_roblox_def, guid_to_companion_scripts, guid_index,
                mesh_path_remap, directional_lights, component_warnings,
            ))

    lighting = directional_lights_to_lighting(directional_lights)

    # Unlit game detection: boost ambient, reduce brightness
    if _detect_unlit_game(mat_results):
        if lighting is None:
            lighting = rbxl_writer.RbxLightingConfig()
        lighting.brightness = 0.5
        lighting.ambient = (0.85, 0.85, 0.85)
        lighting.outdoor_ambient = (0.85, 0.85, 0.85)

    # Extract camera and skybox
    all_nodes: dict[str, scene_parser.SceneNode] = {}
    for parsed in parsed_scenes:
        all_nodes.update(parsed.all_nodes)
    camera = _extract_camera_from_scenes(parsed_scenes, all_nodes)
    skybox = _extract_skybox_from_scenes(parsed_scenes, guid_index)

    return parts, lighting, camera, skybox, component_warnings


def populate_component_report(
    warnings: list[ComponentWarning],
    report: report_generator.ConversionReport,
    total_components: int | None = None,
) -> None:
    """Populate a ConversionReport's component summary from collected warnings."""
    dropped_by_type: dict[str, int] = {}
    for w in warnings:
        dropped_by_type[w.component_type] = dropped_by_type.get(w.component_type, 0) + 1

    dropped = len(warnings)
    report.components.dropped = dropped
    report.components.dropped_by_type = dropped_by_type
    report.components.dropped_details = [
        {"game_object": w.game_object, "component": w.component_type, "suggestion": w.suggestion}
        for w in warnings
    ]
    if total_components is not None:
        report.components.total_encountered = total_components
        report.components.converted = total_components - dropped
    else:
        report.components.converted = 0
        report.components.total_encountered = dropped

    # Also add top-level warnings for the summary
    for ctype, count in sorted(dropped_by_type.items(), key=lambda x: -x[1]):
        suggestion = _COMPONENT_SUGGESTIONS.get(ctype, "Port manually")
        report.warnings.append(
            f"{ctype}: {count} instance(s) not converted — {suggestion}"
        )


# ---------------------------------------------------------------------------
# Bootstrap script generation
# ---------------------------------------------------------------------------

def _find_monobehaviour_scripts(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_index: guid_resolver.GuidIndex,
) -> list[dict[str, Any]]:
    """Walk scene nodes and collect MonoBehaviour component info with their
    script names and serialized field values.

    Returns a list of dicts:
        {
            "script_name": str,       # e.g. "GameManager"
            "game_object": str,       # owning GameObject name
            "fields": dict[str, Any], # serialized field key→value (raw YAML)
        }
    """
    results: list[dict[str, Any]] = []
    for scene in parsed_scenes:
        for node in scene.all_nodes.values():
            for comp in node.components:
                if comp.component_type != "MonoBehaviour":
                    continue
                script_ref = comp.properties.get("m_Script", {})
                if not isinstance(script_ref, dict):
                    continue
                script_guid = script_ref.get("guid", "")
                if not script_guid:
                    continue
                script_path = guid_index.resolve(script_guid)
                if not script_path or script_path.suffix != ".cs":
                    continue

                fields: dict[str, Any] = {}
                for key, value in comp.properties.items():
                    if key in _MONO_INTERNAL_PROPS or key.startswith("m_"):
                        continue
                    fields[key] = value

                results.append({
                    "script_name": script_path.stem,
                    "game_object": node.name,
                    "fields": fields,
                })
    return results


def _resolve_state_array(
    gm_entry: dict[str, Any],
    mono_entries: list[dict[str, Any]],
    guid_index: guid_resolver.GuidIndex,
) -> list[str]:
    """Resolve the GameManager 'states' array to an ordered list of state
    script names by matching local file-ID references to MonoBehaviours
    in the same scene."""
    states_raw = gm_entry["fields"].get("states", [])
    if not isinstance(states_raw, list):
        return []

    # Build file_id → script_name lookup from all MonoBehaviours
    # (the fileID in a serialized reference points to the component doc)
    fid_to_name: dict[str, str] = {}
    for entry in mono_entries:
        # The component's own file_id is stored on the ComponentData but
        # we don't have it here directly; we try to match via the raw
        # reference fileID in the states array against script names.
        pass

    # Fallback: if the states field contains object references with fileID,
    # resolve them via guid_index. If not resolvable, use a heuristic
    # ordering: LoadoutState first, then GameState, then GameOverState.
    state_names: list[str] = []
    for ref in states_raw:
        if isinstance(ref, dict) and ref.get("guid"):
            path = guid_index.resolve(ref["guid"])
            if path:
                state_names.append(path.stem)

    return state_names


# Well-known state machine classes and their canonical order.
# Used as fallback when Inspector references can't be fully resolved.
_DEFAULT_STATE_ORDER: list[str] = ["LoadoutState", "GameState", "GameOverState"]


def generate_bootstrap_script(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_index: guid_resolver.GuidIndex,
    transpilation: code_transpiler.TranspilationResult,
) -> str | None:
    """Generate a Roblox LocalScript that wires the game's state machine.

    Inspects parsed scenes for a GameManager MonoBehaviour and its serialized
    ``states`` array, then emits a bootstrap script that:
      - Disables Roblox's default character auto-loading
      - Calls ``PlayerData.Create()``
      - Instantiates each game state and registers it with GameManager
      - Connects the Heartbeat update loop
      - Wires UI button callbacks

    Returns the Luau source as a string, or ``None`` if no GameManager was
    found (i.e. the project doesn't use this pattern).
    """
    mono_entries = _find_monobehaviour_scripts(parsed_scenes, guid_index)
    if not mono_entries:
        return None

    # Find the GameManager entry
    gm_entry = None
    for entry in mono_entries:
        if entry["script_name"] == "GameManager":
            gm_entry = entry
            break
    if gm_entry is None:
        return None

    # Resolve states ordering
    state_names = _resolve_state_array(gm_entry, mono_entries, guid_index)
    if not state_names:
        # Fallback: use canonical order, filtered to scripts that actually exist
        transpiled_names = {
            ts.output_filename.replace(".lua", "") for ts in transpilation.scripts
        }
        state_names = [s for s in _DEFAULT_STATE_ORDER if s in transpiled_names]
    if not state_names:
        return None

    # Build require lines and state instantiation
    require_lines: list[str] = []
    state_var_names: list[str] = []
    for name in state_names:
        var = name[0].lower() + name[1:]  # e.g. "loadoutState"
        state_var_names.append(var)
        require_lines.append(
            f'local {name} = require(ReplicatedStorage:WaitForChild("{name}"))'
        )

    instantiation_lines: list[str] = []
    for name, var in zip(state_names, state_var_names):
        # GameState uses .new(config) pattern; others use .new()
        if name == "GameState":
            instantiation_lines.append(f"local {var} = {name}.new({{")
            instantiation_lines.append(f"\ttrackManager = trackManager,")
            instantiation_lines.append(f"}})")
        else:
            instantiation_lines.append(f"local {var} = {name}.new()")

    states_table = "{ " + ", ".join(state_var_names) + " }"

    requires_block = "\n".join(require_lines)
    instantiation_block = "\n".join(instantiation_lines)

    # Identify which other transpiled modules to require
    extra_modules = [
        "PlayerData", "MusicPlayer", "TrackManager",
        "CharacterInputController", "CharacterDatabase",
        "ThemeDatabase", "ConsumableDatabase",
    ]
    transpiled_names = {
        ts.output_filename.replace(".lua", "") for ts in transpilation.scripts
    }
    extra_requires = "\n".join(
        f'local {m} = require(ReplicatedStorage:WaitForChild("{m}"))'
        for m in extra_modules
        if m in transpiled_names
    )

    source = f'''\
-- GameBootstrap.lua (auto-generated)
-- Wires the Unity state-machine lifecycle that the engine handled implicitly:
-- scene loading, Inspector-serialized references, OnEnable/Start/Update calls.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

-- Require transpiled modules
local GameManager = require(ReplicatedStorage:WaitForChild("GameManager"))
{requires_block}
{extra_requires}

---------------------------------------------------------------------------
-- Phase 1: PlayerData (mirrors Unity MusicPlayer.Start -> PlayerData.Create)
---------------------------------------------------------------------------
if PlayerData and PlayerData.PlayerData then
\tPlayerData.PlayerData.Create(player)
elseif PlayerData and PlayerData.Create then
\tPlayerData.Create(player)
end

---------------------------------------------------------------------------
-- Phase 2: TrackManager + CharacterInputController
---------------------------------------------------------------------------
local trackManager
if TrackManager and TrackManager.new then
\ttrackManager = TrackManager.new()
end

local characterController
if CharacterInputController and CharacterInputController.new then
\tcharacterController = CharacterInputController.new()
\tif trackManager then
\t\tcharacterController.trackManager = trackManager
\t\ttrackManager.characterController = characterController
\tend
end

---------------------------------------------------------------------------
-- Phase 3: Instantiate game states (order matches Unity Inspector array)
---------------------------------------------------------------------------
{instantiation_block}

---------------------------------------------------------------------------
-- Phase 4: Assemble and start the GameManager state machine
---------------------------------------------------------------------------
local gameManager = GameManager.new()
gameManager.states = {states_table}
gameManager:Start()

---------------------------------------------------------------------------
-- Phase 5: Character input update loop (replaces Unity's implicit Update)
---------------------------------------------------------------------------
if characterController then
\tRunService.Heartbeat:Connect(function(dt)
\t\tcharacterController:Update(dt)
\tend)
end

---------------------------------------------------------------------------
-- Phase 6: Cleanup
---------------------------------------------------------------------------
player.AncestryChanged:Connect(function()
\tif gameManager then
\t\tgameManager:Destroy()
\tend
end)

print("[GameBootstrap] Initialized — first state: {state_names[0] if state_names else "none"}")
'''
    return source


# ---------------------------------------------------------------------------
# Transpiled scripts → rbxl script entries
# ---------------------------------------------------------------------------

def transpiled_to_rbx_scripts(
    transpilation: code_transpiler.TranspilationResult,
) -> list[rbxl_writer.RbxScriptEntry]:
    """Map TranspiledScript objects to RbxScriptEntry objects for rbxl_writer."""
    entries: list[rbxl_writer.RbxScriptEntry] = []
    for ts in transpilation.scripts:
        entries.append(rbxl_writer.RbxScriptEntry(
            name=ts.output_filename.replace(".lua", ""),
            luau_source=ts.luau_source,
            script_type=ts.script_type,
        ))
    return entries


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(
    unity_path: Path,
    output_dir: Path,
    manifest: Any,
    mat_result: material_mapper.MaterialMapResult,
    scenes: list[scene_parser.ParsedScene],
    prefabs: prefab_parser.PrefabLibrary,
    transpilation: code_transpiler.TranspilationResult,
    write_result: rbxl_writer.RbxWriteResult,
    decimation: mesh_decimator.DecimationResult,
    prefab_instances_resolved: int,
    duration: float,
    errors: list[str],
    package_result: rbxl_writer.RbxPackageResult | None = None,
    component_warnings: list[ComponentWarning] | None = None,
) -> report_generator.ConversionReport:
    """Populate a ConversionReport from pipeline outputs."""
    import config

    rpt = report_generator.ConversionReport(
        unity_project_path=str(unity_path),
        output_dir=str(output_dir),
        duration_seconds=duration,
        success=len(errors) == 0,
        errors=errors,
        warnings=write_result.warnings,
    )

    rpt.assets.total = len(manifest.assets)
    rpt.assets.total_size_bytes = manifest.total_size_bytes
    rpt.assets.by_kind = {k: len(v) for k, v in manifest.by_kind.items()}

    rpt.materials.total = mat_result.total
    rpt.materials.fully_converted = mat_result.fully_converted
    rpt.materials.partially_converted = mat_result.partially_converted
    rpt.materials.unconvertible = mat_result.unconvertible
    rpt.materials.texture_ops = mat_result.texture_ops_performed
    if mat_result.unconverted_md_path:
        rpt.materials.unconverted_md_path = str(mat_result.unconverted_md_path)

    rpt.scripts.total = transpilation.total
    rpt.scripts.succeeded = transpilation.succeeded
    rpt.scripts.flagged_for_review = transpilation.flagged
    rpt.scripts.skipped = transpilation.skipped
    rpt.scripts.ai_transpiled = sum(
        1 for s in transpilation.scripts if s.strategy == "ai"
    )
    rpt.scripts.flagged_scripts = [
        str(s.source_path.name) for s in transpilation.scripts if s.flagged_for_review
    ]

    total_gos = sum(len(s.all_nodes) for s in scenes)
    rpt.scene.scenes_parsed = len(scenes)
    rpt.scene.total_game_objects = total_gos
    rpt.scene.prefabs_parsed = len(prefabs.prefabs)
    rpt.scene.prefab_instances_resolved = prefab_instances_resolved
    rpt.scene.meshes_decimated = decimation.decimated
    rpt.scene.meshes_compliant = decimation.already_compliant

    rpt.output.rbxl_path = str(write_result.output_path)
    rpt.output.parts_written = write_result.parts_written
    rpt.output.scripts_in_place = write_result.scripts_written
    rpt.output.report_path = str(output_dir / config.REPORT_FILENAME)

    if package_result and package_result.total_packages:
        rpt.output.packages.total_packages = package_result.total_packages
        rpt.output.packages.package_names = [
            p.prefab_name for p in package_result.packages
        ]
        rpt.output.packages.packages_dir = str(output_dir / config.PACKAGES_SUBDIR)

    if component_warnings:
        # Count total components across all scenes for the converted/dropped ratio
        total_comps = sum(
            len(n.components)
            for s in scenes
            for n in s.all_nodes.values()
        )
        populate_component_report(component_warnings, rpt, total_comps)

    return rpt
