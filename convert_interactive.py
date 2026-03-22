"""
convert_interactive.py — Phase-based CLI for the interactive Unity → Roblox skill.

Unlike converter.py (which runs the full pipeline end-to-end), this module
exposes individual phases as sub-commands.  Each sub-command:
  - Reads from a shared state file (<output_dir>/.convert_state.json)
  - Outputs structured JSON to stdout (for the orchestrating skill to parse)
  - Writes updated state back to the state file

This enables Claude Code's /convert-unity skill to call each phase
independently, inspect results, ask the user for decisions, and resume.

Sub-commands:
  discover   — Parse scenes and prefabs (Phase 1)
  inventory  — Extract assets and build GUID index (Phase 2)
  materials  — Map materials to Roblox equivalents (Phase 3a)
  transpile  — Transpile C# scripts to Luau (Phase 3b)
  validate   — Validate generated Luau code (Phase 3c)
  assemble   — Build the .rbxl file (Phase 4)
  upload     — Upload to Roblox Cloud (Phase 5)
  report     — Generate the final conversion report (Phase 6)
  status     — Show the current state of a conversion in progress
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import click

import config
from modules import (
    asset_extractor,
    code_transpiler,
    code_validator,
    guid_resolver,
    material_mapper,
    mesh_decimator,
    prefab_parser,
    rbxl_writer,
    report_generator,
    roblox_uploader,
    scene_parser,
    scriptable_object_converter,
    ui_translator,
)
from modules.conversion_helpers import (
    resolve_prefab_instances as _resolve_prefab_instances,
    extract_serialized_field_refs as _extract_serialized_field_refs,
    generate_prefab_packages as _generate_prefab_packages,
    scene_nodes_to_parts as _scene_nodes_to_parts,
    transpiled_to_rbx_scripts as _transpiled_to_rbx_scripts,
    build_report as _build_report,
)
from modules.retry import call_with_retry


# ---------------------------------------------------------------------------
# Conversion state — serialised between phases
# ---------------------------------------------------------------------------

STATE_FILENAME = ".convert_state.json"


def _state_path(output_dir: Path) -> Path:
    return output_dir / STATE_FILENAME


def _load_state(output_dir: Path) -> dict:
    sp = _state_path(output_dir)
    if sp.exists():
        return json.loads(sp.read_text(encoding="utf-8"))
    return {}


def _save_state(output_dir: Path, state: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _state_path(output_dir).write_text(
        json.dumps(state, indent=2, default=str),
        encoding="utf-8",
    )


def _emit(data: dict) -> None:
    """Print JSON to stdout for the skill to consume."""
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """Interactive Unity → Roblox conversion (phase-by-phase)."""


# ---------------------------------------------------------------------------
# status — show current conversion state
# ---------------------------------------------------------------------------

ALL_PHASES = ["discover", "inventory", "materials", "transpile", "assemble", "upload", "report"]


@cli.command()
@click.argument("unity_project_path", type=click.Path())
@click.argument("output_dir", type=click.Path())
@click.option("--install", is_flag=True, help="Auto-install missing dependencies.")
def preflight(unity_project_path: str, output_dir: str, install: bool) -> None:
    """Check prerequisites: Python version, packages, Unity project validity."""
    import subprocess
    import sys

    result: dict = {"phase": "preflight", "success": True}
    result["python_version"] = sys.version.split()[0]

    # Check Python version
    if sys.version_info < (3, 10):
        result["success"] = False
        result["python_error"] = f"Python >= 3.10 required, got {sys.version}"

    # Check required packages
    required = {
        "yaml": "PyYAML", "lxml": "lxml", "click": "click", "PIL": "Pillow",
        "trimesh": "trimesh", "anthropic": "anthropic", "tree_sitter": "tree-sitter",
        "tree_sitter_c_sharp": "tree-sitter-c-sharp", "lz4": "lz4",
    }
    missing = []
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    result["missing_packages"] = missing

    if missing and install:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt",
             "--break-system-packages"],
            capture_output=True,
        )
        # Re-check
        still_missing = []
        for mod, pkg in required.items():
            try:
                __import__(mod)
            except ImportError:
                still_missing.append(pkg)
        result["missing_packages"] = still_missing
        result["install_ran"] = True

    # Validate Unity project
    unity_path = Path(unity_project_path)
    result["unity_project_valid"] = unity_path.is_dir() and (unity_path / "Assets").is_dir()
    if not result["unity_project_valid"]:
        result["success"] = False
    if result["missing_packages"]:
        result["success"] = False

    # Check output dir
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result["output_dir"] = str(out_dir.resolve())

    _emit(result)


@cli.command()
@click.argument("output_dir", type=click.Path())
def status(output_dir: str) -> None:
    """Show the current state of a conversion in progress."""
    out = Path(output_dir).resolve()
    state = _load_state(out)
    if not state:
        _emit({"status": "no_conversion", "message": "No conversion in progress at this path."})
        return

    completed = state.get("completed_phases", [])
    # Find next incomplete phase
    next_phase = None
    for phase in ALL_PHASES:
        if phase not in completed:
            next_phase = phase
            break

    _emit({
        "status": "in_progress",
        "completed_phases": completed,
        "unity_project_path": state.get("unity_project_path", ""),
        "output_dir": str(out),
        "errors": state.get("errors", []),
        "resumable": len(completed) > 0 and next_phase is not None,
        "next_phase": next_phase,
    })


# ---------------------------------------------------------------------------
# discover — Phase 1: parse scenes and prefabs
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
def discover(unity_project_path: str, output_dir: str) -> None:
    """Phase 1: Parse Unity scenes and prefabs."""
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(out_dir)
    state["unity_project_path"] = str(unity_path)
    state["output_dir"] = str(out_dir)
    state.setdefault("completed_phases", [])
    state.setdefault("errors", [])

    errors: list[str] = []

    # Parse scenes
    parsed_scenes_info: list[dict] = []
    scene_files = sorted(unity_path.rglob("*.unity"))
    for scene_file in scene_files:
        try:
            ps = scene_parser.parse_scene(scene_file)
            parsed_scenes_info.append({
                "name": scene_file.stem,
                "path": str(scene_file.relative_to(unity_path)),
                "roots": len(ps.roots),
                "total_nodes": len(ps.all_nodes),
                "prefab_instances": len(ps.prefab_instances),
                "referenced_material_guids": len(ps.referenced_material_guids),
                "referenced_mesh_guids": len(ps.referenced_mesh_guids),
            })
        except Exception as exc:
            errors.append(f"Scene parse error ({scene_file.name}): {exc}")

    # Parse prefabs
    prefab_info: dict = {"count": 0, "referenced_material_guids": 0}
    try:
        prefabs = prefab_parser.parse_prefabs(unity_path)
        prefab_info = {
            "count": len(prefabs.prefabs),
            "names": [p.prefab_path.stem for p in prefabs.prefabs[:20]],
            "referenced_material_guids": len(prefabs.referenced_material_guids),
        }
        if len(prefabs.prefabs) > 20:
            prefab_info["names_truncated"] = True
    except FileNotFoundError as exc:
        errors.append(str(exc))

    # Collect total referenced material GUIDs
    all_mat_guids: set[str] = set()
    for scene_file in scene_files:
        try:
            ps = scene_parser.parse_scene(scene_file)
            all_mat_guids |= ps.referenced_material_guids
        except Exception:
            pass
    try:
        all_mat_guids |= prefabs.referenced_material_guids
    except Exception:
        pass

    # Save state for subsequent phases
    state["scene_files"] = [str(f) for f in scene_files]
    state["referenced_material_guids"] = sorted(all_mat_guids)
    state["errors"].extend(errors)
    if "discover" not in state["completed_phases"]:
        state["completed_phases"].append("discover")
    _save_state(out_dir, state)

    _emit({
        "phase": "discover",
        "success": len(errors) == 0,
        "scenes": parsed_scenes_info,
        "prefabs": prefab_info,
        "total_referenced_material_guids": len(all_mat_guids),
        "errors": errors,
    })


# ---------------------------------------------------------------------------
# inventory — Phase 2: extract assets and build GUID index
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
def inventory(unity_project_path: str, output_dir: str) -> None:
    """Phase 2: Extract assets and build GUID index."""
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(out_dir)
    state.setdefault("completed_phases", [])
    state.setdefault("errors", [])
    errors: list[str] = []

    # Asset extraction
    asset_info: dict = {}
    try:
        manifest = asset_extractor.extract_assets(
            unity_path,
            supported_extensions=config.SUPPORTED_ASSET_EXTENSIONS,
        )
        asset_info = {
            "total": len(manifest.assets),
            "total_size_mb": round(manifest.total_size_bytes / 1_048_576, 1),
            "by_kind": {k: len(v) for k, v in manifest.by_kind.items()},
        }
    except FileNotFoundError as exc:
        errors.append(str(exc))
        asset_info = {"total": 0, "total_size_mb": 0, "by_kind": {}}

    # GUID resolution
    guid_info: dict = {}
    try:
        guid_index = guid_resolver.build_guid_index(unity_path)
        guid_info = {
            "total_resolved": guid_index.total_resolved,
            "total_meta_files": guid_index.total_meta_files,
            "duplicate_guids": len(guid_index.duplicate_guids),
            "orphan_metas": len(guid_index.orphan_metas),
        }
        if guid_index.duplicate_guids:
            guid_info["duplicate_guid_list"] = list(guid_index.duplicate_guids)[:10]
        if guid_index.orphan_metas:
            guid_info["orphan_meta_list"] = [str(p) for p in list(guid_index.orphan_metas)[:10]]
    except FileNotFoundError as exc:
        errors.append(str(exc))
        guid_info = {"total_resolved": 0, "total_meta_files": 0}

    state["errors"].extend(errors)
    if "inventory" not in state["completed_phases"]:
        state["completed_phases"].append("inventory")
    _save_state(out_dir, state)

    _emit({
        "phase": "inventory",
        "success": len(errors) == 0,
        "assets": asset_info,
        "guid_index": guid_info,
        "errors": errors,
    })


# ---------------------------------------------------------------------------
# materials — Phase 3a: map materials
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
@click.option("--referenced-guids", default=None,
              help="Comma-separated GUIDs to filter materials (from discover phase).")
def materials(unity_project_path: str, output_dir: str, referenced_guids: str | None) -> None:
    """Phase 3a: Map Unity materials to Roblox equivalents."""
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(out_dir)
    state.setdefault("completed_phases", [])
    state.setdefault("errors", [])
    errors: list[str] = []

    # Resolve referenced GUIDs from state or CLI
    guid_set: set[str] | None = None
    if referenced_guids:
        guid_set = set(referenced_guids.split(","))
    elif "referenced_material_guids" in state:
        guid_set = set(state["referenced_material_guids"])

    try:
        mat_result = material_mapper.map_materials(
            unity_path, out_dir,
            referenced_guids=guid_set or None,
        )
        result_info = {
            "total": mat_result.total,
            "fully_converted": mat_result.fully_converted,
            "partially_converted": mat_result.partially_converted,
            "unconvertible": mat_result.unconvertible,
            "texture_ops_performed": mat_result.texture_ops_performed,
            "unconverted_md_path": str(mat_result.unconverted_md_path) if mat_result.unconverted_md_path else None,
        }

        # Read UNCONVERTED.md if it was generated, for the skill to present
        unconverted_content = None
        if mat_result.unconverted_md_path and Path(mat_result.unconverted_md_path).exists():
            unconverted_content = Path(mat_result.unconverted_md_path).read_text(encoding="utf-8")

    except Exception as exc:
        errors.append(f"Material mapping error: {exc}")
        result_info = {"total": 0, "fully_converted": 0, "partially_converted": 0, "unconvertible": 0}
        unconverted_content = None

    state["errors"].extend(errors)
    if "materials" not in state["completed_phases"]:
        state["completed_phases"].append("materials")
    _save_state(out_dir, state)

    output = {
        "phase": "materials",
        "success": len(errors) == 0,
        "result": result_info,
        "errors": errors,
    }
    if unconverted_content:
        output["unconverted_features"] = unconverted_content
    _emit(output)


# ---------------------------------------------------------------------------
# transpile — Phase 3b: C# → Luau transpilation
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
@click.option("--use-ai/--no-ai", default=config.USE_AI_TRANSPILATION,
              help="Use Claude for C# → Luau transpilation.")
@click.option("--api-key", default=config.ANTHROPIC_API_KEY, envvar="ANTHROPIC_API_KEY")
def transpile(unity_project_path: str, output_dir: str, use_ai: bool, api_key: str) -> None:
    """Phase 3b: Transpile C# scripts to Luau."""
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(out_dir)
    state.setdefault("completed_phases", [])
    state.setdefault("errors", [])
    errors: list[str] = []

    # Build serialized field refs from scene/prefab YAML for WaitForChild wiring
    serialized_refs = None
    try:
        parsed_scenes_for_refs: list[scene_parser.ParsedScene] = []
        for sf in unity_path.rglob("*.unity"):
            try:
                parsed_scenes_for_refs.append(scene_parser.parse_scene(sf))
            except Exception:
                pass
        prefabs_for_refs = prefab_parser.parse_prefabs(unity_path)
        gi_for_refs = guid_resolver.build_guid_index(unity_path)
        if parsed_scenes_for_refs or prefabs_for_refs.prefabs:
            serialized_refs = _extract_serialized_field_refs(
                parsed_scenes_for_refs, prefabs_for_refs, gi_for_refs,
            ) or None
    except Exception:
        pass  # Non-critical — transpilation still works without refs

    try:
        transpilation = code_transpiler.transpile_scripts(
            unity_path,
            use_ai=use_ai,
            api_key=api_key,
            model=config.ANTHROPIC_MODEL,
            max_tokens=config.ANTHROPIC_MAX_TOKENS,
            confidence_threshold=config.TRANSPILATION_CONFIDENCE_THRESHOLD,
            serialized_refs=serialized_refs,
        )

        scripts_info: list[dict] = []
        for ts in transpilation.scripts:
            script_data: dict = {
                "source_file": str(ts.source_path.relative_to(unity_path)),
                "output_filename": ts.output_filename,
                "strategy": ts.strategy,
                "confidence": round(ts.confidence, 2),
                "flagged": ts.flagged_for_review,
                "script_type": ts.script_type,
                "warnings": ts.warnings,
            }
            if ts.flagged_for_review:
                # Include source and output for review
                script_data["csharp_source"] = ts.csharp_source
                script_data["luau_source"] = ts.luau_source
            scripts_info.append(script_data)

        # Save transpiled scripts to output dir for later assembly
        scripts_out = out_dir / "scripts"
        scripts_out.mkdir(parents=True, exist_ok=True)
        for ts in transpilation.scripts:
            (scripts_out / ts.output_filename).write_text(
                ts.luau_source, encoding="utf-8"
            )

        result_info = {
            "total": transpilation.total,
            "succeeded": transpilation.succeeded,
            "flagged": transpilation.flagged,
            "skipped": transpilation.skipped,
        }

        # M8: suggest batch review when many scripts are flagged
        if transpilation.flagged > 5:
            result_info["batch_review_suggested"] = True

        # M5: classify API key failures when all scripts are flagged
        if transpilation.total > 0 and transpilation.flagged == transpilation.total:
            all_warnings = []
            for ts in transpilation.scripts:
                all_warnings.extend(ts.warnings)
            warnings_text = " ".join(all_warnings).lower()
            if "credit balance" in warnings_text or "insufficient_credits" in warnings_text:
                result_info["error_type"] = "insufficient_credits"
                result_info["suggestion"] = "Provide a funded API key or use --no-ai"
            elif (
                "authentication_error" in warnings_text
                or "invalid x-api-key" in warnings_text
                or "401" in warnings_text
            ):
                result_info["error_type"] = "auth_failure"
                result_info["suggestion"] = "Provide a funded API key or use --no-ai"

    except FileNotFoundError as exc:
        errors.append(str(exc))
        scripts_info = []
        result_info = {"total": 0, "succeeded": 0, "flagged": 0, "skipped": 0}

    state["errors"].extend(errors)
    if "transpile" not in state["completed_phases"]:
        state["completed_phases"].append("transpile")
    _save_state(out_dir, state)

    _emit({
        "phase": "transpile",
        "success": len(errors) == 0,
        "result": result_info,
        "scripts": scripts_info,
        "errors": errors,
    })


# ---------------------------------------------------------------------------
# validate — Phase 3c: validate generated Luau code
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False))
def validate(output_dir: str) -> None:
    """Phase 3c: Validate generated Luau scripts."""
    out_dir = Path(output_dir).resolve()
    scripts_dir = out_dir / "scripts"

    state = _load_state(out_dir)
    state.setdefault("completed_phases", [])
    state.setdefault("errors", [])

    if not scripts_dir.is_dir():
        _emit({
            "phase": "validate",
            "success": False,
            "errors": ["No scripts directory found. Run 'transpile' first."],
        })
        return

    results: list[dict] = []
    total_errors = 0
    total_warnings = 0

    for lua_file in sorted(scripts_dir.glob("*.lua")):
        source = lua_file.read_text(encoding="utf-8")
        vr = code_validator.validate_luau(source, lua_file.name)
        issues = []
        for issue in vr.issues:
            issues.append({
                "code": issue.code,
                "severity": issue.severity,
                "line": issue.line,
                "message": issue.message,
            })
        if issues:
            results.append({
                "file": lua_file.name,
                "valid": vr.valid,
                "errors": vr.error_count,
                "warnings": vr.warning_count,
                "issues": issues,
            })
        total_errors += vr.error_count
        total_warnings += vr.warning_count

    if "validate" not in state["completed_phases"]:
        state["completed_phases"].append("validate")
    _save_state(out_dir, state)

    _emit({
        "phase": "validate",
        "success": total_errors == 0,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "files_with_issues": results,
    })


# ---------------------------------------------------------------------------
# assemble — Phase 4: build .rbxl
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
@click.option("--decimate/--no-decimate", default=config.MESH_DECIMATION_ENABLED)
@click.option("--emit-packages/--no-packages", default=config.EMIT_PACKAGES,
              help="Generate .rbxm package files for each prefab.")
@click.option("--preview-mode/--no-preview-mode", default=True,
              help="Preview mode: copy prefabs to Workspace, disable scripts and UI.")
def assemble(unity_project_path: str, output_dir: str, decimate: bool,
             emit_packages: bool, preview_mode: bool) -> None:
    """Phase 4: Assemble the .rbxl file from all converted data."""
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    state = _load_state(out_dir)
    state.setdefault("completed_phases", [])
    state.setdefault("errors", [])
    errors: list[str] = []

    # Re-parse everything needed for assembly (stateless re-read from disk)
    # Phase 1: scenes & prefabs
    parsed_scenes: list[scene_parser.ParsedScene] = []
    for scene_file in unity_path.rglob("*.unity"):
        try:
            parsed_scenes.append(scene_parser.parse_scene(scene_file))
        except Exception as exc:
            errors.append(f"Scene parse error ({scene_file.name}): {exc}")

    try:
        prefabs = prefab_parser.parse_prefabs(unity_path)
    except FileNotFoundError:
        prefabs = prefab_parser.PrefabLibrary()

    # Phase 2: GUID index
    try:
        guid_index = guid_resolver.build_guid_index(unity_path)
    except FileNotFoundError:
        guid_index = guid_resolver.GuidIndex(project_root=unity_path)

    # Resolve prefab instances
    referenced_guids: set[str] = set()
    for ps in parsed_scenes:
        referenced_guids |= ps.referenced_material_guids
    referenced_guids |= prefabs.referenced_material_guids

    total_pi = sum(len(s.prefab_instances) for s in parsed_scenes)
    resolved_count = 0
    if total_pi and prefabs.prefabs:
        resolved_count = _resolve_prefab_instances(parsed_scenes, prefabs, guid_index)
        for ps in parsed_scenes:
            referenced_guids |= ps.referenced_material_guids

    # Phase 3a: materials (re-run to get roblox_defs)
    try:
        mat_result = material_mapper.map_materials(
            unity_path, out_dir,
            referenced_guids=referenced_guids or None,
        )
    except Exception as exc:
        errors.append(f"Material mapping error: {exc}")
        mat_result = material_mapper.MaterialMapResult()

    # Phase 3b: transpilation (re-run to get TranspilationResult)
    asm_serialized_refs = _extract_serialized_field_refs(
        parsed_scenes, prefabs, guid_index,
    ) or None
    try:
        transpilation = code_transpiler.transpile_scripts(
            unity_path,
            use_ai=False,  # Assembly uses whatever was already generated
            confidence_threshold=config.TRANSPILATION_CONFIDENCE_THRESHOLD,
            serialized_refs=asm_serialized_refs,
        )
    except FileNotFoundError:
        transpilation = code_transpiler.TranspilationResult()

    # Luau validation pass
    for ts in transpilation.scripts:
        vr = code_validator.validate_luau(ts.luau_source, ts.output_filename)
        if not vr.valid:
            ts.flagged_for_review = True
            ts.warnings.extend(
                f"[{i.code}] L{i.line}: {i.message}" for i in vr.issues
                if i.severity == "error"
            )

    # ScriptableObjects
    so_result = scriptable_object_converter.convert_asset_files(unity_path)
    for ca in so_result.assets:
        transpilation.scripts.append(code_transpiler.TranspiledScript(
            source_path=ca.source_path,
            output_filename=ca.asset_name + "_Data.lua",
            csharp_source="",
            luau_source=ca.luau_source,
            strategy="rule_based",
            confidence=1.0,
            script_type="ModuleScript",
        ))

    # Mesh decimation
    manifest = asset_extractor.AssetManifest(unity_project_path=unity_path)
    try:
        manifest = asset_extractor.extract_assets(
            unity_path,
            supported_extensions=config.SUPPORTED_ASSET_EXTENSIONS,
        )
    except FileNotFoundError:
        pass

    decimation_result = mesh_decimator.DecimationResult()
    decimation_info: dict = {}
    mesh_entries = manifest.by_kind.get("mesh", [])
    mesh_paths = [e.path for e in mesh_entries]
    if mesh_paths:
        meshes_out = out_dir / "meshes"
        if decimate:
            decimation_result = mesh_decimator.decimate_meshes(
                mesh_paths=mesh_paths,
                output_dir=meshes_out,
                target_faces=config.MESH_TARGET_FACES,
                quality_floor=config.MESH_QUALITY_FLOOR,
                roblox_max_faces=config.MESH_ROBLOX_MAX_FACES,
            )
        else:
            # Copy all meshes without decimation (set max faces to infinity)
            decimation_result = mesh_decimator.decimate_meshes(
                mesh_paths=mesh_paths,
                output_dir=meshes_out,
                roblox_max_faces=2**31,
            )
        decimation_info = {
            "total_meshes": decimation_result.total_meshes,
            "already_compliant": decimation_result.already_compliant,
            "decimated": decimation_result.decimated,
            "skipped": decimation_result.skipped,
            "warnings": decimation_result.warnings,
        }

    # Build mesh path remap
    mesh_path_remap: dict[str, str] | None = None
    if decimation_result.entries:
        mesh_path_remap = {}
        for entry in decimation_result.entries:
            if not entry.skipped and entry.output_path.exists():
                mesh_path_remap[str(entry.source_path)] = str(entry.output_path)

    # Build GUID → material maps
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

    # Prefab → .rbxm package generation
    package_info: dict = {}
    if emit_packages and prefabs.prefabs:
        package_result = _generate_prefab_packages(
            prefabs, out_dir,
            guid_to_roblox_def=guid_to_roblox_def,
            guid_to_companion_scripts=guid_to_companion,
            guid_index=guid_index,
            mesh_path_remap=mesh_path_remap,
        )
        package_info = {
            "total_packages": package_result.total_packages,
            "packages": [
                {"name": p.prefab_name, "path": str(p.output_path),
                 "parts": p.parts_written, "scripts": p.scripts_written}
                for p in package_result.packages
            ],
            "warnings": package_result.warnings,
        }

    # UI translation
    all_scene_roots = [node for ps in parsed_scenes for node in ps.roots]
    ui_result = ui_translator.translate_ui_hierarchy(all_scene_roots)
    ui_info: dict = {}
    if ui_result.total:
        ui_info = {
            "total": ui_result.total,
            "converted": ui_result.converted,
            "warnings": ui_result.warnings,
        }

    # Convert UI elements to RbxScreenGui objects for the writer
    rbx_screen_guis = None
    if ui_result.elements:
        rbx_screen_guis = [
            ui_translator.to_rbx_screen_gui("ConvertedUI", ui_result.elements)
        ]

    # Build parts from scene nodes
    parts, lighting_config, camera_config, skybox_config = _scene_nodes_to_parts(
        parsed_scenes,
        guid_to_roblox_def=guid_to_roblox_def,
        guid_to_companion_scripts=guid_to_companion,
        guid_index=guid_index,
        mesh_path_remap=mesh_path_remap,
    )

    # Record mesh→texture mapping for the upload patcher.
    # Walks all parts and collects {mesh_id: color_map} for parts that have
    # a surface_appearance assigned during apply_materials.
    mesh_texture_map: dict[str, str] = {}
    def _collect_mesh_textures(plist: list) -> None:
        for p in plist:
            if p.mesh_id and p.surface_appearance and p.surface_appearance.color_map:
                mesh_texture_map[p.mesh_id] = p.surface_appearance.color_map
            _collect_mesh_textures(p.children)
    _collect_mesh_textures(parts)
    # Also collect from ServerStorage templates (prefabs)
    if emit_packages and package_info:
        for _name, root_part in (package_result.server_storage_templates or []):
            _collect_mesh_textures([root_part])
    state["mesh_texture_map"] = mesh_texture_map

    audio_out = out_dir / "audio"
    audio_copied = 0
    # From AudioSource components (sound_children on parts)
    for part in parts:
        for sc in part.sound_children:
            clip_path = sc[1]  # resolved file path from convert_audio_components
            if clip_path and Path(clip_path).is_file():
                audio_out.mkdir(parents=True, exist_ok=True)
                dest = audio_out / Path(clip_path).name
                if not dest.exists():
                    shutil.copy2(clip_path, dest)
                    audio_copied += 1
    # From serialized AudioClip fields on MonoBehaviours
    if asm_serialized_refs:
        for _script_path, refs in asm_serialized_refs.items():
            for _field, ref_value in refs.items():
                if ref_value.startswith("audio:"):
                    audio_filename = ref_value[len("audio:"):]
                    # Find the source file in the Unity project
                    matches = list(unity_path.rglob(audio_filename))
                    if matches:
                        audio_out.mkdir(parents=True, exist_ok=True)
                        dest = audio_out / audio_filename
                        if not dest.exists():
                            shutil.copy2(matches[0], dest)
                            audio_copied += 1

    rbx_scripts = _transpiled_to_rbx_scripts(transpilation)
    rbxl_path = out_dir / config.RBXL_OUTPUT_FILENAME

    # Collect ServerStorage templates if packages were generated
    ss_templates = None
    if emit_packages and package_info:
        ss_templates = package_result.server_storage_templates or None

    write_result = rbxl_writer.write_rbxl(
        parts=parts,
        scripts=rbx_scripts,
        output_path=rbxl_path,
        place_name=unity_path.name,
        lighting=lighting_config,
        camera=camera_config,
        skybox=skybox_config,
        server_storage_templates=ss_templates,
        screen_guis=rbx_screen_guis,
    )

    # Preview mode: make the place viewable without working game scripts.
    # - Copy prefabs from ServerStorage to Workspace so they render
    # - Disable scripts that would interfere with viewing
    # - Disable ScreenGuis that overlay the 3D view
    preview_info: dict = {}
    if preview_mode and rbxl_path.exists():
        import copy as _copy
        from xml.etree import ElementTree as _ET

        _tree = _ET.parse(rbxl_path)
        _root = _tree.getroot()
        _changed = False

        # Disable all ScreenGuis
        gui_disabled = 0
        for _item in _root.iter("Item"):
            if _item.get("class") == "ScreenGui":
                _props = _item.find("Properties")
                if _props is not None:
                    _en = None
                    for _p in _props:
                        if _p.get("name") == "Enabled":
                            _en = _p
                    if _en is None:
                        _en = _ET.SubElement(_props, "bool")
                        _en.set("name", "Enabled")
                    _en.text = "false"
                    gui_disabled += 1
                    _changed = True

        # Disable all Scripts and LocalScripts (except MeshLoader)
        scripts_disabled = 0
        _keep_scripts = {"MeshLoader", "GameBootstrap"}
        for _item in _root.iter("Item"):
            if _item.get("class") in ("Script", "LocalScript"):
                _props = _item.find("Properties")
                if _props is not None:
                    _script_name = ""
                    for _p in _props:
                        if _p.get("name") == "Name":
                            _script_name = _p.text or ""
                    if _script_name in _keep_scripts:
                        continue
                    _dis = None
                    for _p in _props:
                        if _p.get("name") == "Disabled":
                            _dis = _p
                    if _dis is None:
                        _dis = _ET.SubElement(_props, "bool")
                        _dis.set("name", "Disabled")
                    _dis.text = "true"
                    scripts_disabled += 1
                    _changed = True

        # Copy prefab templates from ServerStorage to Workspace
        prefabs_copied = 0
        _workspace = None
        _ss = None
        for _item in _root.findall("Item"):
            if _item.get("class") == "Workspace":
                _workspace = _item
            elif _item.get("class") == "ServerStorage":
                _ss = _item
        if _workspace is not None and _ss is not None:
            for _model in _ss.findall("Item"):
                if _model.get("class") == "Model":
                    _workspace.append(_copy.deepcopy(_model))
                    prefabs_copied += 1
                    _changed = True

        if _changed:
            _tree.write(str(rbxl_path), encoding="unicode", xml_declaration=True)

        preview_info = {
            "preview_mode": True,
            "scripts_disabled": scripts_disabled,
            "guis_disabled": gui_disabled,
            "prefabs_copied_to_workspace": prefabs_copied,
        }

    # Store assembly info in state for the report phase
    state["assembly"] = {
        "rbxl_path": str(write_result.output_path),
        "parts_written": write_result.parts_written,
        "scripts_written": write_result.scripts_written,
        "prefab_instances_resolved": resolved_count,
    }
    state["errors"].extend(errors)
    if "assemble" not in state["completed_phases"]:
        state["completed_phases"].append("assemble")
    _save_state(out_dir, state)

    rbxl_size_mb = 0.0
    if rbxl_path.exists():
        rbxl_size_mb = round(rbxl_path.stat().st_size / 1_048_576, 2)

    _emit({
        "phase": "assemble",
        "success": len(errors) == 0,
        "rbxl_path": str(write_result.output_path),
        "rbxl_size_mb": rbxl_size_mb,
        "parts_written": write_result.parts_written,
        "scripts_written": write_result.scripts_written,
        "audio_files_staged": audio_copied,
        "warnings": write_result.warnings,
        "decimation": decimation_info,
        "ui_translation": ui_info,
        "packages": package_info,
        "preview": preview_info,
        "errors": errors,
    })


# ---------------------------------------------------------------------------
# upload — Phase 5: upload to Roblox
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--roblox-api-key", default=config.ROBLOX_API_KEY, envvar="ROBLOX_API_KEY")
@click.option("--universe-id", default=config.ROBLOX_UNIVERSE_ID, type=int)
@click.option("--place-id", default=config.ROBLOX_PLACE_ID, type=int)
@click.option("--creator-id", default=config.ROBLOX_CREATOR_ID, type=int,
              help="Roblox user or group ID that will own uploaded assets.")
@click.option("--creator-type", default=config.ROBLOX_CREATOR_TYPE,
              type=click.Choice(["User", "Group"]),
              help="Whether creator-id is a User or Group.")
@click.option("--creator-username", default=None,
              help="Roblox username (resolved to numeric ID if --creator-id not given).")
def upload(output_dir: str, roblox_api_key: str, universe_id: int | None,
           place_id: int | None, creator_id: int | None, creator_type: str,
           creator_username: str | None) -> None:
    """Phase 5: Upload assets and .rbxl to Roblox Cloud."""
    out_dir = Path(output_dir).resolve()
    state = _load_state(out_dir)

    # Resolve username to numeric ID if needed
    if creator_username and not creator_id:
        resolved = roblox_uploader.resolve_roblox_username(creator_username)
        if resolved:
            creator_id = resolved
        else:
            _emit({
                "phase": "upload", "success": False,
                "errors": [f"Could not resolve Roblox username '{creator_username}' to a numeric ID."],
            })
            return

    rbxl_path = Path(state.get("assembly", {}).get("rbxl_path", out_dir / config.RBXL_OUTPUT_FILENAME))
    if not rbxl_path.exists():
        _emit({
            "phase": "upload",
            "success": False,
            "errors": [f"RBXL file not found: {rbxl_path}. Run 'assemble' first."],
        })
        return

    textures_dir = out_dir / "textures" if (out_dir / "textures").is_dir() else None
    sprites_dir = out_dir / "sprites" if (out_dir / "sprites").is_dir() else None
    audio_dir = out_dir / "audio" if (out_dir / "audio").is_dir() else None
    meshes_dir = out_dir / "meshes" if (out_dir / "meshes").is_dir() else None

    # Load mesh→texture mapping from state (stored during assembly).
    mesh_texture_map = state.get("mesh_texture_map")
    unity_project_path = Path(state.get("unity_project_path", ""))

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
        creator_id=creator_id,
        creator_type=creator_type,
        mesh_texture_map=mesh_texture_map,
        unity_project_path=unity_project_path if unity_project_path.is_dir() else None,
        max_retries=config.RETRY_MAX_ATTEMPTS,
        base_delay=config.RETRY_BASE_DELAY,
        max_delay=config.RETRY_MAX_DELAY,
        backoff_factor=config.RETRY_BACKOFF_FACTOR,
    )

    state.setdefault("completed_phases", [])
    if "upload" not in state["completed_phases"]:
        state["completed_phases"].append("upload")
    state["upload"] = {
        "asset_ids": upload_result.asset_ids,
        "rbxl_patched": upload_result.rbxl_patched,
    }
    _save_state(out_dir, state)

    output = {
        "phase": "upload",
        "success": upload_result.success,
        "skipped": upload_result.skipped,
        "place_id": upload_result.place_id,
        "version_number": upload_result.version_number,
        "asset_ids": upload_result.asset_ids,
        "sprites_uploaded": upload_result.sprites_uploaded,
        "audio_uploaded": upload_result.audio_uploaded,
        "rbxl_patched": upload_result.rbxl_patched,
        "errors": upload_result.errors,
        "warnings": upload_result.warnings,
    }
    if upload_result.error_type:
        output["error_type"] = upload_result.error_type
    if upload_result.suggestion:
        output["suggestion"] = upload_result.suggestion
    _emit(output)


# ---------------------------------------------------------------------------
# report — Phase 6: generate final conversion report
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("unity_project_path", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--verbose/--no-verbose", default=config.REPORT_VERBOSE)
def report(unity_project_path: str, output_dir: str, verbose: bool) -> None:
    """Phase 6: Generate the final conversion report."""
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    state = _load_state(out_dir)
    t_start = time.monotonic()

    # Re-derive everything we need for the report
    errors: list[str] = state.get("errors", [])

    # Scenes
    parsed_scenes: list[scene_parser.ParsedScene] = []
    for scene_file in unity_path.rglob("*.unity"):
        try:
            parsed_scenes.append(scene_parser.parse_scene(scene_file))
        except Exception:
            pass

    # Prefabs
    try:
        prefabs = prefab_parser.parse_prefabs(unity_path)
    except FileNotFoundError:
        prefabs = prefab_parser.PrefabLibrary()

    # Assets
    try:
        manifest = asset_extractor.extract_assets(
            unity_path, supported_extensions=config.SUPPORTED_ASSET_EXTENSIONS,
        )
    except FileNotFoundError:
        manifest = asset_extractor.AssetManifest(unity_project_path=unity_path)

    # Materials
    try:
        mat_result = material_mapper.map_materials(unity_path, out_dir)
    except Exception:
        mat_result = material_mapper.MaterialMapResult()

    # Transpilation
    try:
        rpt_guid_index = guid_resolver.build_guid_index(unity_path)
    except FileNotFoundError:
        rpt_guid_index = guid_resolver.GuidIndex(project_root=unity_path)
    rpt_serialized_refs = _extract_serialized_field_refs(
        parsed_scenes, prefabs, rpt_guid_index,
    ) or None
    try:
        transpilation = code_transpiler.transpile_scripts(
            unity_path, use_ai=False,
            confidence_threshold=config.TRANSPILATION_CONFIDENCE_THRESHOLD,
            serialized_refs=rpt_serialized_refs,
        )
    except FileNotFoundError:
        transpilation = code_transpiler.TranspilationResult()

    # Write result from state
    assembly = state.get("assembly", {})
    write_result = rbxl_writer.RbxWriteResult(
        output_path=Path(assembly.get("rbxl_path", out_dir / config.RBXL_OUTPUT_FILENAME)),
        parts_written=assembly.get("parts_written", 0),
        scripts_written=assembly.get("scripts_written", 0),
    )

    decimation_result = mesh_decimator.DecimationResult()
    resolved_count = assembly.get("prefab_instances_resolved", 0)
    duration = time.monotonic() - t_start

    rpt = _build_report(
        unity_path, out_dir, manifest, mat_result, parsed_scenes,
        prefabs, transpilation, write_result, decimation_result,
        resolved_count, duration, errors,
    )

    report_path = out_dir / config.REPORT_FILENAME
    report_generator.generate_report(
        rpt, output_path=report_path, verbose=verbose, print_summary=False,
    )

    state.setdefault("completed_phases", [])
    if "report" not in state["completed_phases"]:
        state["completed_phases"].append("report")
    _save_state(out_dir, state)

    # Emit the full report as JSON
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    _emit({
        "phase": "report",
        "success": rpt.success,
        "report_path": str(report_path),
        "summary": report_data,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
