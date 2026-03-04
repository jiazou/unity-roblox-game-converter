# Skill: Review Material Mapper Coverage

## Goal

Expand shader coverage, add missing-dependency warnings, and improve error
reporting in `modules/material_mapper.py`.

## Context

The material mapper converts Unity materials to Roblox SurfaceAppearance
definitions.  It has coverage gaps in the built-in shader table, silently
drops all texture processing when Pillow is missing, and swallows per-texture
errors with no logging.

## Fixes Required

### 1. Expand `_BUILTIN_SHADERS` table

**File**: `material_mapper.py:136-147`
**Current**: 10 entries covering Standard, Legacy Diffuse/Specular, Particles, Sprites.
**Missing**: UI/Default (10750), Unlit/Texture, Unlit/Color, Unlit/Transparent,
Transparent/Diffuse (10703), Transparent/Specular (10704), Self-Illumin (10707),
Mobile/Diffuse, Skybox shaders, Nature/Tree shaders, TextMeshPro shaders.
**Fix**: Add at minimum the top-10 most common missing shaders with correct
property-read flags.

### 2. Warn when Pillow is missing

**File**: `material_mapper.py:1149-1153`
**Current**: `except ImportError: return []` — silently skips ALL texture processing.
**Fix**: Add a warning to the result indicating that Pillow is required for
texture processing.  The `MaterialMapResult.warnings` list should include a
clear message like `"Pillow (PIL) not installed — texture processing skipped"`.

### 3. Log per-texture errors instead of swallowing

**File**: `material_mapper.py:1504-1506`
**Current**: `except Exception: continue` — no logging, no warning.
**Fix**: Append a warning per failed texture to the result, including the
texture filename and error message.  Do not crash; continue processing other
textures.

### 4. Reuse unity_yaml_utils for YAML parsing

**File**: `material_mapper.py:321-326`
**Current**: Separate regex for YAML tag stripping, duplicating logic from
`unity_yaml_utils.py`.
**Fix**: Use `unity_yaml_utils.load_unity_yaml()` if possible, or at minimum
import the shared header-stripping regex to avoid divergence.

### 5. Improve specular-to-metallic conversion

**File**: `material_mapper.py:813-843`
**Current**: Binary threshold — luminance > 0.5 → metallic=1.0, else metallic=0.0.
**Fix**: Use a continuous mapping: `metallic = clamp(luminance * 2 - 0.5, 0, 1)`
or similar curve that preserves gradients.

## Verification

```bash
python -m pytest tests/test_material_mapper.py tests/test_material_mapper_detailed.py -v
```

## References

- Unity built-in shader classIDs: https://docs.unity3d.com/Manual/ClassIDReference.html
- `docs/FRAGILITY_AUDIT.md` — P2b section
