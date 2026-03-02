"""
modules/ — Conversion pipeline modules for unity-roblox-game-converter.

Each module is self-contained and exposes exactly one public function.
Wiring between modules happens exclusively in converter.py.

Pipeline modules:
    asset_extractor   — discovers textures, meshes, audio, materials, animations
    scene_parser      — parses .unity scene YAML files into node trees
    prefab_parser     — parses .prefab files into reusable templates
    material_mapper   — converts Unity materials to Roblox SurfaceAppearance
    code_transpiler   — transpiles C# MonoBehaviours to Luau (tree-sitter + API mappings)
    code_validator    — validates generated Luau code for syntactic correctness
    guid_resolver     — full bidirectional GUID ↔ asset-path index
    mesh_decimator    — conservative mesh decimation for Roblox polygon limits
    roblox_uploader   — uploads .rbxl and textures to Roblox Open Cloud
    rbxl_writer       — serialises geometry and scripts into .rbxl XML
    report_generator  — writes JSON conversion report

Data modules:
    api_mappings      — comprehensive Unity C# → Roblox Luau API mapping table

Utility modules:
    retry             — exponential backoff retry decorator for transient failures
    llm_cache         — hash-based disk cache for LLM responses
"""
