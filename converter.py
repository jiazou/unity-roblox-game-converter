"""
converter.py — Batch (non-interactive) orchestrator for the Unity → Roblox pipeline.

This runs ALL phases end-to-end without stopping.  For the interactive,
human-in-the-loop version that pauses at decision points, use the
/convert-unity Claude Code skill (backed by convert_interactive.py).

Phases:

  1. Discovery    — scene_parser + prefab_parser
  2. Inventory    — asset_extractor + guid_resolver
  3. Processing   — material_mapper + code_transpiler + mesh_decimator
  3b. Bootstrap   — generate_bootstrap_script (wires state machine lifecycle)
  4. Assembly     — rbxl_writer
  5. Upload       — roblox_uploader + report_generator

Data flows linearly: each step's output is passed explicitly to the next.
No module imports another module — all wiring happens here.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import click

import config
from modules import (
    animation_converter,
    asset_extractor,
    bridge_injector,
    code_validator,
    guid_resolver,
    material_mapper,
    mesh_decimator,
    scene_parser,
    prefab_parser,
    code_transpiler,
    roblox_uploader,
    rbxl_writer,
    report_generator,
    scriptable_object_converter,
    sprite_extractor,
    ui_translator,
)
from modules.conversion_helpers import (
    resolve_prefab_instances as _resolve_prefab_instances,
    extract_serialized_field_refs as _extract_serialized_field_refs,
    generate_prefab_packages as _generate_prefab_packages,
    generate_bootstrap_script as _generate_bootstrap_script,
    scene_nodes_to_parts as _scene_nodes_to_parts,
    transpiled_to_rbx_scripts as _transpiled_to_rbx_scripts,
    build_report as _build_report,
)
from modules.retry import call_with_retry


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
@click.option("--api-key", default=config.ANTHROPIC_API_KEY, envvar="ANTHROPIC_API_KEY",
              help="Anthropic API key for C# → Luau transpilation (required, or set ANTHROPIC_API_KEY env var).")
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
@click.option("--emit-packages/--no-packages", default=config.EMIT_PACKAGES,
              help="Generate .rbxm package files for each prefab.")
def convert(
    unity_project_path: str,
    output_dir: str,
    api_key: str,
    verbose: bool,
    roblox_api_key: str,
    universe_id: int | None,
    place_id: int | None,
    decimate: bool,
    emit_packages: bool,
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

    if not api_key or api_key.startswith("sk-ant-PLACEHOLDER"):
        raise click.UsageError(
            "An Anthropic API key is required for C# → Luau transpilation. "
            "Set --api-key or the ANTHROPIC_API_KEY environment variable."
        )

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

    # ── Resolve prefab instances in scenes ────────────────────────
    click.echo("🧩  Resolving prefab instances …")
    total_pi = sum(len(s.prefab_instances) for s in parsed_scenes)
    resolved_count = 0
    if total_pi and prefabs.prefabs:
        resolved_count = _resolve_prefab_instances(parsed_scenes, prefabs, guid_index)
        click.echo(f"    → {resolved_count}/{total_pi} prefab instance(s) resolved")
        # Update referenced material GUIDs (prefab instances may add new ones)
        for ps in parsed_scenes:
            referenced_guids |= ps.referenced_material_guids
    else:
        click.echo(f"    → {total_pi} instance(s), nothing to resolve")

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

    # ── Extract serialized field references for transpiler ──────
    serialized_refs = _extract_serialized_field_refs(parsed_scenes, prefabs, guid_index)
    if serialized_refs:
        total_fields = sum(len(v) for v in serialized_refs.values())
        click.echo(f"🔗  Extracted {total_fields} serialized prefab reference(s) "
                   f"across {len(serialized_refs)} script(s)")

    click.echo("📝  Transpiling C# scripts …")
    try:
        scripts_cache = out_dir / "scripts"
        transpilation = code_transpiler.transpile_scripts(
            unity_path,
            api_key=api_key,
            model=config.ANTHROPIC_MODEL,
            max_tokens=config.ANTHROPIC_MAX_TOKENS,
            confidence_threshold=config.TRANSPILATION_CONFIDENCE_THRESHOLD,
            serialized_refs=serialized_refs or None,
            transpile_cache_dir=scripts_cache if scripts_cache.is_dir() else None,
        )
        click.echo(f"    → {transpilation.total} script(s): "
                   f"{transpilation.succeeded} OK, {transpilation.flagged} flagged")
    except FileNotFoundError as exc:
        errors.append(str(exc))
        transpilation = code_transpiler.TranspilationResult()

    # ── Validate generated Luau code ──────────────────────────────
    validation_errors = 0
    validation_warnings = 0
    for ts in transpilation.scripts:
        vr = code_validator.validate_luau(ts.luau_source, ts.output_filename)
        if not vr.valid:
            validation_errors += vr.error_count
            ts.flagged_for_review = True
            ts.warnings.extend(
                f"[{i.code}] L{i.line}: {i.message}" for i in vr.issues
                if i.severity == "error"
            )
        validation_warnings += vr.warning_count
    if validation_errors or validation_warnings:
        click.echo(f"    → Luau validation: {validation_errors} error(s), "
                   f"{validation_warnings} warning(s)")

    # ── ScriptableObject .asset → ModuleScript data tables ─────────
    click.echo("📦  Converting ScriptableObject data assets …")
    so_result = scriptable_object_converter.convert_asset_files(unity_path)
    if so_result.total:
        click.echo(f"    → {so_result.converted}/{so_result.total} .asset file(s) → ModuleScript data")
        # Add converted ScriptableObjects as ModuleScripts
        for ca in so_result.assets:
            transpilation.scripts.append(code_transpiler.TranspiledScript(
                source_path=ca.source_path,
                output_filename=ca.asset_name + "_Data.lua",
                csharp_source="",
                luau_source=ca.luau_source,
                strategy="ai",
                confidence=1.0,
                script_type="ModuleScript",
            ))

    # ── Animation conversion (Animator → config tables + bridge) ────
    click.echo("🎭  Converting animations …")
    anim_result = animation_converter.convert_animations(
        parsed_scenes, guid_index, unity_path,
    )
    if anim_result.animators_found:
        click.echo(f"    → {anim_result.animators_found} Animator(s) found, "
                   f"{anim_result.animators_converted} converted")
        for mod_name, mod_source in anim_result.config_modules:
            transpilation.scripts.append(code_transpiler.TranspiledScript(
                source_path=Path("(generated)"),
                output_filename=f"{mod_name}.lua",
                csharp_source="",
                luau_source=mod_source,
                strategy="ai",
                confidence=1.0,
                script_type="ModuleScript",
            ))
        if anim_result.bridge_needed:
            bridge_path = Path(__file__).parent / "bridge" / "AnimatorBridge.lua"
            if bridge_path.exists():
                transpilation.scripts.append(code_transpiler.TranspiledScript(
                    source_path=Path("(generated)"),
                    output_filename="AnimatorBridge.lua",
                    csharp_source="",
                    luau_source=bridge_path.read_text(encoding="utf-8"),
                    strategy="ai",
                    confidence=1.0,
                    script_type="ModuleScript",
                ))
                click.echo("    → AnimatorBridge.lua added (ModuleScript in ReplicatedStorage)")
        for w in anim_result.warnings:
            click.echo(f"    ⚠ {w}")
    else:
        click.echo("    → No Animator components found")

    # ── Transform animation conversion (Legacy Animation → config + bridge) ──
    click.echo("🔄  Converting transform animations …")
    transform_result = animation_converter.convert_transform_animations(
        parsed_scenes, guid_index, unity_path, prefab_library=prefabs,
    )
    if transform_result.anims_found:
        click.echo(f"    → {transform_result.anims_found} Legacy Animation(s) found, "
                   f"{transform_result.anims_converted} converted")
        for mod_name, mod_source in transform_result.config_modules:
            transpilation.scripts.append(code_transpiler.TranspiledScript(
                source_path=Path("(generated)"),
                output_filename=f"{mod_name}.lua",
                csharp_source="",
                luau_source=mod_source,
                strategy="ai",
                confidence=1.0,
                script_type="ModuleScript",
            ))
        if transform_result.bridge_needed:
            bridge_path = Path(__file__).parent / "bridge" / "TransformAnimator.lua"
            if bridge_path.exists():
                transpilation.scripts.append(code_transpiler.TranspiledScript(
                    source_path=Path("(generated)"),
                    output_filename="TransformAnimator.lua",
                    csharp_source="",
                    luau_source=bridge_path.read_text(encoding="utf-8"),
                    strategy="ai",
                    confidence=1.0,
                    script_type="ModuleScript",
                ))
                click.echo("    → TransformAnimator.lua added (ModuleScript in ReplicatedStorage)")
        for w in transform_result.warnings:
            click.echo(f"    ⚠ {w}")
    else:
        click.echo("    → No Legacy Animation components found")

    # ── Auto-inject bridge modules based on transpiled code usage ─────
    existing_scripts = {ts.output_filename for ts in transpilation.scripts}
    all_luau = [ts.luau_source for ts in transpilation.scripts]
    bridge_result = bridge_injector.detect_needed_bridges(all_luau, existing_scripts)
    if bridge_result.needed:
        for filename, source in bridge_injector.inject_bridges(bridge_result.needed):
            transpilation.scripts.append(code_transpiler.TranspiledScript(
                source_path=Path("(generated)"),
                output_filename=filename,
                csharp_source="",
                luau_source=source,
                strategy="ai",
                confidence=1.0,
                script_type="ModuleScript",
            ))
        click.echo(f"🔌  Bridge modules auto-injected: {', '.join(bridge_result.needed)}")

    # ── Bootstrap script generation ──────────────────────────────────
    click.echo("🎬  Generating bootstrap script …")
    bootstrap_source = _generate_bootstrap_script(parsed_scenes, guid_index, transpilation)
    if bootstrap_source:
        transpilation.scripts.append(code_transpiler.TranspiledScript(
            source_path=Path("(generated)"),
            output_filename="GameBootstrap.lua",
            csharp_source="",
            luau_source=bootstrap_source,
            strategy="ai",
            confidence=1.0,
            script_type="LocalScript",
        ))
        click.echo("    → GameBootstrap.lua added (LocalScript in StarterPlayerScripts)")
    else:
        click.echo("    → No GameManager found, skipping bootstrap generation")

    # ── Mesh processing (copy + optional decimation) ────────────────
    decimation_result = mesh_decimator.DecimationResult()
    mesh_entries = manifest.by_kind.get("mesh", [])
    mesh_paths = [e.path for e in mesh_entries]
    if mesh_paths:
        meshes_out = out_dir / "meshes"
        if decimate:
            click.echo(f"🔺  Decimating meshes ({len(mesh_paths)} file(s)) …")
            decimation_result = mesh_decimator.decimate_meshes(
                mesh_paths=mesh_paths,
                output_dir=meshes_out,
                target_faces=config.MESH_TARGET_FACES,
                quality_floor=config.MESH_QUALITY_FLOOR,
                roblox_max_faces=config.MESH_ROBLOX_MAX_FACES,
            )
        else:
            click.echo(f"🔺  Copying meshes ({len(mesh_paths)} file(s)) …")
            # Copy all meshes without decimation (set max faces to infinity)
            decimation_result = mesh_decimator.decimate_meshes(
                mesh_paths=mesh_paths,
                output_dir=meshes_out,
                roblox_max_faces=2**31,
            )
        click.echo(f"    → {decimation_result.total_meshes} mesh(es): "
                   f"{decimation_result.already_compliant} compliant, "
                   f"{decimation_result.decimated} decimated, "
                   f"{decimation_result.skipped} skipped")
        for w in decimation_result.warnings:
            click.echo(f"    ⚠ {w}")

    # ── Build mesh path remap (original → decimated) ─────────────
    mesh_path_remap: dict[str, str] | None = None
    if decimation_result.entries:
        mesh_path_remap = {}
        for entry in decimation_result.entries:
            if not entry.skipped and entry.output_path.exists():
                mesh_path_remap[str(entry.source_path)] = str(entry.output_path)

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

    # ── Prefab → .rbxm package generation ───────────────────────────
    package_result = rbxl_writer.RbxPackageResult()
    if emit_packages and prefabs.prefabs:
        click.echo("📦  Generating .rbxm packages …")
        package_result = _generate_prefab_packages(
            prefabs, out_dir,
            guid_to_roblox_def=guid_to_roblox_def,
            guid_to_companion_scripts=guid_to_companion,
            guid_index=guid_index,
            mesh_path_remap=mesh_path_remap,
        )
        click.echo(f"    → {package_result.total_packages} package(s) written to "
                   f"{out_dir / config.PACKAGES_SUBDIR}")
        for w in package_result.warnings:
            click.echo(f"    ⚠ {w}")

    # ── UI Translation (RectTransform → UDim2) ─────────────────────
    all_scene_roots = [node for ps in parsed_scenes for node in ps.roots]
    ui_result = ui_translator.translate_ui_hierarchy(all_scene_roots)
    if ui_result.total:
        click.echo(f"🖼   UI translation: {ui_result.converted}/{ui_result.total} "
                   f"RectTransform(s) → UDim2")
        for w in ui_result.warnings:
            click.echo(f"    ⚠ {w}")

    # Convert UI elements to RbxScreenGui objects for the writer
    rbx_screen_guis = None
    if ui_result.elements:
        rbx_screen_guis = [
            ui_translator.to_rbx_screen_gui("ConvertedUI", ui_result.elements)
        ]

    click.echo("🏗   Writing .rbxl …")
    parts, lighting_config, camera_config, skybox_config, comp_warnings = _scene_nodes_to_parts(
        parsed_scenes,
        guid_to_roblox_def=guid_to_roblox_def,
        guid_to_companion_scripts=guid_to_companion,
        guid_index=guid_index,
        mesh_path_remap=mesh_path_remap,
        mat_results=mat_result.materials if mat_result else None,
        split_output_dir=out_dir / "split_meshes",
    )
    if lighting_config:
        click.echo(f"    → Directional light → Lighting (brightness={lighting_config.brightness:.1f})")
    if camera_config:
        click.echo(f"    → Camera → Workspace.CurrentCamera (FOV={camera_config.field_of_view:.0f})")
    if skybox_config:
        click.echo("    → Skybox material → Sky object")

    audio_out = out_dir / "audio"
    audio_copied = 0
    # From AudioSource components (sound_children on parts)
    for part in parts:
        for sc in part.sound_children:
            clip_path = sc[1]
            if clip_path and Path(clip_path).is_file():
                audio_out.mkdir(parents=True, exist_ok=True)
                dest = audio_out / Path(clip_path).name
                if not dest.exists():
                    shutil.copy2(clip_path, dest)
                    audio_copied += 1
    # From serialized AudioClip fields on MonoBehaviours
    if serialized_refs:
        for _script_path, refs in serialized_refs.items():
            for _field, ref_value in refs.items():
                if ref_value.startswith("audio:"):
                    audio_path = Path(ref_value[len("audio:"):])
                    if audio_path.is_file():
                        audio_out.mkdir(parents=True, exist_ok=True)
                        dest = audio_out / audio_path.name
                        if not dest.exists():
                            shutil.copy2(audio_path, dest)
                            audio_copied += 1
    if audio_copied:
        click.echo(f"    → Staged {audio_copied} audio file(s) in {audio_out}")

    rbx_scripts = _transpiled_to_rbx_scripts(transpilation)
    rbxl_path = out_dir / config.RBXL_OUTPUT_FILENAME

    write_result = rbxl_writer.write_rbxl(
        parts=parts,
        scripts=rbx_scripts,
        output_path=rbxl_path,
        place_name=unity_path.name,
        lighting=lighting_config,
        camera=camera_config,
        skybox=skybox_config,
        replicated_templates=package_result.replicated_templates or None,
        screen_guis=rbx_screen_guis,
    )
    click.echo(f"    → Written to {write_result.output_path}")

    # ------------------------------------------------------------------
    # Phase 5 — Portal upload (requires Roblox API key)
    # ------------------------------------------------------------------

    # ── Sprite extraction ─────────────────────────────────────────
    click.echo("🖼️   Extracting sprites from spritesheets …")
    sprite_result = sprite_extractor.extract_sprites(guid_index, out_dir)
    if sprite_result.total_sprites_extracted:
        click.echo(f"    → {sprite_result.total_sprites_extracted} sprites from "
                   f"{sprite_result.total_spritesheets} spritesheet(s)")
    for w in sprite_result.warnings:
        warnings.append(w)

    click.echo("☁️   Checking Roblox upload …")
    textures_dir = out_dir / "textures" if (out_dir / "textures").is_dir() else None
    sprites_dir = out_dir / "sprites" if (out_dir / "sprites").is_dir() else None
    audio_dir = audio_out if audio_out.is_dir() else None
    meshes_dir = out_dir / "meshes" if (out_dir / "meshes").is_dir() else None

    # Build mesh→texture map so the uploader can pair mesh assets with their
    # textures when patching the .rbxl.
    mesh_texture_map = roblox_uploader._build_mesh_material_map(unity_path) if meshes_dir else None

    upload_result = call_with_retry(
        roblox_uploader.upload_to_roblox,
        rbxl_path=rbxl_path,
        textures_dir=textures_dir,
        sprites_dir=sprites_dir,
        audio_dir=audio_dir,
        meshes_dir=meshes_dir,
        api_key=roblox_api_key,
        universe_id=universe_id,
        place_id=place_id,
        mesh_texture_map=mesh_texture_map,
        unity_project_path=unity_path,
        asset_cache_path=out_dir / "asset_id_map.json",
        max_retries=config.RETRY_MAX_ATTEMPTS,
        base_delay=config.RETRY_BASE_DELAY,
        max_delay=config.RETRY_MAX_DELAY,
        backoff_factor=config.RETRY_BACKOFF_FACTOR,
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

    # ── Root motion for skinned meshes ──────────────────────────────
    # When FBX→GLB strips skinning data, extract root bone motion from
    # associated animation FBXes and generate TransformAnimator configs.
    if upload_result.skinned_meshes:
        meshes_out = out_dir / "meshes"
        click.echo(f"🦴  Extracting root motion for {len(upload_result.skinned_meshes)} skinned mesh(es)…")
        anim_suffixes = ["_Run", "_Walk", "_Idle", "_Anim"]
        root_motion_count = 0
        for mesh_stem in sorted(upload_result.skinned_meshes):
            anim_fbx = None
            for suffix in anim_suffixes:
                candidate = meshes_out / f"{mesh_stem}{suffix}.fbx"
                if candidate.exists():
                    anim_fbx = candidate
                    break
            if not anim_fbx:
                click.echo(f"    ⚠ {mesh_stem}: no animation FBX found (tried {anim_suffixes})")
                continue
            motion = animation_converter.extract_fbx_root_motion(anim_fbx)
            if not motion:
                click.echo(f"    ⚠ {mesh_stem}: failed to extract root motion from {anim_fbx.name}")
                continue
            config_source = animation_converter.generate_root_motion_config(motion, mesh_stem)
            module_name = f"{mesh_stem}_RootMotionConfig"
            transpilation.scripts.append(code_transpiler.TranspiledScript(
                source_path=Path("(generated)"),
                output_filename=f"{module_name}.lua",
                csharp_source="",
                luau_source=config_source,
                strategy="ai",
                confidence=1.0,
                script_type="ModuleScript",
            ))
            root_motion_count += 1
            click.echo(f"    → {module_name}.lua generated from {anim_fbx.name}")
        if root_motion_count > 0:
            # Ensure TransformAnimator bridge is included
            bridge_path = Path(__file__).parent / "bridge" / "TransformAnimator.lua"
            if bridge_path.exists():
                # Check if already added by transform animation step
                already_added = any(
                    s.output_filename == "TransformAnimator.lua"
                    for s in transpilation.scripts
                )
                if not already_added:
                    transpilation.scripts.append(code_transpiler.TranspiledScript(
                        source_path=Path("(generated)"),
                        output_filename="TransformAnimator.lua",
                        csharp_source="",
                        luau_source=bridge_path.read_text(encoding="utf-8"),
                        strategy="ai",
                        confidence=1.0,
                        script_type="ModuleScript",
                    ))
                    click.echo("    → TransformAnimator.lua added (ModuleScript in ReplicatedStorage)")

    duration = time.monotonic() - t_start

    rpt = _build_report(
        unity_path, out_dir, manifest, mat_result, parsed_scenes,
        prefabs, transpilation, write_result, decimation_result,
        resolved_count, duration, errors,
        package_result=package_result if emit_packages else None,
        component_warnings=comp_warnings,
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
