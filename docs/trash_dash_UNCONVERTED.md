# Trash Dash — Material Conversion Analysis & Unconverted Features Report

> Generated: 2026-03-01
> Converter Version: 0.1.0 (pre-release, analysis only)
> Unity Project: Trash Dash (Endless Runner Sample Game)
> Unity Version: 2021.3+ (URP 12.1.7)
> Unity Pipeline: **MIXED** — Custom unlit shaders + Built-in Standard + URP Unlit + Legacy Diffuse + Particle shaders

---

## Conversion Statistics

| Metric | Value |
|--------|-------|
| Total materials analyzed | 72 |
| Fully convertible (automated) | 12 |
| Partially convertible (texture OK, effects lost) | 49 |
| Not convertible (need manual rework) | 7 |
| Conversion-irrelevant (empty FBX defaults) | 4 |
| Unique shaders found | 13 |
| Custom project shaders | 6 |
| Textures referenced (_MainTex) | ~52 |
| Materials using non-white _Color tint | 3 |
| Materials using vertex colors | ~43 |
| Materials with alpha blending | ~14 |
| Materials with PBR maps (normal, metallic, AO) | **0** |

---

## Game-Specific Context

Trash Dash is a **stylized mobile endless runner**. Its art style is flat-shaded/toon with
no PBR texturing at all — no normal maps, no metallic maps, no occlusion maps, no emission
maps. Materials are simple: one albedo texture, optionally tinted, with vertex colors for
variation. The game uses custom unlit shaders that apply a **world-space curve** effect
(bending the ground away from the camera for the endless-runner perspective).

This means the PBR mapping portion of our research (metallic, roughness, normal maps,
emission) is NOT tested by this game. Trash Dash primarily tests:
- Albedo texture extraction
- Custom shader identification and fallback behavior
- Vertex color handling
- Alpha/transparency detection
- Unlit vs lit rendering mode
- Particle material conversion

---

## Shader Inventory

### 1. `Unlit/CurvedUnlit` — 27 materials (37.5%)

**GUID**: `93d8fc18fdc65dd4aa903210d93f3343`
**Source**: `Assets/Shaders/CurvedUnlit.shader` + `CurvedCode.cginc`

**What it does**:
- Samples `_MainTex` and multiplies by **vertex color** (`i.color`)
- Applies a vertex-shader world curve: `o.vertex.y -= _CurveStrength * dist² * projSign`
- Opaque rendering, fog support

**Materials using it**: Bin, BinBag, BinNight, BrickWall, Car01, Car02, Clover,
CorrugatedMetal, Dog, DogNight, Dumpster, Heart, Magnet, ManHole, Obstacle, Pipe,
Plaster, Rat, RatNight, Rubbish, Skip, StarInner, Stone, StoneWall, VCOL, WheelyBin,
WoodSlats

**Conversion status**: PARTIALLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_MainTex` | YES | `SurfaceAppearance.ColorMap` | Direct texture copy |
| `_Color` (stored but NOT read by shader) | SKIP | — | Ghost property; shader doesn't use it |
| Vertex color multiply | **NO** | — | See [Vertex Colors](#vertex-colors) |
| `_CurveStrength` (world curve) | **NO** | — | See [World Curve Effect](#world-curve-effect) |
| Unlit rendering | PARTIAL | — | See [Unlit Materials](#unlit-materials-vs-roblox-lighting) |

### 2. `Unlit/CurvedUnlitAlpha` — 14 materials (19.4%)

**GUID**: `e678ec0f80695014392e78a0142dfd2f`
**Source**: `Assets/Shaders/CurvedUnlitAlpha.shader`

**What it does**: Same as CurvedUnlit but with `Blend SrcAlpha OneMinusSrcAlpha`, `ZWrite Off`.

**Materials using it**: BlobShadow, Graffiti, LightCone, LightGlow, LightPool,
MagnetSparks, PickupParticle, PuffParticle, Sparkle, StarOuter, StarParticle,
TreeBranch, WarningLight, WashingLineClothes

**Conversion status**: PARTIALLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_MainTex` | YES | `SurfaceAppearance.ColorMap` | With alpha channel |
| Alpha blending | YES | `SurfaceAppearance.AlphaMode = Transparency` | Direct mapping |
| Vertex color multiply | **NO** | — | |
| `_CurveStrength` | **NO** | — | |

### 3. Built-in `Standard` — 12 materials (16.7%)

**fileID**: 46 (Built-in Standard shader)

**Materials using it**: lambert1 (×2), DogDiffuse, CatAlbedo, EndlessRunnerSourceImages...,
WheelyBinAlbedo, pasted__VCOL3, Default_Material, RatDiffuse, DumpsterAlbedo,
ParthatAndBowtie, lambert2

**Conversion status**: FULLY CONVERTIBLE (but trivially empty)

These are all FBX-imported default materials with NO textures, default metallic (0),
default glossiness (0.5), white color. They are placeholders from the 3D modeling
software (Maya `lambert1`, etc.) and are overridden by the game's actual materials at
runtime via `MeshRenderer.materials`.

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_Mode` = 0 (Opaque) | YES | `AlphaMode = Opaque` | |
| `_Metallic` = 0 | YES | Uniform MetalnessMap (black 4×4) | |
| `_Glossiness` = 0.5 | YES | Uniform RoughnessMap (0.5 gray 4×4) | |
| No textures | — | `BasePart.Color3 = (1,1,1)` | Default appearance |

### 4. `Unlit/UnlitBlinking` — 4 materials (5.6%)

**GUID**: `b9ac761e73263dc46b8b27826e86ee14`
**Source**: `Assets/Shaders/UnlitBlinking.shader`

**What it does**: Samples `_MainTex`, then `lerp(col, float4(1,1,0.75,1), _BlinkingValue)`.
`_BlinkingValue` is set at runtime via script to create a blinking/pulsing glow.

**Materials using it**: CatOrange, ConstructionGear, PartyHatAndBowtie, Racoon

**Conversion status**: PARTIALLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_MainTex` | YES | `SurfaceAppearance.ColorMap` | Direct copy |
| `_BlinkingValue` (runtime animation) | **NO** | — | See [Blinking Animation](#blinking-animation) |

### 5. URP `Universal Render Pipeline/Unlit` — 3 materials (4.2%)

**GUID**: `650dd9526735d5b46b79224bc6e94025` (from URP package, not in Assets/)

**Materials using it**: Shield, ControlRig, StarGlow

**Conversion status**: FULLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_BaseMap` / `_MainTex` | YES | `SurfaceAppearance.ColorMap` | StarGlow has texture |
| `_BaseColor` / `_Color` | YES | `SurfaceAppearance.Color` | ControlRig: (0.5,0.5,0.5) |

### 6. Legacy `Diffuse` — 3 materials (4.2%)

**fileID**: 10720 (Built-in `Legacy Shaders/Diffuse`)

**Materials using it**: DefaultParticleReplacementMaterial, MultiplierGlowParticle,
MultiplierParticle

**Conversion status**: FULLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_MainTex` | YES | `SurfaceAppearance.ColorMap` | Built-in texture for DefaultParticle |
| `_Color` | YES | `SurfaceAppearance.Color` | Default white |

### 7. `Unlit/VertexColor` — 2 materials (2.8%)

**GUID**: `d63f5eb2904b2b346afd16ebb961ff06`
**Source**: `Assets/Shaders/VertexColor.shader`

**What it does**: Renders ONLY vertex colors. No textures, no properties.
`col = i.color` — that's the entire fragment shader.

**Materials using it**: Sky, BackgroundCircle

**Conversion status**: NOT CONVERTIBLE (as standard material)

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| Vertex colors (only input) | **NO** | — | See [Vertex Colors](#vertex-colors) |
| Sky: `_SkyTint`, `_GroundColor`, etc. | GHOST | — | Stored but not read by shader |

**Special handling needed**: Sky → Roblox `Skybox` + `Atmosphere` objects.
BackgroundCircle → likely a visual effect part; needs manual color assignment.

### 8. `Unlit/CurvedRotation` — 2 materials (2.8%)

**GUID**: `0999d58022e15764c9c7f1db616452d4`
**Source**: `Assets/Shaders/CurvedRotation.shader`

**What it does**: Same as CurvedUnlit but also rotates the mesh vertices around Y using `_Time`.

**Materials using it**: Fishbone, Sardines

**Conversion status**: PARTIALLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_MainTex` | YES | `SurfaceAppearance.ColorMap` | |
| Vertex rotation animation | **NO** | — | See [Runtime Animation](#runtime-vertex-animation) |
| Vertex colors | **NO** | — | |

### 9. `Unlit/CurvedUnlitCloud` — 1 material (1.4%)

**GUID**: `61242e7b68c333746862afde9cdaf181`
**Source**: `Assets/Shaders/CurvedUnlitCloud.shader`

**Material**: CloudMaterial

**What it does**: Same as CurvedUnlit but renders before geometry (`Queue = Geometry-1`),
`ZWrite Off`. Creates a cloud background layer.

**Conversion status**: PARTIALLY CONVERTIBLE — texture can be extracted, but render
order and ZWrite behavior can't be mapped.

### 10. Particle Shaders — 4 materials (5.6%)

| Shader | fileID | Material | Blend Mode |
|--------|--------|----------|------------|
| Particles/Alpha Blended | 10751 | ExtraLifeParticle | SrcAlpha / OneMinusSrcAlpha |
| Particles/Alpha Blended Premultiply | 10752 | Grass, Construction | Premultiplied Alpha |
| Particles/Additive | 10753 | SmokePuff | Additive |
| Unknown (200) | 200 | FishBoneParticle | Unknown |

**Conversion status**: PARTIALLY CONVERTIBLE

| Property | Convertible | Roblox Target | Notes |
|----------|-------------|---------------|-------|
| `_MainTex` | YES | `ParticleEmitter.Texture` | If used as particle |
| `_TintColor` | YES | `ParticleEmitter.Color` | ExtraLifeParticle, PickupParticle |
| `_InvFade` (soft particles) | **NO** | — | No Roblox equivalent |
| Additive blending | PARTIAL | `ParticleEmitter.LightEmission = 1` | Approximation only |
| Premultiplied alpha | **NO** | — | No Roblox premultiply |

---

## Unconverted Features Detail

### Vertex Colors

**Affected materials**: ~43 (all CurvedUnlit, CurvedUnlitAlpha, CurvedRotation, VertexColor)
**Severity**: **HIGH**
**Impact**: Vertex colors in Trash Dash are used to add color variation to environment
objects — different bricks have different tints, trash items have color variation. Losing
vertex colors makes the environment look flat and monotone.

**Why it can't be converted**: Roblox `MeshPart` + `SurfaceAppearance` does not read
vertex colors from the mesh. There is no property to enable vertex color multiplication.

**Workarounds**:
1. **Bake vertex colors into the albedo texture** — Requires UV access AND the actual
   mesh data. For each face, sample the vertex color at each UV coordinate and multiply
   it into the albedo texture. This is computationally expensive and requires the FBX
   mesh data.
   - Estimated effort: 2-4 hours per unique mesh (manual in Blender/Substance)
   - Automatable: YES in future (requires FBX parsing + UV mapping + texture baking)

2. **Create multiple tinted copies** — For objects that use vertex color as a flat tint
   (e.g., entire mesh is one color), create `SurfaceAppearance.Color` variants.
   - Estimated effort: 30 minutes (if vertex colors are per-object, not per-vertex)
   - Automatable: PARTIAL

3. **Accept the visual difference** — Many objects will still look recognizable without
   vertex color variation, just less detailed.
   - Estimated effort: 0

**Future automation**: Phase 2 — FBX parser extracts vertex colors, UV-maps them to
texture space, and bakes a multiplied albedo texture.

### World Curve Effect

**Affected materials**: ~44 (all Curved* shaders)
**Severity**: **LOW**
**Impact**: The endless-runner "world curving away" is a purely cosmetic viewport effect.
The game is fully playable without it. Objects will appear on a flat plane instead.

**Why it can't be converted**: This is a vertex shader effect that modifies clip-space
positions based on distance. Roblox has no custom vertex shaders.

**Workarounds**:
1. **Ignore entirely** — The game works fine on flat ground. This is the recommended approach.
2. **Approximate with camera tilt** — A slight downward camera angle can hint at curvature.
   - Estimated effort: 5 minutes (camera setup in Roblox Studio)

**Future automation**: Not planned. This is an aesthetic choice, not a material property.

### Unlit Materials vs Roblox Lighting

**Affected materials**: ~60 (all custom shaders are unlit)
**Severity**: **MEDIUM**
**Impact**: Trash Dash was designed as an unlit game — textures encode all lighting/shading
already (pre-baked style). In Roblox, `SurfaceAppearance` on a `MeshPart` will still receive
Roblox scene lighting (sun, ambient, point lights), causing double-lighting: the pre-baked
shadows in the textures PLUS Roblox's realtime shadows.

**Why it can't be converted**: Roblox does not have an "unlit" `SurfaceAppearance` mode.
`BasePart.Material = Enum.Material.Neon` makes a part self-lit but has a strong glow effect
that doesn't match the original style.

**Workarounds**:
1. **Use `SmoothPlastic` material with bright ambient** — Set environment lighting to
   high ambient, reduce directional light. Objects will look less shadowed.
   - Estimated effort: 15 minutes
   - Automatable: YES (set lighting properties in .rbxl output)

2. **Use `Neon` material** — Creates self-illuminated parts but with glow. May work for
   some pickup/effect materials but looks wrong for environment objects.

3. **Accept double-lighting** — For many objects the visual difference is subtle since the
   textures are stylized and don't have strong baked shadows.

**Future automation**: Phase 1 — Set Roblox `Lighting.Ambient` high and `Lighting.Brightness`
low in the generated .rbxl to approximate an unlit environment.

### Blinking Animation

**Affected materials**: 4 (UnlitBlinking shader)
**Severity**: **LOW**
**Impact**: Collectible items (cat, raccoon, party hat, construction gear) won't pulse/blink.

**Why it can't be converted**: `_BlinkingValue` is a runtime float set by C# scripts via
`Material.SetFloat()`. Roblox `SurfaceAppearance` properties cannot be scripted at runtime.

**Workarounds**:
1. **Luau script with Color3 tweening** — A Luau script can tween `BasePart.Color` to
   simulate the blink effect. The lerp target `(1, 1, 0.75)` maps to a warm white.
   ```lua
   local TweenService = game:GetService("TweenService")
   local part = script.Parent
   local tween = TweenService:Create(part, TweenInfo.new(0.5, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true), {Color = Color3.new(1, 1, 0.75)})
   tween:Play()
   ```
   - Estimated effort: 15 minutes
   - Automatable: YES (generate Luau script when UnlitBlinking shader detected)

**Future automation**: Phase 1 — Detect `UnlitBlinking` shader, generate companion Luau
tween script automatically.

### Runtime Vertex Animation

**Affected materials**: 2 (CurvedRotation shader — Fishbone, Sardines)
**Severity**: **LOW**
**Impact**: Collectible items won't spin.

**Why it can't be converted**: Vertex rotation is a shader effect. Roblox has no custom
vertex shaders.

**Workarounds**:
1. **Luau script with CFrame rotation** — Rotate the MeshPart via script instead.
   ```lua
   game:GetService("RunService").Heartbeat:Connect(function(dt)
       script.Parent.CFrame = script.Parent.CFrame * CFrame.Angles(0, math.pi * dt, 0)
   end)
   ```
   - Estimated effort: 5 minutes
   - Automatable: YES (detect CurvedRotation shader, generate rotation script)

**Future automation**: Phase 1 — Detect `CurvedRotation` shader, generate rotation script.

### Particle Additive/Premultiplied Blending

**Affected materials**: 3 (SmokePuff additive, Grass/Construction premultiplied)
**Severity**: **LOW**
**Impact**: Particle visual effects will look slightly different.

**Workarounds**:
- Additive → Roblox `ParticleEmitter.LightEmission = 1` (close approximation)
- Premultiplied → No direct equivalent; use standard alpha blending (close enough)

**Future automation**: Phase 1 — Map blend mode to `LightEmission` property.

### Soft Particles (`_InvFade`)

**Affected materials**: 3 (ExtraLifeParticle, PickupParticle, DefaultParticleReplacementMaterial)
**Severity**: **LOW**
**Impact**: Particle edges will have hard intersections with geometry instead of soft fading.

**Why it can't be converted**: Roblox particles don't support depth-based soft edge fading.

**Workaround**: Accept visual difference. Not noticeable in fast gameplay.

### Ghost Properties (Non-Issue)

**Affected materials**: ~40
**Severity**: NONE (informational)

Many materials store Standard shader properties (`_Metallic`, `_Glossiness`, `_BumpScale`,
`_EmissionColor`, etc.) that are **NOT read by their actual shader**. For example:
- `Dog.mat` has `_Color: {r: 0.4, g: 0.4, b: 0.4}` — but uses `CurvedUnlit` which
  doesn't read `_Color` at all (it only reads `_MainTex` and vertex color)
- `LightGlow.mat` has `_Color: {r: 0.588, g: 0.588, b: 0.588}` — but uses
  `CurvedUnlitAlpha` which doesn't read `_Color`

**Converter action**: The converter MUST check which shader is actually assigned and only
convert properties that the shader reads. Blindly converting `_Color` for CurvedUnlit
materials would produce incorrect results (applying a tint that doesn't exist in the
original game).

This is a **critical correctness insight** discovered during this analysis.

### Sky Material

**Affected materials**: 1 (Sky.mat)
**Severity**: **MEDIUM**

Sky.mat uses `VertexColor` shader but has ghost Skybox/Procedural properties:
- `_SkyTint: (0.949, 0.949, 0.949)`
- `_GroundColor: (0.956, 0.816, 0.689)`
- `_AtmosphereThickness: 0.6`
- `_Exposure: 1.71`
- `_SunDisk: 0` (none)

**Workaround**: Map to Roblox `Skybox` + `Atmosphere` objects using the stored color values.
Since these are ghost properties, they may not match what the game actually renders.
Manual verification needed.

**Future automation**: Phase 2 — Detect Skybox-like properties, generate Roblox
Skybox/Atmosphere configuration.

---

## Specific _Color Tint Analysis

Only 3 materials in the entire game have non-white `_Color`:

| Material | _Color | Shader | Shader reads _Color? | Action |
|----------|--------|--------|---------------------|--------|
| Dog | `(0.4, 0.4, 0.4, 1)` | CurvedUnlit | **NO** | SKIP (ghost property) |
| LightGlow | `(0.588, 0.588, 0.588, 1)` | CurvedUnlitAlpha | **NO** | SKIP (ghost property) |
| ControlRig | `(0.5, 0.5, 0.5, 1)` | URP Unlit | **YES** (as `_BaseColor`) | `SurfaceAppearance.Color = (0.5, 0.5, 0.5)` |

**Conclusion for Trash Dash**: The `_Color` question from our research is largely moot
for this game. Only 1 material (ControlRig) actually uses color tinting, and it's a
control rig visualization that wouldn't appear in the game. The converter's shader-aware
property extraction correctly avoids false positives.

---

## Overall Conversion Verdict

### What Works Well

1. **Albedo texture extraction** — 52 materials reference `_MainTex` textures via GUID.
   All can be resolved and copied as `SurfaceAppearance.ColorMap`.

2. **Transparency detection** — The 14 `CurvedUnlitAlpha` materials can be correctly
   identified as transparent by checking the actual shader source (not `_Mode`, which
   is 0 for all materials). This means the converter needs shader-level transparency
   detection, not just `_Mode` float checking.

3. **No PBR complexity** — Zero materials use normal maps, metallic maps, occlusion maps,
   or emission maps. No channel extraction or smoothness-to-roughness conversion needed.

4. **No tiling issues** — All materials use `Scale: {x: 1, y: 1}`, `Offset: {x: 0, y: 0}`.
   No pre-tiling workarounds needed.

### What Doesn't Work

1. **Vertex colors (HIGH impact)** — The single biggest fidelity loss. 43 materials
   multiply textures by vertex colors for variation. Requires mesh-level baking to fix.

2. **Custom shader identification (MEDIUM)** — 6 custom shaders need to be recognized
   and their properties correctly mapped. The converter can't rely on Standard shader
   property names alone.

3. **Unlit rendering (MEDIUM)** — The entire game is designed unlit. Roblox will add
   realtime lighting on top, causing visual mismatch.

4. **Runtime animations (LOW)** — Blinking and rotation effects need Luau script generation.

### Converter Enhancements Needed (Discovered)

| Enhancement | Priority | Reason |
|-------------|----------|--------|
| Shader-aware property extraction | **P0** | Ghost properties cause false conversions |
| Custom shader source parsing | **P1** | 60% of materials use custom shaders |
| Transparency from shader source (not `_Mode`) | **P1** | `_Mode=0` but shader has alpha blend |
| Vertex color baking pipeline | **P2** | Biggest visual fidelity improvement |
| Companion Luau script generation | **P2** | Blinking, rotation effects |
| Unlit environment lighting preset | **P2** | Reduce double-lighting issue |

---

## Per-Material Quick Reference

### Fully Convertible (12)

| Material | Shader | Textures | Notes |
|----------|--------|----------|-------|
| lambert1 (Anim) | Standard | None | FBX default, skip |
| DogDiffuse | Standard | None | FBX default, skip |
| CatAlbedo | Standard | None | FBX default, skip |
| EndlessRunner...BinAlbedo | Standard | None | FBX default, skip |
| WheelyBinAlbedo | Standard | None | FBX default, skip |
| pasted__VCOL3 | Standard | None | FBX default, skip |
| Default_Material | Standard | None | FBX default, skip |
| RatDiffuse | Standard | None | FBX default, skip |
| DumpsterAlbedo | Standard | None | FBX default, skip |
| ParthatAndBowtie | Standard | None | FBX default, skip |
| lambert1 (Models) | Standard | None | FBX default, skip |
| lambert2 | Standard | None | FBX default, skip |

### Partially Convertible — Texture OK (49)

Texture → ColorMap works. Vertex colors, curve effect, and unlit rendering are lost.

**CurvedUnlit (27)**: Bin, BinBag, BinNight, BrickWall, Car01, Car02, Clover,
CorrugatedMetal, Dog, DogNight, Dumpster, Heart, Magnet, ManHole, Obstacle, Pipe,
Plaster, Rat, RatNight, Rubbish, Skip, StarInner, Stone, StoneWall, VCOL,
WheelyBin, WoodSlats

**CurvedUnlitAlpha (14)**: BlobShadow, Graffiti, LightCone, LightGlow, LightPool,
MagnetSparks, PickupParticle, PuffParticle, Sparkle, StarOuter, StarParticle,
TreeBranch, WarningLight, WashingLineClothes

**UnlitBlinking (4)**: CatOrange, ConstructionGear, PartyHatAndBowtie, Racoon

**CurvedRotation (2)**: Fishbone, Sardines

**CurvedUnlitCloud (1)**: CloudMaterial

**URP Unlit (1)**: StarGlow (has texture)

### Not Directly Convertible (7)

| Material | Shader | Issue | Manual Action |
|----------|--------|-------|---------------|
| Sky | VertexColor | Vertex-color-only sky; ghost Skybox props | Create Roblox Skybox + Atmosphere |
| BackgroundCircle | VertexColor | Vertex-color-only background | Assign flat color manually |
| Shield | URP Unlit | No texture, no color tint | Assign flat color |
| ControlRig | URP Unlit | Control rig visualization | Skip (not gameplay-visible) |
| ExtraLifeParticle | Particles/Alpha Blended | Particle material | Map to ParticleEmitter |
| SmokePuff | Particles/Additive | Additive particle | Map to ParticleEmitter with LightEmission |
| FishBoneParticle | Built-in (200) | Unknown shader | Investigate |

### Particle Materials (Map to ParticleEmitter, not SurfaceAppearance)

| Material | Shader | _TintColor | _MainTex |
|----------|--------|------------|----------|
| ExtraLifeParticle | Particles/Alpha Blended | (0.5, 0.5, 0.5, 0.5) | Yes |
| Construction | Particles/Premultiply | — | Yes |
| Grass | Particles/Premultiply | — | Yes |
| SmokePuff | Particles/Additive | — | Yes |
| DefaultParticleReplacement | Legacy Diffuse | (0.5, 0.5, 0.5, 0.5) | Built-in |
| MultiplierParticle | Legacy Diffuse | — | Yes |
| MultiplierGlowParticle | Legacy Diffuse | — | Built-in |
| PickupParticle | CurvedUnlitAlpha | (1, 1, 1, 0.5) | Yes |
| FishBoneParticle | Built-in (200) | — | Yes |

---

## Future Automation Roadmap (Informed by Trash Dash)

### Phase 1 — Immediate (This converter release)
1. Shader-aware property extraction (check shader source, not just stored properties)
2. Custom shader → Standard property fallback (extract `_MainTex`, detect alpha from shader tags)
3. Transparency detection from shader `Blend` directives
4. Generate lighting presets for unlit games

### Phase 2 — Next release
5. Vertex color baking pipeline (FBX parse → UV map → texture multiply)
6. Companion Luau script generation for runtime effects (blink, rotate)
7. Particle material → ParticleEmitter property mapping
8. Skybox/Atmosphere generation from sky material properties

### Phase 3 — Long term
9. Custom Shader Graph analysis
10. Multi-material mesh splitting
11. Terrain material conversion
