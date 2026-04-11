# Phase 3: Material Mapping

Resolves every Unity material to a Roblox `MaterialDef` (Color3 + optional SurfaceAppearance). Handles PBR textures, vertex-color baking, and mesh-splitting for multi-material meshes.

## Command

```bash
python3 convert_interactive.py materials <unity_project_path> <output_dir> 2>/dev/null
```

## Decision: unconvertible or partial materials

**Question:** What to do when a Unity material cannot be fully mapped to Roblox?

**Factors:**
- How much of the material's visual identity is carried by the albedo vs. by shader effects (emission, parallax, refraction).
- Whether the material is used on gameplay-critical surfaces (character, key props) or on background geometry.
- The material's rendering mode. Opaque materials with only Color3 are easy wins; custom shaders are not.

**Options:**
- **Accept the partial mapping.** Default. The converter uses albedo + roughness/metalness where available; other effects are dropped.
- **Provide manual override.** For critical materials, override the `RobloxMaterialDef` entry with hand-chosen Color3/SurfaceAppearance values.
- **Skip the material.** The mesh using it falls back to default gray. Only for test assets or debug props.

**Escape hatch:** Read `UNCONVERTED.md` in the output directory. The converter lists every material it couldn't fully handle with the reason — use this to triage.

## SurfaceAppearance rules

**SurfaceAppearance without a ColorMap makes the part white.** SurfaceAppearance completely overrides `Part.Color3` for rendering. A material with metalness/roughness textures but no albedo produces an all-white part — Color3 is ignored.

**Rule:** Only create SurfaceAppearance when `rdef.color_map` is present. Materials with only metalness/roughness rely on Color3 alone. Enforced in `conversion_helpers.py:apply_materials()`.

**Missing SurfaceAppearance on vertex-color meshes.** Vertex-color-only materials create an empty `RobloxMaterialDef` that depends on baking to fill the `color_map` later. If baking fails or the mesh path doesn't match the `vc_baked_textures` lookup key, the MeshPart ends up with no SurfaceAppearance at all.

**Diagnostic:** After assembly, scan the `.rbxl` for MeshParts that have a `MeshId` but no SurfaceAppearance child. If the Unity source had an albedo for that mesh's material, the SurfaceAppearance was dropped and must be restored manually.

## Opaque-mode alpha bug

Unity's Standard shader discards `_Color.a` in Opaque mode (`_Mode = 0`), and many opaque materials ship with `a=0`. If the converter blindly applies `1.0 - _Color.a` as `base_part_transparency`, textured MeshParts become fully invisible despite having a valid renderer.

**Rule:** Only apply alpha transparency when `parsed.render_mode != 0`. Enforced in `material_mapper.py`.

**Symptom:** MeshPart has SurfaceAppearance with textures but is still invisible → check the source `.mat` file for `_Mode: 0` and `_Color: {... a: 0}`.

## Split meshes

`mesh_splitter.py` splits multi-material meshes into per-material OBJs under `split_meshes/`. The uploader only scans `meshes/`, so split submeshes may not get uploaded — the `.rbxl` falls back to the unsplit mesh asset, which may include bone geometry separated out by the split.

**Rule:** If `_sub0.obj` files exist in `split_meshes/`, verify the uploaded single-asset fallback still renders correctly. A mesh rendering as skeleton bones or wireframe is the tell.
