"""
converter.py — Orchestrator for the Unity → Roblox conversion pipeline.

This is the single entry point that wires all pipeline modules together:

  Phase 1 — Discovery (lightweight YAML reads):
    1. scene_parser     → parses .unity scene files, extracts material GUIDs
    2. prefab_parser    → parses .prefab files, extracts material GUIDs

  Phase 2 — Asset inventory + GUID resolution:
    3. asset_extractor  → discovers and catalogues Unity assets
    4. guid_resolver    → builds full bidirectional GUID ↔ asset-path index

  Phase 3 — Heavy processing (informed by Phases 1 & 2):
    5. material_mapper  → parses .mat files, converts to Roblox materials
    6. code_transpiler  → converts C# MonoBehaviours to Luau scripts
    7. mesh_decimator   → conservative decimation for Roblox polygon limits

  Phase 4 — Assembly:
    8. rbxl_writer      → writes the final .rbxl Roblox place file

  Phase 5 — Portal upload (optional, requires Roblox API key):
    9. roblox_uploader  → uploads .rbxl + textures to Roblox Open Cloud
   10. report_generator → produces a JSON + stdout conversion report

Scenes and prefabs are parsed first so material mapping can be filtered to
only the materials actually referenced by MeshRenderer components.

Data flows linearly: each step's output is passed explicitly to the next.
No module imports another module — all wiring happens here.
"""

from __future__ import annotations

import time
from pathlib import Path

import click

import config
from modules import (
    asset_extractor,
    guid_resolver,
    material_mapper,
    mesh_decimator,
    scene_parser,
    prefab_parser,
    code_transpiler,
    roblox_uploader,
    rbxl_writer,
    report_generator,
)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _roblox_def_to_surface_appearance(
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


def _scene_nodes_to_parts(
    parsed_scenes: list[scene_parser.ParsedScene],
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None = None,
    guid_to_companion_scripts: dict[str, list[str]] | None = None,
) -> list[rbxl_writer.RbxPartEntry]:
    """
    Convert parsed Unity scene nodes into RbxPartEntry objects.

    Each root SceneNode becomes a BasePart in Roblox Workspace.
    Position is mapped directly (Unity Y-up == Roblox Y-up).

    Args:
        parsed_scenes: Parsed scene data.
        guid_to_roblox_def: Optional mapping from material GUID directly to
            RobloxMaterialDef.  Built by the caller from the GUID index +
            path-keyed roblox_defs, so there is no name-based indirection.
        guid_to_companion_scripts: Optional mapping from material GUID to
            Luau companion scripts (e.g. blinking/rotation effects) that
            should be parented to the part using that material.
    """
    parts: list[rbxl_writer.RbxPartEntry] = []
    for parsed in parsed_scenes:
        for node in parsed.roots:
            part = rbxl_writer.RbxPartEntry(
                name=node.name,
                position=node.position,
                size=(4.0, 1.0, 4.0),  # default size; real size from MeshRenderer bounds
                anchored=True,
            )

            # Attach material data and companion scripts if available
            if guid_to_roblox_def:
                for comp in node.components:
                    if comp.component_type not in ("MeshRenderer", "SkinnedMeshRenderer"):
                        continue
                    for mat_ref in comp.properties.get("m_Materials", []):
                        if not isinstance(mat_ref, dict):
                            continue
                        guid = mat_ref.get("guid", "")
                        rdef = guid_to_roblox_def.get(guid)
                        if rdef:
                            part.surface_appearance = _roblox_def_to_surface_appearance(rdef)
                            if rdef.base_part_color:
                                part.color3 = rdef.base_part_color
                            if rdef.base_part_transparency > 0:
                                part.transparency = rdef.base_part_transparency
                            # Attach companion scripts to this part
                            if guid_to_companion_scripts:
                                for i, src in enumerate(guid_to_companion_scripts.get(guid, ())):
                                    suffix = f"_{i+1}" if i > 0 else ""
                                    part.scripts.append(rbxl_writer.RbxScriptEntry(
                                        name=f"{node.name}_MaterialEffect{suffix}",
                                        luau_source=src,
                                        script_type="Script",
                                    ))
                            break  # use first material for the part

            parts.append(part)
    return parts


def _transpiled_to_rbx_scripts(
    transpilation: code_transpiler.TranspilationResult,
) -> list[rbxl_writer.RbxScriptEntry]:
    """Map TranspiledScript objects to RbxScriptEntry objects for rbxl_writer."""
    entries: list[rbxl_writer.RbxScriptEntry] = []
    for ts in transpilation.scripts:
        entries.append(rbxl_writer.RbxScriptEntry(
            name=ts.output_filename.replace(".lua", ""),
            luau_source=ts.luau_source,
            script_type="Script",
        ))
    return entries


def _build_report(
    unity_path: Path,
    output_dir: Path,
    manifest: asset_extractor.AssetManifest,
    mat_result: material_mapper.MaterialMapResult,
    scenes: list[scene_parser.ParsedScene],
    prefabs: prefab_parser.PrefabLibrary,
    transpilation: code_transpiler.TranspilationResult,
    write_result: rbxl_writer.RbxWriteResult,
    duration: float,
    errors: list[str],
) -> report_generator.ConversionReport:
    """Populate a ConversionReport from pipeline outputs."""
    rpt = report_generator.ConversionReport(
        unity_project_path=str(unity_path),
        output_dir=str(output_dir),
        duration_seconds=duration,
        success=len(errors) == 0,
        errors=errors,
        warnings=write_result.warnings,
    )

    # Assets
    rpt.assets.total = len(manifest.assets)
    rpt.assets.total_size_bytes = manifest.total_size_bytes
    rpt.assets.by_kind = {k: len(v) for k, v in manifest.by_kind.items()}

    # Materials
    rpt.materials.total = mat_result.total
    rpt.materials.fully_converted = mat_result.fully_converted
    rpt.materials.partially_converted = mat_result.partially_converted
    rpt.materials.unconvertible = mat_result.unconvertible
    rpt.materials.texture_ops = mat_result.texture_ops_performed
    if mat_result.unconverted_md_path:
        rpt.materials.unconverted_md_path = str(mat_result.unconverted_md_path)

    # Scripts
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

    # Scene
    total_gos = sum(len(s.all_nodes) for s in scenes)
    rpt.scene.scenes_parsed = len(scenes)
    rpt.scene.total_game_objects = total_gos
    rpt.scene.prefabs_parsed = len(prefabs.prefabs)

    # Output
    rpt.output.rbxl_path = str(write_result.output_path)
    rpt.output.parts_written = write_result.parts_written
    rpt.output.scripts_in_place = write_result.scripts_written
    rpt.output.report_path = str(output_dir / config.REPORT_FILENAME)

    return rpt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
@click.option("--use-ai/--no-ai", default=config.USE_AI_TRANSPILATION,
              help="Use Claude for C# → Luau transpilation.")
@click.option("--api-key", default=config.ANTHROPIC_API_KEY, envvar="ANTHROPIC_API_KEY",
              help="Anthropic API key (or set ANTHROPIC_API_KEY env var).")
@click.option("--verbose/--no-verbose", default=config.REPORT_VERBOSE,
              help="Include per-script detail in the report.")
@click.option("--roblox-api-key", default=config.ROBLOX_API_KEY, envvar="ROBLOX_API_KEY",
              help="Roblox Open Cloud API key (required for portal upload).")
@click.option("--universe-id", default=config.ROBLOX_UNIVERSE_ID, type=int,
              help="Roblox universe (experience) ID for upload.")
@click.option("--place-id", default=config.ROBLOX_PLACE_ID, type=int,
              help="Roblox place ID for upload.")
@click.option("--decimate/--no-decimate", default=config.MESH_DECIMATION_ENABLED,
              help="Decimate meshes exceeding Roblox polygon limits.")
def convert(
    unity_project_path: str,
    output_dir: str,
    use_ai: bool,
    api_key: str,
    verbose: bool,
    roblox_api_key: str,
    universe_id: int | None,
    place_id: int | None,
    decimate: bool,
) -> None:
    """
    Convert a Unity project at UNITY_PROJECT_PATH to a Roblox place in OUTPUT_DIR.

    \b
    Example:
        python converter.py ./MyUnityGame ./roblox_output
        python converter.py ./MyUnityGame ./out --roblox-api-key KEY --universe-id 123 --place-id 456
    """
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    t_start = time.monotonic()

    # ------------------------------------------------------------------
    # Phase 1 — Discovery (lightweight YAML reads)
    # ------------------------------------------------------------------

    click.echo("🗺   Parsing scenes …")
    parsed_scenes: list[scene_parser.ParsedScene] = []
    for scene_file in unity_path.rglob("*.unity"):
        try:
            parsed_scenes.append(scene_parser.parse_scene(scene_file))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Scene parse error ({scene_file.name}): {exc}")
    click.echo(f"    → {len(parsed_scenes)} scene(s) parsed")

    click.echo("🧩  Parsing prefabs …")
    try:
        prefabs = prefab_parser.parse_prefabs(unity_path)
        click.echo(f"    → {len(prefabs.prefabs)} prefab(s) found")
    except FileNotFoundError as exc:
        errors.append(str(exc))
        prefabs = prefab_parser.PrefabLibrary()

    # Collect material GUIDs referenced by scenes and prefabs
    referenced_guids: set[str] = set()
    for ps in parsed_scenes:
        referenced_guids |= ps.referenced_material_guids
    referenced_guids |= prefabs.referenced_material_guids

    # ------------------------------------------------------------------
    # Phase 2 — Asset inventory + GUID resolution
    # ------------------------------------------------------------------

    click.echo(f"🔍  Extracting assets from {unity_path} …")
    try:
        manifest = asset_extractor.extract_assets(
            unity_path,
            supported_extensions=config.SUPPORTED_ASSET_EXTENSIONS,
        )
        click.echo(f"    → {len(manifest.assets)} assets found "
                   f"({manifest.total_size_bytes / 1_048_576:.1f} MB)")
    except FileNotFoundError as exc:
        errors.append(str(exc))
        manifest = asset_extractor.AssetManifest(unity_project_path=unity_path)

    click.echo("🔗  Building GUID index …")
    try:
        guid_index = guid_resolver.build_guid_index(unity_path)
        click.echo(f"    → {guid_index.total_resolved} GUIDs resolved "
                   f"from {guid_index.total_meta_files} .meta files")
        if guid_index.duplicate_guids:
            click.echo(f"    → {len(guid_index.duplicate_guids)} duplicate GUID(s) detected")
        if guid_index.orphan_metas:
            click.echo(f"    → {len(guid_index.orphan_metas)} orphan .meta file(s)")
    except FileNotFoundError as exc:
        errors.append(str(exc))
        guid_index = guid_resolver.GuidIndex(project_root=unity_path)

    # ------------------------------------------------------------------
    # Phase 3 — Heavy processing (informed by Phase 1 & 2)
    # ------------------------------------------------------------------

    click.echo("🎨  Mapping materials …")
    try:
        mat_result = material_mapper.map_materials(
            unity_path, out_dir,
            referenced_guids=referenced_guids or None,
        )
        click.echo(f"    → {mat_result.total} material(s): "
                   f"{mat_result.fully_converted} full, "
                   f"{mat_result.partially_converted} partial, "
                   f"{mat_result.unconvertible} unconvertible")
        if mat_result.texture_ops_performed:
            click.echo(f"    → {mat_result.texture_ops_performed} texture operation(s)")
        if mat_result.unconverted_md_path:
            click.echo(f"    → UNCONVERTED.md written to {mat_result.unconverted_md_path}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Material mapping error: {exc}")
        mat_result = material_mapper.MaterialMapResult()

    click.echo("📝  Transpiling C# scripts …")
    try:
        transpilation = code_transpiler.transpile_scripts(
            unity_path,
            use_ai=use_ai,
            api_key=api_key,
            model=config.ANTHROPIC_MODEL,
            max_tokens=config.ANTHROPIC_MAX_TOKENS,
            confidence_threshold=config.TRANSPILATION_CONFIDENCE_THRESHOLD,
        )
        click.echo(f"    → {transpilation.total} script(s): "
                   f"{transpilation.succeeded} OK, {transpilation.flagged} flagged")
    except FileNotFoundError as exc:
        errors.append(str(exc))
        transpilation = code_transpiler.TranspilationResult()

    # ── Mesh decimation (conservative) ─────────────────────────────
    decimation_result = mesh_decimator.DecimationResult()
    if decimate:
        mesh_entries = manifest.by_kind.get("mesh", [])
        mesh_paths = [e.path for e in mesh_entries]
        if mesh_paths:
            click.echo(f"🔺  Decimating meshes ({len(mesh_paths)} file(s)) …")
            meshes_out = out_dir / "meshes"
            decimation_result = mesh_decimator.decimate_meshes(
                mesh_paths=mesh_paths,
                output_dir=meshes_out,
                target_faces=config.MESH_TARGET_FACES,
                quality_floor=config.MESH_QUALITY_FLOOR,
                roblox_max_faces=config.MESH_ROBLOX_MAX_FACES,
            )
            click.echo(f"    → {decimation_result.total_meshes} mesh(es): "
                       f"{decimation_result.already_compliant} compliant, "
                       f"{decimation_result.decimated} decimated, "
                       f"{decimation_result.skipped} skipped")
            for w in decimation_result.warnings:
                click.echo(f"    ⚠ {w}")

    # ------------------------------------------------------------------
    # Phase 4 — Assembly
    # ------------------------------------------------------------------

    # Build GUID → RobloxMaterialDef and GUID → companion scripts directly
    # via the GUID index.  Both maps are keyed by material file path (unique),
    # and the GUID index maps each GUID to its asset path, so the join is
    # exact — no name-based indirection.
    guid_to_roblox_def: dict[str, material_mapper.RobloxMaterialDef] | None = None
    guid_to_companion: dict[str, list[str]] | None = None
    if mat_result.roblox_defs or mat_result.companion_scripts:
        guid_to_roblox_def = {}
        guid_to_companion = {}
        for guid, entry in guid_index.guid_to_entry.items():
            rdef = mat_result.roblox_defs.get(entry.asset_path)
            if rdef is not None:
                guid_to_roblox_def[guid] = rdef
            scripts = mat_result.companion_scripts.get(entry.asset_path)
            if scripts:
                guid_to_companion[guid] = scripts

    click.echo("🏗   Writing .rbxl …")
    parts = _scene_nodes_to_parts(
        parsed_scenes,
        guid_to_roblox_def=guid_to_roblox_def,
        guid_to_companion_scripts=guid_to_companion,
    )
    rbx_scripts = _transpiled_to_rbx_scripts(transpilation)
    rbxl_path = out_dir / config.RBXL_OUTPUT_FILENAME

    write_result = rbxl_writer.write_rbxl(
        parts=parts,
        scripts=rbx_scripts,
        output_path=rbxl_path,
        place_name=unity_path.name,
    )
    click.echo(f"    → Written to {write_result.output_path}")

    # ------------------------------------------------------------------
    # Phase 5 — Portal upload (requires Roblox API key)
    # ------------------------------------------------------------------

    click.echo("☁️   Checking Roblox upload …")
    textures_dir = out_dir / "textures" if (out_dir / "textures").is_dir() else None
    upload_result = roblox_uploader.upload_to_roblox(
        rbxl_path=rbxl_path,
        textures_dir=textures_dir,
        api_key=roblox_api_key,
        universe_id=universe_id,
        place_id=place_id,
    )
    if upload_result.skipped:
        for w in upload_result.warnings:
            click.echo(f"    → {w}")
    elif upload_result.success:
        click.echo(f"    → Uploaded to place {upload_result.place_id} "
                   f"(version {upload_result.version_number})")
        if upload_result.asset_ids:
            click.echo(f"    → {len(upload_result.asset_ids)} texture(s) uploaded")
    else:
        for err in upload_result.errors:
            click.echo(f"    ✗ {err}")
            errors.append(err)

    duration = time.monotonic() - t_start

    rpt = _build_report(
        unity_path, out_dir, manifest, mat_result, parsed_scenes,
        prefabs, transpilation, write_result, duration, errors,
    )

    report_path = out_dir / config.REPORT_FILENAME
    report_generator.generate_report(
        rpt,
        output_path=report_path,
        verbose=verbose,
        print_summary=True,
    )


if __name__ == "__main__":
    convert()
