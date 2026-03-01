# Unity-to-Roblox Material Mapping: Comprehensive Research

> Research date: March 2026
> Status: Design specification for `material_mapper.py` module

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Unity Material System Overview](#unity-material-system-overview)
3. [Roblox Material System Overview](#roblox-material-system-overview)
4. [Property-by-Property Mapping](#property-by-property-mapping)
5. [Texture Processing Requirements](#texture-processing-requirements)
6. [Unconvertible Features & Workarounds](#unconvertible-features--workarounds)
7. [The `_Color` Question: Tint vs. ColorMap](#the-_color-question-tint-vs-colormap)
8. [Alpha/Transparency Mode Mapping](#alphatransparency-mode-mapping)
9. [Emission Mapping (New as of Feb 2026)](#emission-mapping)
10. [Tiling and Offset](#tiling-and-offset)
11. [Pipeline-Specific Property Names](#pipeline-specific-property-names)
12. [`.mat` File Parsing Strategy](#mat-file-parsing-strategy)
13. [Conversion Decision Flowchart](#conversion-decision-flowchart)
14. [Smartdown File Design](#smartdown-file-design)

---

## Executive Summary

This document maps Unity's material/shader properties to Roblox's `SurfaceAppearance` + `BasePart` system. The core finding is that **~70% of common Unity material properties have direct or close Roblox equivalents**, thanks to Roblox's recent PBR additions (SurfaceAppearance tinting Nov 2024, Emissive Masks Feb 2026). The remaining ~30% are advanced features (SSS, anisotropy, detail maps, height maps, tiling) that require either workarounds or must be logged for manual intervention.

**No existing Unity-to-Roblox material converter exists.** This module fills a genuine ecosystem gap.

### What IS Convertible (Automated)

| Feature | Confidence |
|---------|------------|
| Albedo texture + color tint | Direct mapping |
| Normal maps | Direct (may need green channel flip) |
| Metallic maps | Channel extraction from packed texture |
| Roughness (from smoothness) | Channel extraction + inversion |
| Emission maps + color | Grayscale mask + tint + strength |
| Render mode (opaque/cutout/transparent) | AlphaMode mapping |
| Occlusion maps | Bake into ColorMap (multiply) |
| Flat color materials (no textures) | BasePart.Color3 |

### What is NOT Convertible (Logged to Smartdown)

| Feature | Severity |
|---------|----------|
| Height/parallax maps | Medium — visual-only loss |
| Detail maps (secondary textures) | Medium — can bake offline |
| Tiling & offset (non-1x1) | High — requires UV modification |
| Subsurface scattering (HDRP) | Low — rare in game assets |
| Anisotropy (HDRP) | Low — rare |
| Iridescence (HDRP) | Low — rare |
| Clear coat (HDRP) | Low — rare |
| Custom Shader Graph shaders | Variable — best-effort property extraction |
| Multi-material meshes | High — Roblox is 1 material per MeshPart |
| UV1+ (secondary UV channels) | Medium — only UV0 supported |

---

## Unity Material System Overview

### Render Pipelines and Their Shaders

Unity has three render pipelines, each with different shader property names for the same concepts:

| Pipeline | Primary Lit Shader | Shader Name in `.mat` |
|----------|-------------------|----------------------|
| Built-in | Standard | `Standard` (fileID: 46) |
| Built-in | Standard (Specular) | `Standard (Specular setup)` (fileID: 45) |
| URP | Lit | `Universal Render Pipeline/Lit` |
| URP | Simple Lit | `Universal Render Pipeline/Simple Lit` |
| URP | Unlit | `Universal Render Pipeline/Unlit` |
| HDRP | Lit | `HDRP/Lit` |
| Any | Custom (Shader Graph) | Varies by asset GUID |

### Built-in Standard Shader — Complete Property List

| Property Name | Type | Default | Description |
|---------------|------|---------|-------------|
| `_Color` | Color | `(1,1,1,1)` | Albedo tint (multiplied with `_MainTex`) |
| `_MainTex` | Texture2D | white | Albedo/diffuse texture |
| `_Cutoff` | Float 0-1 | 0.5 | Alpha cutoff threshold |
| `_Glossiness` | Float 0-1 | 0.5 | Smoothness value (when no map) |
| `_GlossMapScale` | Float 0-1 | 1.0 | Smoothness scale (when using map) |
| `_SmoothnessTextureChannel` | Float | 0 | 0=Metallic Alpha, 1=Albedo Alpha |
| `_Metallic` | Float 0-1 | 0.0 | Metallic value (when no map) |
| `_MetallicGlossMap` | Texture2D | white | R=Metallic, A=Smoothness |
| `_BumpScale` | Float | 1.0 | Normal map intensity |
| `_BumpMap` | Texture2D | bump | Normal map (tangent space) |
| `_Parallax` | Float 0.005-0.08 | 0.02 | Height/parallax intensity |
| `_ParallaxMap` | Texture2D | black | Height map |
| `_OcclusionStrength` | Float 0-1 | 1.0 | AO strength |
| `_OcclusionMap` | Texture2D | white | Ambient occlusion |
| `_EmissionColor` | Color HDR | `(0,0,0)` | Emission color/intensity |
| `_EmissionMap` | Texture2D | white | Emission texture |
| `_DetailMask` | Texture2D | white | Detail mask (where detail shows) |
| `_DetailAlbedoMap` | Texture2D | grey | Secondary albedo |
| `_DetailNormalMapScale` | Float | 1.0 | Secondary normal intensity |
| `_DetailNormalMap` | Texture2D | bump | Secondary normal map |
| `_UVSec` | Float | 0 | UV set for detail (0=UV0, 1=UV1) |
| `_Mode` | Float | 0 | 0=Opaque, 1=Cutout, 2=Fade, 3=Transparent |
| `_SrcBlend` | Float | 1.0 | Blend mode source |
| `_DstBlend` | Float | 0.0 | Blend mode dest |
| `_ZWrite` | Float | 1.0 | Depth write |
| `_SpecularHighlights` | Float | 1.0 | Toggle specular highlights |
| `_GlossyReflections` | Float | 1.0 | Toggle glossy reflections |

### Built-in Standard (Specular) — Differences Only

| Property Name | Type | Default | Replaces |
|---------------|------|---------|----------|
| `_SpecColor` | Color | `(0.2,0.2,0.2)` | `_Metallic` |
| `_SpecGlossMap` | Texture2D | white | `_MetallicGlossMap` |

All other properties identical to Standard.

### URP Lit — Property Name Differences

| Concept | Built-in Name | URP Name |
|---------|--------------|----------|
| Albedo texture | `_MainTex` | `_BaseMap` |
| Albedo color | `_Color` | `_BaseColor` |
| Smoothness | `_Glossiness` | `_Smoothness` |
| Alpha clip toggle | `_Mode` (0-3) | `_AlphaClip` (0/1) + `_Surface` (0/1) |
| Detail albedo scale | _(implicit)_ | `_DetailAlbedoMapScale` |

### HDRP Lit — Property Name Differences

| Concept | Built-in Name | HDRP Name |
|---------|--------------|-----------|
| Albedo texture | `_MainTex` | `_BaseColorMap` |
| Albedo color | `_Color` | `_BaseColor` |
| Normal map | `_BumpMap` | `_NormalMap` |
| Normal scale | `_BumpScale` | `_NormalScale` |
| Metallic+AO+Smoothness | `_MetallicGlossMap` + `_OcclusionMap` | `_MaskMap` (MODS: R=Metal, G=AO, B=Detail, A=Smooth) |
| Emission map | `_EmissionMap` | `_EmissiveColorMap` |
| Emission color | `_EmissionColor` | `_EmissiveColor` |
| Height map | `_ParallaxMap` | `_HeightMap` |

### HDRP-Only Advanced Properties

| Property | Type | Description |
|----------|------|-------------|
| `_MaterialID` | Enum | 0=SSS, 1=Standard, 2=Anisotropy, 3=Iridescence, 4=SpecularColor, 5=Translucent |
| `_SubsurfaceMask` / `_SubsurfaceMaskMap` | Float/Tex | SSS intensity |
| `_Thickness` / `_ThicknessMap` | Float/Tex | Translucency thickness |
| `_Anisotropy` / `_AnisotropyMap` | Float/Tex | Anisotropic highlight stretch |
| `_IridescenceThickness` / Map | Float/Tex | Thin-film interference |
| `_CoatMask` / `_CoatMaskMap` | Float/Tex | Clear coat layer |
| `_BentNormalMap` | Texture2D | Bent normal for indirect lighting |

### Legacy Shaders

| Shader | Properties |
|--------|-----------|
| `Legacy Shaders/Diffuse` | `_Color`, `_MainTex` |
| `Legacy Shaders/Specular` | + `_SpecColor`, `_Shininess` |
| `Legacy Shaders/Bumped Diffuse` | + `_BumpMap` |
| `Legacy Shaders/Bumped Specular` | + `_SpecColor`, `_Shininess`, `_BumpMap` |
| `Legacy Shaders/Parallax Diffuse` | + `_BumpMap`, `_Parallax`, `_ParallaxMap` |
| `Legacy Shaders/Self-Illumin/*` | + `_Illum` (emission texture) |
| `Legacy Shaders/Reflective/*` | + `_ReflectColor`, `_Cube` (cubemap) |
| `Legacy Shaders/Transparent/Cutout/*` | + `_Cutoff` |

### Special Shaders

| Shader | Key Properties | Roblox Convertibility |
|--------|---------------|----------------------|
| Particles (Additive/Alpha Blended) | `_TintColor`, `_MainTex`, `_InvFade` | Partial — static texture only |
| Skybox/6 Sided | `_FrontTex` through `_DownTex`, `_Tint`, `_Exposure` | Roblox Skybox object |
| Skybox/Procedural | `_SunSize`, `_AtmosphereThickness`, `_SkyTint` | Roblox Atmosphere |
| Skybox/Panoramic | `_MainTex`, `_Rotation` | Roblox Skybox |
| Sprites/Default | `_MainTex`, `_Color` | Decal or ImageLabel |
| UI/Default | `_MainTex`, `_Color`, stencil props | ScreenGui/ImageLabel |
| Terrain | `_Control`, `_Splat0-3`, `_Normal0-3` | Roblox Terrain + MaterialVariant |

---

## Roblox Material System Overview

### SurfaceAppearance (Primary PBR Target)

Applies to `MeshPart` only. One per MeshPart. UV0 only.

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `ColorMap` | ContentId | `""` | Albedo texture (RGBA). Alpha interpreted per AlphaMode. |
| `NormalMap` | ContentId | `""` | OpenGL-format tangent-space normal map |
| `MetalnessMap` | ContentId | `""` | Grayscale. 0=non-metal, 1=metal |
| `RoughnessMap` | ContentId | `""` | Grayscale. 0=smooth, 1=rough |
| `EmissiveMaskContent` | Content | `""` | Grayscale emissive mask. **Live Feb 2026.** |
| `EmissiveStrength` | Float | 1.0 | Emissive intensity multiplier |
| `EmissiveTint` | Color3 | `(1,1,1)` | Emissive color tint |
| `Color` | Color3 | `(1,1,1)` | Tint multiplied with ColorMap. **Live Nov 2024.** |
| `AlphaMode` | Enum | Overlay | How ColorMap alpha is interpreted |

### AlphaMode Enum

| Value | Name | Behavior |
|-------|------|----------|
| 0 | **Overlay** | Alpha blends texture over `BasePart.Color` |
| 1 | **Transparency** | Alpha = see-through transparency |
| 2 | **Opaque** | Alpha ignored entirely |
| 3 | **TintMask** | Alpha controls where `Color` tinting applies |

### BasePart Properties (Relevant to Materials)

| Property | Type | Notes |
|----------|------|-------|
| `Color` | Color3 | Flat color. Shows through SurfaceAppearance in Overlay mode. |
| `Material` | Enum.Material | 45 built-in materials. Overridden visually by SurfaceAppearance. |
| `Transparency` | Float 0-1 | Part-level transparency. Multiplicative with SA alpha. |
| `Reflectance` | Float 0-1 | Legacy. Overridden by PBR when SA present. |

### MaterialVariant (For Tileable Materials)

Similar PBR maps to SurfaceAppearance, but adds `StudsPerTile` for automatic tiling. Applies to any BasePart or Terrain. Lives in `MaterialService`.

### Key Limitations

- **MeshPart only** for SurfaceAppearance (not regular Parts)
- **4096x4096** max texture resolution (Roblox upload limit; 1024x1024 was a conservative budget, not a hard cap)
- **PNG, JPG, TGA, BMP** formats only (no EXR/HDR)
- **No runtime script modification** of SurfaceAppearance maps
- **One material per MeshPart** (no sub-meshes with different materials)
- **UV0 only** (no secondary UV channels)
- **Normal maps must be OpenGL format** (Y+ up)

---

## Property-by-Property Mapping

### Tier 1: Direct Mappings (Automated, High Confidence)

| Unity Property | Roblox Property | Conversion |
|----------------|----------------|------------|
| `_MainTex` / `_BaseMap` / `_BaseColorMap` | `SurfaceAppearance.ColorMap` | Direct file copy (resize to ≤`TEXTURE_MAX_RESOLUTION`, default 4096) |
| `_Color` / `_BaseColor` | `SurfaceAppearance.Color` | Direct Color3 mapping (see [Color section](#the-_color-question-tint-vs-colormap)) |
| `_BumpMap` / `_NormalMap` | `SurfaceAppearance.NormalMap` | Direct copy (verify OpenGL format) |
| `_BumpScale` / `_NormalScale` | _(no Roblox property)_ | Bake into normal map if ≠ 1.0 |
| `_Metallic` (float, no map) | `SurfaceAppearance.MetalnessMap` | Generate uniform grayscale PNG |
| `_Glossiness` / `_Smoothness` (float, no map) | `SurfaceAppearance.RoughnessMap` | Generate uniform grayscale PNG at `1.0 - value` |
| `_Mode` = 0 (Opaque) | `AlphaMode = Opaque` | Direct |
| `_Mode` = 1 (Cutout) | `AlphaMode = Transparency` | Include alpha channel in ColorMap |
| `_Mode` = 2 or 3 (Fade/Transparent) | `AlphaMode = Transparency` | Include alpha + set `Transparency ≥ 0.02` |

### Tier 2: Channel Processing Required (Automated, Medium Confidence)

| Unity Property | Roblox Property | Conversion |
|----------------|----------------|------------|
| `_MetallicGlossMap` R channel | `MetalnessMap` | Extract R → grayscale PNG |
| `_MetallicGlossMap` A channel | `RoughnessMap` | Extract A, invert → grayscale PNG |
| `_MaskMap` (HDRP) R channel | `MetalnessMap` | Extract R → grayscale PNG |
| `_MaskMap` (HDRP) A channel | `RoughnessMap` | Extract A, invert → grayscale PNG |
| `_MaskMap` (HDRP) G channel | _(bake into ColorMap)_ | Multiply AO into albedo |
| `_OcclusionMap` | _(bake into ColorMap)_ | Multiply AO into albedo texture |
| `_EmissionMap` (RGB) | `EmissiveMaskContent` | Convert to grayscale luminance |
| `_EmissionColor` (HDR) | `EmissiveTint` + `EmissiveStrength` | Split color and intensity |
| `_SmoothnessTextureChannel` = 1 | _(affects extraction)_ | Extract smoothness from albedo alpha instead of metallic alpha |

### Tier 3: Workarounds Needed (Semi-Automated, Low Confidence)

| Unity Property | Workaround | Notes |
|----------------|-----------|-------|
| `_OcclusionMap` | Bake AO into ColorMap | `final_albedo = albedo * lerp(1, ao, _OcclusionStrength)` |
| `_BumpScale ≠ 1.0` | Modify normal map Z | Scale XY channels, renormalize |
| Specular workflow (`_SpecColor`) | Convert to metallic | Approximate: high spec luminance → metal=1, low → metal=0 |
| `_Shininess` (legacy) | Convert to roughness | `roughness = 1.0 - sqrt(_Shininess)` (approximation) |

### Tier 4: Not Convertible (Logged to Smartdown)

| Unity Property | Reason |
|----------------|--------|
| `_ParallaxMap` / `_HeightMap` | No Roblox height/displacement support |
| `_DetailAlbedoMap` | No secondary texture layer |
| `_DetailNormalMap` | No secondary texture layer |
| `_DetailMask` | No detail system |
| `_UVSec = 1` (UV1 for details) | Only UV0 supported |
| `_SubsurfaceMask*` (HDRP) | No SSS support |
| `_Anisotropy*` (HDRP) | No anisotropic reflections |
| `_IridescenceThickness*` (HDRP) | No thin-film interference |
| `_CoatMask*` (HDRP) | No clear coat layer |
| `_BentNormalMap` (HDRP) | No bent normal support |
| `_Cube` (legacy reflective) | No per-material cubemap reflection |
| Tiling `_ST.xy ≠ (1,1)` | No SurfaceAppearance tiling (see [Tiling section](#tiling-and-offset)) |
| Offset `_ST.zw ≠ (0,0)` | No SurfaceAppearance offset |

---

## Texture Processing Requirements

### Channel Extraction Pipeline

```
Unity _MetallicGlossMap (RGBA)
├── R channel ──────────────────→ MetalnessMap.png (grayscale)
├── G channel ──────────────────→ (discarded)
├── B channel ──────────────────→ (discarded)
└── A channel ──invert──────────→ RoughnessMap.png (grayscale)

Unity HDRP _MaskMap (RGBA) — "MODS" packing
├── R channel (Metallic) ──────→ MetalnessMap.png (grayscale)
├── G channel (Occlusion) ─────→ multiply into ColorMap
├── B channel (Detail mask) ───→ (discarded, or use for detail baking)
└── A channel (Smoothness) ──invert──→ RoughnessMap.png (grayscale)
```

### Smoothness Source Handling

```python
if _SmoothnessTextureChannel == 0:  # Metallic Alpha (default)
    smoothness_source = metallic_gloss_map.alpha_channel
elif _SmoothnessTextureChannel == 1:  # Albedo Alpha
    smoothness_source = main_tex.alpha_channel

roughness = 1.0 - (smoothness_source * _GlossMapScale)
```

### Normal Map Format

- Unity Standard/URP: **OpenGL format** (Y+ up) — same as Roblox
- Some Unity assets use DirectX format (Y- up, common when assets come from Substance Painter or Unreal)
- **Detection**: If the normal map looks inverted (dents instead of bumps), the green channel needs flipping
- **Safe approach**: Offer a flag to flip green channel, default OFF for Standard/URP, flagged for review

### Normal Map Scale Baking

When `_BumpScale ≠ 1.0`, the converter should modify the normal map:

```python
# Scale the XY components, renormalize
nx = (normal_r / 127.5 - 1.0) * bump_scale
ny = (normal_g / 127.5 - 1.0) * bump_scale
nz = normal_b / 127.5 - 1.0
length = sqrt(nx*nx + ny*ny + nz*nz)
# Write back normalized
```

### Occlusion Baking

When `_OcclusionMap` is present, bake into ColorMap:

```python
for each pixel:
    ao_value = occlusion_map[pixel]  # 0=fully occluded, 1=no occlusion
    strength = _OcclusionStrength
    effective_ao = lerp(1.0, ao_value, strength)
    final_albedo[pixel] = albedo[pixel] * effective_ao
```

### Texture Sizing

- Roblox accepts textures up to **4096x4096** (the upload API limit)
- `config.TEXTURE_MAX_RESOLUTION` (default 4096) controls the ceiling; textures exceeding this are downscaled
- Aspect ratio preserved; non-square textures are fine
- Uniform-value textures (e.g., metallic = 0.0 everywhere) can be a tiny 4x4 PNG

---

## Unconvertible Features & Workarounds

### Height/Parallax Maps

**Status**: No Roblox equivalent. No planned support.

**Workaround options** (for Smartdown file):
1. Convert height map to additional normal map detail (automated possible)
2. Bake displacement into mesh geometry (requires mesh modification — future work)
3. Drop entirely (minimal visual impact for subtle parallax)

### Detail Maps

**Status**: No multi-layer texturing in Roblox.

**Workaround** (automated possible but complex):
1. Composite detail albedo into main albedo, respecting detail mask and tiling difference
2. Blend detail normal into main normal using reoriented normal mapping
3. Requires resolving different tiling rates between base and detail

**Recommendation**: Phase 1 — log to Smartdown. Phase 2 — implement automated baking.

### Specular-to-Metallic Conversion

When a Unity material uses the Specular workflow (`Standard (Specular setup)`), we need to approximate metallic values:

```python
spec_luminance = 0.2126 * _SpecColor.r + 0.7152 * _SpecColor.g + 0.0722 * _SpecColor.b

if spec_luminance > 0.5:
    metallic ≈ 1.0  # Likely a metal
    albedo = _SpecColor  # For metals, spec color IS the albedo
else:
    metallic ≈ 0.0  # Dielectric
    albedo = _Color * _MainTex  # Standard albedo
```

This is inherently lossy — the Specular workflow is more expressive than Metallic for dielectrics with tinted reflections.

### Subsurface Scattering / Anisotropy / Iridescence / Clear Coat

**Status**: No Roblox equivalent. No known workarounds.

**Action**: Log to Smartdown with severity "visual difference expected."

---

## The `_Color` Question: Tint vs. ColorMap

This was a core research question: should Unity's `_Color` map only to `SurfaceAppearance.Color`, or should it also influence the ColorMap?

### Answer: It depends on the scenario

**Scenario 1: `_Color` + `_MainTex` both present (most common)**

```
Unity:    final_albedo = _MainTex * _Color
Roblox:   final_albedo = ColorMap * SurfaceAppearance.Color
```

These are mathematically equivalent. Map `_MainTex` → `ColorMap`, `_Color` → `SurfaceAppearance.Color`. **Do NOT bake the color into the texture** — this preserves the tint as an editable property in Roblox Studio.

**Scenario 2: `_Color` present, NO `_MainTex` (flat color material)**

No texture to upload. Two options:

- **Option A (preferred)**: Set `BasePart.Color3 = _Color.rgb`. Don't use SurfaceAppearance at all — use a built-in Material like `SmoothPlastic` for a flat look.
- **Option B**: Create a 4x4 white PNG as ColorMap, set `SurfaceAppearance.Color = _Color.rgb`.

**Scenario 3: `_Color` is white `(1,1,1)` (default, no tint)**

Skip setting `SurfaceAppearance.Color` — the default `(1,1,1)` is already "no tint."

**Scenario 4: `_Color` has alpha < 1**

In Unity, `_Color.a` multiplies the albedo alpha, affecting transparency. In Roblox, `SurfaceAppearance.Color` is Color3 (no alpha). Handle by:
- If `AlphaMode = Transparency`, bake `_Color.a` into the ColorMap's alpha channel
- Otherwise, set `BasePart.Transparency = 1.0 - _Color.a`

### Summary Decision

| Condition | Roblox Target |
|-----------|--------------|
| `_Color` ≠ white, `_MainTex` present | `SurfaceAppearance.Color = _Color.rgb` |
| `_Color` = white | Don't set (use default) |
| `_Color` present, no `_MainTex` | `BasePart.Color3 = _Color.rgb` (no SA needed) |
| `_Color.a < 1.0` | Bake into alpha or set `BasePart.Transparency` |

---

## Alpha/Transparency Mode Mapping

| Unity `_Mode` | Unity Behavior | Roblox Mapping | Additional Steps |
|---------------|---------------|----------------|-----------------|
| 0 (Opaque) | Alpha ignored | `AlphaMode = Opaque` | None |
| 1 (Cutout) | Binary alpha at `_Cutoff` | `AlphaMode = Transparency` | Threshold the alpha channel to binary (0 or 255) at `_Cutoff` value |
| 2 (Fade) | Smooth alpha, no specular | `AlphaMode = Transparency` | Preserve gradient alpha; set `BasePart.Transparency ≥ 0.02` |
| 3 (Transparent) | Smooth alpha, keeps specular | `AlphaMode = Transparency` | Same as Fade (Roblox doesn't distinguish) |

### URP Alpha Handling

URP uses `_Surface` + `_AlphaClip` instead of `_Mode`:
- `_Surface = 0` → Opaque
- `_Surface = 1, _AlphaClip = 0` → Transparent (Fade equivalent)
- `_Surface = 1, _AlphaClip = 1` → Cutout

### Cutoff Baking

Roblox has no `_Cutoff` threshold property. For cutout materials, we must bake the threshold into the texture:

```python
for each pixel:
    if albedo_alpha[pixel] < _Cutoff * 255:
        output_alpha[pixel] = 0     # Fully transparent
    else:
        output_alpha[pixel] = 255   # Fully opaque
```

---

## Emission Mapping

As of February 2026, Roblox supports emissive materials natively via:

| Roblox Property | Type | Description |
|-----------------|------|-------------|
| `EmissiveMaskContent` | Grayscale texture | Where emission occurs (white = full glow) |
| `EmissiveStrength` | Float | Intensity multiplier |
| `EmissiveTint` | Color3 | Color of the emission |

### Unity Emission → Roblox Emission

Unity's emission is: `emission_output = _EmissionMap * _EmissionColor`

Where `_EmissionMap` is RGB and `_EmissionColor` is HDR Color.

Roblox's emission is approximately: `emission_output = ColorMap * EmissiveMask * EmissiveStrength * EmissiveTint`

**Key difference**: Unity's emission is additive and independent of albedo. Roblox's emission uses the ColorMap color as a base, modulated by the mask.

### Conversion Strategy

**Case 1: Uniform emission color (most common)**

```python
# Unity has _EmissionMap (RGB) + _EmissionColor (r, g, b, intensity)
emission_mask = luminance(_EmissionMap)  # Convert RGB → grayscale
emissive_tint = normalize(_EmissionColor.rgb)  # Just the color direction
emissive_strength = magnitude(_EmissionColor) * max(emission_mask)

# Output:
# EmissiveMaskContent = emission_mask (grayscale PNG)
# EmissiveTint = emissive_tint
# EmissiveStrength = emissive_strength
```

**Case 2: Per-pixel emission color (complex)**

When `_EmissionMap` has varying colors per pixel, the grayscale mask loses color information. Workaround:

1. Extract luminance of `_EmissionMap` → `EmissiveMaskContent`
2. Extract dominant/average color → `EmissiveTint`
3. For emissive regions, bake the emission RGB into the `ColorMap` so the `ColorMap * EmissiveMask * EmissiveTint` product approximates the original emission color
4. Log to Smartdown that per-pixel emission color was approximated

**Case 3: No emission map, only `_EmissionColor` > 0**

```python
# Uniform emission across entire surface
EmissiveMaskContent = uniform white 4x4 PNG
EmissiveTint = _EmissionColor.rgb (normalized)
EmissiveStrength = luminance(_EmissionColor)
```

**Case 4: Legacy `_Illum` texture (Self-Illumin shaders)**

```python
EmissiveMaskContent = _Illum (already grayscale mask)
EmissiveTint = (1, 1, 1)
EmissiveStrength = 1.0
```

---

## Tiling and Offset

### The Problem

Unity materials store tiling and offset in `_TexName_ST` vectors:
```yaml
m_Scale: {x: 4, y: 4}    # tile 4x in each direction
m_Offset: {x: 0.25, y: 0}  # shift 25% in X
```

Roblox `SurfaceAppearance` has **NO tiling or offset properties.** Textures map 1:1 to the mesh's UV0.

### Conversion Strategy

**When tiling ≠ (1, 1):**

1. **Pre-tile the texture** (automated):
   - Create a new texture that is the source tiled N×M times
   - Downscale to fit within `TEXTURE_MAX_RESOLUTION` (default 4096)
   - Loss: resolution per-tile decreases as tiling factor increases
   - Example at 4096 ceiling: 512x512 texture tiled 4x4 → 2048x2048 → fits under ceiling, no downscale needed
   - Example at 1024 ceiling: 512x512 texture tiled 4x4 → 2048x2048 → downscale to 1024x1024 → each tile is 256x256

2. **Modify mesh UVs** (better quality but requires mesh processing):
   - Scale all UV coordinates by the tiling factor
   - Requires access to the mesh file and a UV editing step
   - Best for high tiling factors

3. **Log to Smartdown** if tiling factor is high (>4x) — quality loss from pre-tiling may be unacceptable

**When offset ≠ (0, 0):**

1. Shift texture pixels by the offset amount (PIL `ImageChops.offset`)
2. Simple and lossless

### Decision Matrix

| Tiling Factor | Strategy | Quality |
|--------------|----------|---------|
| (1, 1) | No action | Perfect |
| (2, 2) or smaller | Pre-tile texture | Good |
| (2, 2) to (4, 4) | Pre-tile + warn | Acceptable |
| > (4, 4) | Log to Smartdown for UV modification | Manual needed |

---

## Pipeline-Specific Property Names

The converter must normalize property names across pipelines. This mapping table is the core of the parser:

| Concept | Built-in | URP | HDRP | Normalized Key |
|---------|----------|-----|------|---------------|
| Albedo texture | `_MainTex` | `_BaseMap` | `_BaseColorMap` | `albedo_tex` |
| Albedo color | `_Color` | `_BaseColor` | `_BaseColor` | `albedo_color` |
| Normal map | `_BumpMap` | `_BumpMap` | `_NormalMap` | `normal_tex` |
| Normal scale | `_BumpScale` | `_BumpScale` | `_NormalScale` | `normal_scale` |
| Metallic value | `_Metallic` | `_Metallic` | `_Metallic` | `metallic` |
| Metallic map | `_MetallicGlossMap` | `_MetallicGlossMap` | `_MaskMap` | `metallic_tex` |
| Smoothness value | `_Glossiness` | `_Smoothness` | `_Smoothness` | `smoothness` |
| Smoothness scale | `_GlossMapScale` | `_Smoothness` | `_SmoothnessRemapMax` | `smoothness_scale` |
| Smoothness source | `_SmoothnessTextureChannel` | `_SmoothnessTextureChannel` | _(always MaskMap A)_ | `smoothness_src` |
| AO map | `_OcclusionMap` | `_OcclusionMap` | `_MaskMap` (G) | `ao_tex` |
| AO strength | `_OcclusionStrength` | `_OcclusionStrength` | `_AORemapMax` | `ao_strength` |
| Emission map | `_EmissionMap` | `_EmissionMap` | `_EmissiveColorMap` | `emission_tex` |
| Emission color | `_EmissionColor` | `_EmissionColor` | `_EmissiveColor` | `emission_color` |
| Height map | `_ParallaxMap` | `_ParallaxMap` | `_HeightMap` | `height_tex` |
| Height scale | `_Parallax` | `_Parallax` | `_HeightAmplitude` | `height_scale` |
| Detail albedo | `_DetailAlbedoMap` | `_DetailAlbedoMap` | `_DetailMap` | `detail_albedo_tex` |
| Detail normal | `_DetailNormalMap` | `_DetailNormalMap` | `_DetailMap` | `detail_normal_tex` |
| Detail mask | `_DetailMask` | `_DetailMask` | `_MaskMap` (B) | `detail_mask_tex` |
| Alpha cutoff | `_Cutoff` | `_Cutoff` | `_Cutoff` | `alpha_cutoff` |
| Render mode | `_Mode` | `_Surface`+`_AlphaClip` | surface type | `render_mode` |
| Specular color | `_SpecColor` | `_SpecColor` | `_SpecularColor` | `specular_color` |
| Specular map | `_SpecGlossMap` | `_SpecGlossMap` | `_SpecularColorMap` | `specular_tex` |

---

## `.mat` File Parsing Strategy

### File Structure

```yaml
%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!21 &2100000
Material:
  m_Name: MyMaterial
  m_Shader: {fileID: 46, guid: 0000000000000000f000000000000000, type: 0}
  m_ShaderKeywords: _EMISSION _NORMALMAP _METALLICGLOSSMAP
  m_SavedProperties:
    serializedVersion: 3
    m_TexEnvs:
    - _MainTex:
        m_Texture: {fileID: 2800000, guid: 6d0752c619fa62b45, type: 3}
        m_Scale: {x: 1, y: 1}
        m_Offset: {x: 0, y: 0}
    m_Floats:
    - _Metallic: 0
    - _Glossiness: 0.5
    - _Mode: 0
    m_Colors:
    - _Color: {r: 1, g: 0.8, b: 0.6, a: 1}
    - _EmissionColor: {r: 0, g: 0, b: 0, a: 1}
```

### Parsing Steps

1. **Strip Unity YAML tags** (`%TAG !u! ...` and `--- !u!21 &...`)
2. **Parse with PyYAML** (already a project dependency)
3. **Identify shader** from `m_Shader.fileID` + `m_Shader.guid`:
   - `fileID: 46, guid: 0000...f000...` → Standard
   - `fileID: 45, guid: 0000...f000...` → Standard (Specular)
   - `fileID: 4800000, guid: <custom>` → Look up shader by GUID
4. **Extract properties** from `m_SavedProperties`:
   - `m_TexEnvs` → texture references (resolve GUIDs via `.meta` files)
   - `m_Floats` → scalar values
   - `m_Colors` → color values
5. **Normalize** using the pipeline-specific property name table
6. **Check `m_ShaderKeywords`** to verify which features are actually enabled

### GUID Resolution

Every texture in `m_TexEnvs` references a GUID:
```yaml
m_Texture: {fileID: 2800000, guid: 6d0752c619fa62b45bf892ecc8b0a258, type: 3}
```

To find the actual file:
1. Scan all `.meta` files in the project
2. Build a map: `GUID → file path`
3. Look up the GUID to get the texture file path

The `AssetManifest` from `asset_extractor.py` already tracks `.meta` files — we can extend it to build this GUID map.

### Shader Keyword Significance

`m_ShaderKeywords` tells us which features are enabled:

| Keyword | Meaning |
|---------|---------|
| `_NORMALMAP` | Normal map is active |
| `_METALLICGLOSSMAP` | Metallic texture map is used |
| `_PARALLAXMAP` | Height/parallax is active |
| `_EMISSION` | Emission is active |
| `_DETAIL_MULX2` | Detail maps are active |
| `_ALPHATEST_ON` | Cutout mode |
| `_ALPHABLEND_ON` | Fade mode |
| `_ALPHAPREMULTIPLY_ON` | Transparent mode |
| `_SPECGLOSSMAP` | Specular map is used (specular workflow) |

If a keyword is missing, the corresponding texture property can be ignored even if it has a GUID reference — it's not active.

---

## Conversion Decision Flowchart

```
Parse .mat YAML
       │
       ▼
Identify shader (Built-in / URP / HDRP / Legacy / Custom)
       │
       ▼
Normalize property names to unified keys
       │
       ▼
Check m_ShaderKeywords → determine active features
       │
       ▼
┌──────┴──────┐
│ For each    │
│ property:   │
└──────┬──────┘
       │
       ├─ albedo_tex present? ──→ Resolve GUID → copy as ColorMap
       │                          Apply tiling if ≠ (1,1)
       │                          Apply offset if ≠ (0,0)
       │
       ├─ albedo_color ≠ white? ─→ Set SurfaceAppearance.Color
       │   └─ albedo_color.a < 1? → Bake alpha or set Transparency
       │
       ├─ normal_tex present? ──→ Resolve GUID → copy as NormalMap
       │   └─ normal_scale ≠ 1? → Bake scale into normal map
       │
       ├─ metallic_tex present? ─→ Extract R → MetalnessMap
       │                           Extract A → invert → RoughnessMap
       │   └─ HDRP MaskMap? ────→ Also extract G → bake AO into ColorMap
       │
       ├─ metallic (float only)? → Generate uniform MetalnessMap
       │
       ├─ smoothness (float only)? → Generate uniform RoughnessMap (1-val)
       │
       ├─ ao_tex present? ──────→ Bake into ColorMap (multiply)
       │
       ├─ emission active? ─────→ Convert emission map → EmissiveMaskContent
       │                          Extract color → EmissiveTint
       │                          Extract intensity → EmissiveStrength
       │
       ├─ render_mode? ─────────→ Map to AlphaMode
       │   └─ cutout? → Threshold alpha channel at _Cutoff
       │
       ├─ height_tex present? ──→ LOG TO SMARTDOWN (not convertible)
       ├─ detail maps present? ─→ LOG TO SMARTDOWN (not convertible)
       ├─ SSS/aniso/iridescence? → LOG TO SMARTDOWN (not convertible)
       └─ tiling ≠ (1,1)? ─────→ Pre-tile or LOG TO SMARTDOWN
```

---

## Smartdown File Design

The converter generates a Markdown file per conversion run that tracks everything it couldn't fully convert. The intent is that this file shrinks over time as the converter improves.

### File Name

`UNCONVERTED.md` (placed in the output directory alongside the `.rbxl`)

### Structure

```markdown
# Unconverted Features Report
> Generated: {timestamp}
> Unity Project: {project_name}
> Total Materials: {N}
> Fully Converted: {M}
> Partially Converted: {P}
> Skipped: {S}

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Height/parallax maps | {n} | Medium |
| Detail maps | {n} | Medium |
| Non-unit tiling | {n} | High |
| SSS materials | {n} | Low |
| Custom shaders | {n} | Variable |
| Multi-material meshes | {n} | High |
| ... | ... | ... |

## Materials Requiring Manual Work

### {MaterialName} ({shader_name})
- **File**: `Assets/Materials/MaterialName.mat`
- **Status**: Partially converted
- **Converted**:
  - [x] Albedo texture → ColorMap
  - [x] Normal map → NormalMap
  - [x] Metallic/roughness extraction
- **Unconverted**:
  - [ ] Height map (`_ParallaxMap`) — No Roblox equivalent
    - *Workaround*: Convert to normal map detail, or bake into mesh geometry
  - [ ] Tiling (4x, 4x) — SurfaceAppearance has no tiling property
    - *Workaround*: Pre-tile texture (quality loss) or modify mesh UVs
- **Estimated manual effort**: ~15 minutes

### {MaterialName2} ...

## Future Automation Opportunities

Features that could be automated in future converter versions:
1. **Detail map baking** — Composite detail textures into base at correct tiling ratio
2. **Height-to-normal conversion** — Generate additional normal detail from height maps
3. **UV tiling injection** — Modify FBX mesh UVs to embed tiling factors
4. **Specular-to-metallic ML model** — Train a model for better specular→metallic conversion
5. **Per-pixel emission color** — Bake emission colors into ColorMap emissive regions
```

### Categories Tracked

| Category | Severity | Auto-Fixable (Future) |
|----------|----------|----------------------|
| Height/parallax maps | Medium | Yes (height→normal) |
| Detail maps (albedo) | Medium | Yes (composite baking) |
| Detail maps (normal) | Medium | Yes (normal blending) |
| Non-unit tiling | High | Partial (pre-tile ≤4x) |
| Non-zero offset | Low | Yes (pixel shift) |
| Specular workflow conversion | Medium | Partial (heuristic) |
| Custom Shader Graph shaders | Variable | No (property-name guessing) |
| SSS / Anisotropy / Iridescence / Clear Coat | Low | No |
| Multi-material meshes | High | Maybe (mesh splitting) |
| UV1+ (secondary UV channels) | Medium | No |
| Cubemap reflections | Low | No |
| Vertex colors | Low | No |
| Particle shaders | Medium | Partial |
| Skybox materials | Medium | Yes (Roblox Skybox mapping) |
| Terrain splat maps | High | Partial (MaterialVariant) |

---

## References

### Unity Documentation
- [Standard Shader source (GitHub)](https://github.com/TwoTailsGames/Unity-Built-in-Shaders/blob/master/DefaultResourcesExtra/Standard.shader)
- [URP Lit shader source (GitHub)](https://github.com/Unity-Technologies/Graphics/blob/master/Packages/com.unity.render-pipelines.universal/Shaders/Lit.shader)
- [HDRP Lit shader source](https://github.com/UnityTechnologies/ScriptableRenderPipeline/blob/master/com.unity.render-pipelines.high-definition/HDRP/Material/Lit/Lit.shader)
- [Unity Manual: Standard Shader Parameters](https://docs.unity3d.com/Manual/StandardShaderMaterialParameters.html)
- [Unity YAML format](https://docs.unity3d.com/Manual/FormatDescription.html)
- [Unity Class ID Reference](https://docs.unity3d.com/Manual/ClassIDReference.html)

### Roblox Documentation
- [SurfaceAppearance API](https://create.roblox.com/docs/reference/engine/classes/SurfaceAppearance)
- [SurfaceAppearance Guide](https://create.roblox.com/docs/art/modeling/surface-appearance)
- [MaterialVariant API](https://create.roblox.com/docs/reference/engine/classes/MaterialVariant)
- [Material Enum](https://create.roblox.com/docs/reference/engine/enums/Material)
- [AlphaMode Enum](https://create.roblox.com/docs/reference/engine/enums/AlphaMode)
- [SurfaceAppearance Tinting (Full Release)](https://devforum.roblox.com/t/full-release-surfaceappearance-tinting/3129960)
- [Emissive Masks (Live Release)](https://devforum.roblox.com/t/emissive-masks-are-now-live-for-published-experiences/4357705)
- [TintMask (Client Beta)](https://devforum.roblox.com/t/client-beta-introducing-tintmask-for-surfaceappearance/3600497)
- [Texture Specifications](https://create.roblox.com/docs/art/modeling/texture-specifications)

### Community & Tools
- [Roblox for Unity Developers](https://create.roblox.com/docs/unity)
- [MaximumADHD/Roblox-Materials (GitHub)](https://github.com/MaximumADHD/Roblox-Materials)
- [GenPBR texture generator](https://genpbr.com/generate)
