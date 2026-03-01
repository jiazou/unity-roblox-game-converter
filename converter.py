"""
converter.py — Orchestrator for the Unity → Roblox conversion pipeline.

This is the single entry point that wires all pipeline modules together:

  1. asset_extractor  → discovers and catalogues Unity assets
  2. scene_parser     → parses .unity scene files into node trees
  3. prefab_parser    → parses .prefab files into reusable templates
  4. code_transpiler  → converts C# MonoBehaviours to Luau scripts
  5. rbxl_writer      → writes the final .rbxl Roblox place file
  6. report_generator → produces a JSON + stdout conversion report

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
    scene_parser,
    prefab_parser,
    code_transpiler,
    rbxl_writer,
    report_generator,
)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _scene_nodes_to_parts(
    parsed_scenes: list[scene_parser.ParsedScene],
) -> list[rbxl_writer.RbxPartEntry]:
    """
    Convert parsed Unity scene nodes into RbxPartEntry objects.

    Each root SceneNode becomes a BasePart in Roblox Workspace.
    Position is mapped directly (Unity Y-up == Roblox Y-up).
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
def convert(
    unity_project_path: str,
    output_dir: str,
    use_ai: bool,
    api_key: str,
    verbose: bool,
) -> None:
    """
    Convert a Unity project at UNITY_PROJECT_PATH to a Roblox place in OUTPUT_DIR.

    \b
    Example:
        python converter.py ./MyUnityGame ./roblox_output
    """
    unity_path = Path(unity_project_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    t_start = time.monotonic()

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

    click.echo("🏗   Writing .rbxl …")
    parts = _scene_nodes_to_parts(parsed_scenes)
    rbx_scripts = _transpiled_to_rbx_scripts(transpilation)
    rbxl_path = out_dir / config.RBXL_OUTPUT_FILENAME

    write_result = rbxl_writer.write_rbxl(
        parts=parts,
        scripts=rbx_scripts,
        output_path=rbxl_path,
        place_name=unity_path.name,
    )
    click.echo(f"    → Written to {write_result.output_path}")

    duration = time.monotonic() - t_start

    rpt = _build_report(
        unity_path, out_dir, manifest, parsed_scenes,
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
