# Smartdown Template: UNCONVERTED.md

> This file documents the template structure for the `UNCONVERTED.md` file
> that the converter generates alongside each `.rbxl` output. The actual
> file is populated at runtime by `material_mapper.py` and `report_generator.py`.

## Design Philosophy

The Smartdown file ("UNCONVERTED.md") is a living document that:

1. **Tracks every feature the converter couldn't handle** for a specific game
2. **Provides actionable workarounds** — either future automation targets or manual steps
3. **Shrinks over time** as the converter gains capabilities
4. **Estimates manual effort** so teams can scope the remaining work

The long-term goal: even the most complex Unity games eventually produce an empty
UNCONVERTED.md, meaning the conversion is fully automated.

## Template Structure

```markdown
# Unconverted Features Report

> Generated: {ISO_TIMESTAMP}
> Converter Version: {VERSION}
> Unity Project: {PROJECT_NAME}
> Unity Pipeline: {BUILTIN | URP | HDRP | MIXED}

## Conversion Statistics

| Metric | Value |
|--------|-------|
| Total materials processed | {N} |
| Fully converted (no issues) | {M} |
| Partially converted (some features lost) | {P} |
| Skipped (unrecognized shader) | {S} |
| Total textures processed | {T} |
| Total textures generated (channel extraction) | {G} |

## Unconverted Feature Summary

| Feature | Materials Affected | Severity | Auto-Fixable (Future) |
|---------|--------------------|----------|-----------------------|
| Height/parallax maps | {n} | MEDIUM | Yes — height-to-normal conversion |
| Detail albedo maps | {n} | MEDIUM | Yes — composite baking |
| Detail normal maps | {n} | MEDIUM | Yes — normal blending |
| UV tiling ≠ (1,1) | {n} | HIGH | Partial — pre-tile ≤4x |
| UV offset ≠ (0,0) | {n} | LOW | Yes — pixel shift |
| Specular workflow materials | {n} | MEDIUM | Partial — heuristic conversion |
| Custom Shader Graph shaders | {n} | VARIABLE | No — manual property mapping |
| Subsurface scattering (HDRP) | {n} | LOW | No equivalent in Roblox |
| Anisotropy (HDRP) | {n} | LOW | No equivalent in Roblox |
| Iridescence (HDRP) | {n} | LOW | No equivalent in Roblox |
| Clear coat (HDRP) | {n} | LOW | No equivalent in Roblox |
| Multi-material meshes | {n} | HIGH | Maybe — mesh splitting |
| Secondary UV channels (UV1+) | {n} | MEDIUM | No — Roblox supports UV0 only |
| Cubemap reflections (legacy) | {n} | LOW | No per-material cubemaps |
| Vertex color usage | {n} | LOW | Not investigated |
| Particle shader materials | {n} | MEDIUM | Partial — static texture only |
| Skybox materials | {n} | MEDIUM | Yes — Roblox Skybox mapping |
| Terrain splat maps | {n} | HIGH | Partial — MaterialVariant |
| Normal map scale ≠ 1.0 | {n} | LOW | Yes — bake into normal map |
| Per-pixel emission color | {n} | MEDIUM | Partial — luminance + average tint |

## Per-Material Details

{FOR EACH MATERIAL WITH ISSUES:}

### {Material Name} (`{relative_path}`)

**Shader**: `{shader_name}`
**Pipeline**: {BUILTIN | URP | HDRP}

#### Successfully Converted
{FOR EACH CONVERTED PROPERTY:}
- [x] {property_description} → {roblox_target}
  - Source: `{unity_property_name}` = `{value_or_texture_path}`
  - Output: `{output_texture_filename}` or `{roblox_property} = {value}`

#### Requires Manual Work
{FOR EACH UNCONVERTED PROPERTY:}
- [ ] **{feature_name}** — {reason_not_converted}
  - Unity property: `{property_name}` = `{value_or_texture_path}`
  - Severity: {LOW | MEDIUM | HIGH}
  - Workaround: {description_of_manual_fix}
  - Estimated effort: {time_estimate}
  - Future automation: {YES_description | NO_reason}

#### Warnings
{FOR EACH WARNING:}
- ⚠ {warning_message}

---

## Texture Processing Log

| Source Texture | Operation | Output | Notes |
|----------------|-----------|--------|-------|
| `{input_path}` | Channel extract R | `{output_metalness}` | From MetallicGlossMap |
| `{input_path}` | Channel extract A + invert | `{output_roughness}` | Smoothness → Roughness |
| `{input_path}` | Resize 2048→1024 | `{output_path}` | Roblox max resolution |
| `{input_path}` | AO bake into albedo | `{output_path}` | OcclusionMap * ColorMap |
| `{input_path}` | Luminance grayscale | `{output_emissive}` | EmissionMap → mask |
| `{input_path}` | Pre-tile 2x2 | `{output_path}` | Tiling workaround |
| `{input_path}` | Alpha threshold at 0.5 | `{output_path}` | Cutoff bake |

## Future Automation Roadmap

Features listed in priority order based on frequency across games:

### Phase 1 (Next Release)
1. **UV tiling injection** — Modify FBX mesh UVs to embed tiling factors
   - Affects: {n} materials across {g} games analyzed
   - Approach: Parse FBX, scale UV coordinates, re-export

2. **Detail map baking** — Composite detail textures into base
   - Affects: {n} materials
   - Approach: PIL composite with tiling ratio + detail mask

3. **Normal map scale baking** — Adjust normal intensity in texture
   - Affects: {n} materials
   - Approach: Scale XY channels, renormalize Z

### Phase 2 (Future)
4. **Height-to-normal conversion** — Generate normal detail from height maps
   - Approach: Sobel filter on height map, blend into existing normal

5. **Specular-to-metallic ML model** — Better spec→metal conversion
   - Approach: Train on paired datasets

6. **Multi-material mesh splitting** — Split meshes at material boundaries
   - Approach: Parse FBX submeshes, create separate MeshParts

### Phase 3 (Long-Term)
7. **Custom Shader Graph analysis** — Parse .shadergraph files
   - Approach: Extract exposed properties and node connections

8. **Terrain splat map → MaterialVariant** — Full terrain conversion
   - Approach: Create MaterialVariants per splat layer

## Appendix: Roblox Limitations Reference

These are engine-level limitations that cannot be worked around:

| Limitation | Status | Tracking |
|------------|--------|----------|
| No custom shaders | Permanent | N/A |
| 1 material per MeshPart | Permanent | N/A |
| UV0 only | Permanent | N/A |
| No height/displacement mapping | Permanent | N/A |
| No SSS/anisotropy/iridescence | No plans announced | N/A |
| No per-material cubemap reflections | Engine uses probes | N/A |
| Max 1024x1024 texture (reliable) | Platform limit | N/A |
| SurfaceAppearance: MeshPart only | By design | N/A |
| No runtime SurfaceAppearance changes | PluginSecurity | N/A |
| No SurfaceAppearance tiling/offset | Feature request open | DevForum #928282 |
```

## Integration Points

The Smartdown file is generated by two modules:

1. **`material_mapper.py`** — produces per-material conversion results with
   lists of converted properties, unconverted properties, and warnings

2. **`report_generator.py`** — aggregates material results into the final
   UNCONVERTED.md alongside the existing JSON conversion report

### Data Contract

`material_mapper.py` returns a `MaterialConversionResult` per material:

```python
@dataclass
class UnconvertedFeature:
    feature_name: str           # e.g., "Height/parallax map"
    unity_property: str         # e.g., "_ParallaxMap"
    unity_value: str            # e.g., "Assets/Textures/height.png"
    severity: str               # "LOW" | "MEDIUM" | "HIGH"
    workaround: str             # Human-readable workaround description
    effort_minutes: int         # Estimated manual fix time
    auto_fixable_future: bool   # Could future version handle this?
    auto_fix_description: str   # How future automation would work

@dataclass
class ConvertedProperty:
    description: str            # e.g., "Albedo texture"
    unity_source: str           # e.g., "_MainTex = Assets/Textures/albedo.png"
    roblox_target: str          # e.g., "ColorMap = albedo_converted.png"

@dataclass
class MaterialConversionResult:
    material_name: str
    material_path: Path
    shader_name: str
    pipeline: str               # "BUILTIN" | "URP" | "HDRP" | "LEGACY" | "CUSTOM"
    fully_converted: bool
    converted: list[ConvertedProperty]
    unconverted: list[UnconvertedFeature]
    warnings: list[str]
    textures_generated: list[str]  # Output texture filenames
```
