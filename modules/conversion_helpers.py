"""
conversion_helpers.py — Data conversion helpers for the Unity → Roblox pipeline.

These functions transform parsed Unity data structures into Roblox-ready
objects. They are extracted from converter.py to keep the CLI orchestration
separate from the conversion logic and to make these functions independently
testable.
"""

from __future__ import annotations

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
# Material → SurfaceAppearance bridge
# ---------------------------------------------------------------------------

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
            part.anchored = False
            size = comp.properties.get("m_Size", {})
            if isinstance(size, dict):
                sx = float(size.get("x", 4.0))
                sy = float(size.get("y", 1.0))
                sz = float(size.get("z", 4.0))
                part.size = (sx, sy, sz)
        elif comp.component_type == "SphereCollider":
            part.anchored = False
            radius = float(comp.properties.get("m_Radius", 0.5))
            diameter = radius * 2
            part.size = (diameter, diameter, diameter)
        elif comp.component_type == "CapsuleCollider":
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
) -> None:
    """Convert Unity Light components to Roblox light child tuples."""
    for comp in components:
        if comp.component_type != "Light":
            continue
        props = comp.properties
        light_type = int(props.get("m_Type", 2))
        color_data = props.get("m_Color", {})
        color = (
            float(color_data.get("r", 1.0)) if isinstance(color_data, dict) else 1.0,
            float(color_data.get("g", 1.0)) if isinstance(color_data, dict) else 1.0,
            float(color_data.get("b", 1.0)) if isinstance(color_data, dict) else 1.0,
        )
        intensity = float(props.get("m_Intensity", 1.0))
        range_val = float(props.get("m_Range", 10.0))
        shadows = int(props.get("m_Shadows", {}).get("m_Type", 0) if isinstance(props.get("m_Shadows"), dict) else props.get("m_Shadows", 0))
        spot_angle = float(props.get("m_SpotAngle", 30.0))

        if light_type == 0:  # Spot
            part.light_children.append(("SpotLight", color, intensity, range_val, bool(shadows), spot_angle))
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
        loop = bool(props.get("m_Loop", 0))
        play_on_awake = bool(props.get("m_PlayOnAwake", 1))
        min_dist = float(props.get("m_MinDistance", 1.0))
        max_dist = float(props.get("m_MaxDistance", 500.0))

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
        p_color = (
            float(color_data.get("r", 1.0)) / 255.0 if float(color_data.get("r", 1.0)) > 1 else float(color_data.get("r", 1.0)),
            float(color_data.get("g", 1.0)) / 255.0 if float(color_data.get("g", 1.0)) > 1 else float(color_data.get("g", 1.0)),
            float(color_data.get("b", 1.0)) / 255.0 if float(color_data.get("b", 1.0)) > 1 else float(color_data.get("b", 1.0)),
        ) if isinstance(color_data, dict) else (1.0, 1.0, 1.0)

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
) -> None:
    """Attach material data and companion scripts to a part from a scene node."""
    if not guid_to_roblox_def:
        return
    for comp in node.components:
        if comp.component_type not in ("MeshRenderer", "SkinnedMeshRenderer"):
            continue
        for mat_ref in comp.properties.get("m_Materials", []):
            if not isinstance(mat_ref, dict):
                continue
            guid = mat_ref.get("guid", "")
            rdef = guid_to_roblox_def.get(guid)
            if rdef:
                part.surface_appearance = roblox_def_to_surface_appearance(rdef)
                if rdef.base_part_color:
                    part.color3 = rdef.base_part_color
                if rdef.base_part_transparency > 0:
                    part.transparency = rdef.base_part_transparency
                if guid_to_companion_scripts:
                    for i, src in enumerate(guid_to_companion_scripts.get(guid, ())):
                        suffix = f"_{i+1}" if i > 0 else ""
                        part.scripts.append(rbxl_writer.RbxScriptEntry(
                            name=f"{node.name}_MaterialEffect{suffix}",
                            luau_source=src,
                            script_type="Script",
                        ))
                break  # use first material for the part


# ---------------------------------------------------------------------------
# SceneNode → RbxPartEntry conversion
# ---------------------------------------------------------------------------

def node_to_part(
    node: scene_parser.SceneNode,
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None,
    guid_to_companion_scripts: dict[str, list[str]] | None,
    guid_index: guid_resolver.GuidIndex | None,
    mesh_path_remap: dict[str, str] | None = None,
) -> rbxl_writer.RbxPartEntry:
    """Convert a single SceneNode (and its children recursively) to an RbxPartEntry."""
    base_size = (1.0, 1.0, 1.0)
    scaled_size = (
        base_size[0] * abs(node.scale[0]),
        base_size[1] * abs(node.scale[1]),
        base_size[2] * abs(node.scale[2]),
    )
    part = rbxl_writer.RbxPartEntry(
        name=node.name,
        position=node.position,
        rotation=node.rotation,
        size=scaled_size,
        anchored=True,
    )

    # Set mesh_id from the node's mesh GUID via the GUID index.
    if node.mesh_guid and guid_index:
        mesh_path = guid_index.resolve(node.mesh_guid)
        if mesh_path:
            mesh_str = str(mesh_path)
            if mesh_path_remap and mesh_str in mesh_path_remap:
                mesh_str = mesh_path_remap[mesh_str]
            part.mesh_id = mesh_str

    # Apply component conversions
    apply_collider_properties(part, node.components)
    convert_light_components(part, node.components)
    convert_audio_components(part, node.name, node.components, guid_index)
    convert_particle_components(part, node.name, node.components)
    apply_materials(part, node, guid_to_roblox_def, guid_to_companion_scripts)

    # Recurse into children to preserve hierarchy
    for child in node.children:
        part.children.append(node_to_part(
            child, guid_to_roblox_def, guid_to_companion_scripts, guid_index,
            mesh_path_remap,
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
# Prefab instance resolution
# ---------------------------------------------------------------------------

def resolve_prefab_instances(
    parsed_scenes: list[scene_parser.ParsedScene],
    prefab_lib: prefab_parser.PrefabLibrary,
    guid_index: guid_resolver.GuidIndex,
) -> int:
    """
    Resolve PrefabInstance documents in parsed scenes.

    Returns the number of prefab instances resolved.
    """
    guid_to_prefab: dict[str, prefab_parser.PrefabTemplate] = {}
    for template in prefab_lib.prefabs:
        prefab_guid = guid_index.guid_for_path(template.prefab_path.resolve())
        if prefab_guid:
            guid_to_prefab[prefab_guid] = template

    resolved = 0
    for scene in parsed_scenes:
        for pi in scene.prefab_instances:
            template = guid_to_prefab.get(pi.source_prefab_guid)
            if template is None or template.root is None:
                continue

            root_node = prefab_node_to_scene_node(template.root)
            apply_prefab_modifications(root_node, pi.modifications)

            scene.referenced_material_guids |= template.referenced_material_guids
            scene.referenced_mesh_guids |= template.referenced_mesh_guids

            parent_fid = pi.transform_parent_file_id
            parent_node = scene.all_nodes.get(parent_fid) if parent_fid else None
            if parent_node:
                parent_node.children.append(root_node)
            else:
                scene.roots.append(root_node)

            resolved += 1

    return resolved


# ---------------------------------------------------------------------------
# Scene nodes → parts batch conversion
# ---------------------------------------------------------------------------

def scene_nodes_to_parts(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None = None,
    guid_to_companion_scripts: dict[str, list[str]] | None = None,
    guid_index: guid_resolver.GuidIndex | None = None,
    mesh_path_remap: dict[str, str] | None = None,
) -> list[rbxl_writer.RbxPartEntry]:
    """Convert parsed Unity scene nodes into RbxPartEntry objects."""
    parts: list[rbxl_writer.RbxPartEntry] = []
    for parsed in parsed_scenes:
        for node in parsed.roots:
            parts.append(node_to_part(
                node, guid_to_roblox_def, guid_to_companion_scripts, guid_index,
                mesh_path_remap,
            ))
    return parts


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
    rpt.scripts.rule_based = sum(
        1 for s in transpilation.scripts if s.strategy == "rule_based"
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

    return rpt
