# Trash Dash End-to-End Gap Analysis

> Date: 2026-03-02
> Scope: Full pipeline analysis of converter vs Trash Dash game requirements
> Previous analysis: `docs/trash_dash_UNCONVERTED.md` covers material/shader gaps only
> This document covers ALL other converter gaps discovered by tracing the full game

---

## Executive Summary

The existing `trash_dash_UNCONVERTED.md` thoroughly covers material/shader conversion
gaps (72 materials, 13 shaders, vertex colors, custom shaders). This analysis covers
**everything else** — the structural, gameplay, and data conversion gaps that would
prevent Trash Dash from being a functional Roblox game.

**Two critical bugs were found** that affect ALL Unity projects, not just Trash Dash:
1. **Rotation is completely dropped** — no CFrame/Orientation is written to .rbxl
2. **Scale is never applied from Unity** — hardcoded default size on all parts

Beyond these bugs, **9 converter gaps** were identified that are specific to game
systems Trash Dash uses but the converter doesn't handle.

---

## Critical Bugs (Affect ALL Unity Projects)

### BUG-1: Rotation Not Written to .rbxl

**Severity: CRITICAL**

The scene parser correctly extracts quaternion rotation from every Transform:
```python
# scene_parser.py line 93
rotation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)  # quaternion
```

But `RbxPartEntry` has **no rotation field at all** (rbxl_writer.py:48-60), and
`_make_part()` only writes Position and Size — no CFrame, no Orientation.

**Impact on Trash Dash**: Every rotated track segment, obstacle, building, and
decoration will appear at default orientation. The entire game world will look
broken — walls will be flat on the ground, angled obstacles will be axis-aligned,
the track won't curve properly.

**Impact on all games**: Any scene with rotated objects (i.e., essentially every
Unity scene) will have incorrect orientations.

**Fix**: Add a `rotation` field to `RbxPartEntry`, convert quaternion → CFrame
in `_make_part()`, and write a proper CFrame property to the XML.

### BUG-2: Scale Not Applied from Unity

**Severity: CRITICAL**

The scene parser correctly extracts scale:
```python
# scene_parser.py line 94
scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
```

But `_node_to_part()` in converter.py (line 91) sets a hardcoded default:
```python
size=(4.0, 1.0, 4.0),
```

Unity scale is never used to compute the Part size. Only collider sizes
(BoxCollider.m_Size, etc.) override this default.

**Impact on Trash Dash**: All objects without colliders will appear as 4×1×4
blocks. Characters, decorations, coins, track props — all wrong size.

**Impact on all games**: Every non-collider object will have wrong dimensions.

**Fix**: In `_node_to_part()`, multiply the base mesh bounding box (or a
reasonable default like 1×1×1) by `node.scale` to produce the Part size.

---

## Converter Gaps Specific to Trash Dash

### GAP-1: No Animation System Conversion

**Severity: HIGH**
**Trash Dash usage**: Character run/jump/slide/stumble/death animations,
UI transitions, coin spin animations

**What exists**: `api_mappings.py` has stub comments for Animator/Animation:
```python
"Animator.SetBool": "-- Animator: use Roblox AnimationController",
"Animator.Play": "-- Animator: use AnimationTrack:Play()",
```

**What's missing**:
- No Animator Controller parsing (classID 91 — state machine, transitions, blend trees)
- No AnimationClip extraction (classID 74 — keyframe data)
- No conversion to Roblox AnimationController + AnimationTrack
- No Humanoid rig retargeting (Unity Humanoid → Roblox R15/R6)
- `.anim` files are discovered by asset_extractor but never processed

**Impact**: Characters will be static T-poses. No run cycle, no jump, no
slide animation. The game loses all character animation.

**Workaround**: Manual re-animation in Roblox Studio using the Animation Editor.
Alternatively, export animations as FBX and import into Roblox.

### GAP-2: No ParticleSystem Component Conversion

**Severity: MEDIUM**
**Trash Dash usage**: Coin pickup sparkles, magnet sparks, smoke puffs,
star effects, extra life particles

**What exists**: `trash_dash_UNCONVERTED.md` covers particle **materials** (textures,
blend modes), but not the ParticleSystem **component** itself.

**What's missing**:
- ParticleSystem (classID 198) is not in scene_parser's classID list
- No extraction of: emission rate, lifetime, start speed, start size, shape
  module, color/size over lifetime, gravity modifier
- No conversion to Roblox ParticleEmitter properties (Rate, Lifetime, Speed,
  SpreadAngle, Color, Size, Texture, etc.)

**Impact**: No particle effects at all — no sparkles, no smoke, no glow effects.

### GAP-3: No Audio/Sound Conversion

**Severity: MEDIUM**
**Trash Dash usage**: Background music, coin collect SFX, crash SFX,
power-up activation sounds, UI button clicks

**What exists**: `asset_extractor.py` discovers .wav/.mp3/.ogg files.
`api_mappings.py` maps AudioSource API calls:
```python
"AudioSource.Play": ":Play()",
"AudioSource.volume": ".Volume",
"AudioSource.loop": ".Looped",
```

**What's missing**:
- AudioSource component (classID 82) not parsed from scenes
- No extraction of: clip reference, volume, pitch, spatial blend,
  loop, play-on-awake, rolloff settings
- No conversion to Roblox Sound objects (SoundId, Volume, Looped, RollOffMode)
- Audio files are discovered but not uploaded or embedded in .rbxl
- No AudioListener → no equivalent (Roblox auto-listens from camera)

**Impact**: Completely silent game — no music, no SFX.

### GAP-4: No Light Component Conversion

**Severity: MEDIUM**
**Trash Dash usage**: The game is mostly unlit (custom shaders), but has
LightCone, LightPool, LightGlow materials and likely some Point/Spot lights
for night-mode track segments.

**What's missing**:
- Light (classID 108) not parsed from scenes
- No extraction of: type (Directional/Point/Spot), color, intensity,
  range, spot angle, shadow settings
- No conversion to Roblox PointLight/SpotLight/SurfaceLight
- No Lighting service setup (Ambient, Brightness, ClockTime, etc.)

**Impact**: Scene will use Roblox default lighting. Night-mode track
segments will look wrong.

### GAP-5: No CharacterController Handling

**Severity: MEDIUM**
**Trash Dash usage**: The player character uses Unity's CharacterController
(classID 143) — NOT Rigidbody — for lane-based movement with ground detection.

**What's missing**:
- CharacterController is not a recognized classID in scene_parser
- No concept of Roblox Humanoid (the closest equivalent)
- CharacterInputController.cs uses touch/swipe input, which the transpiler
  will partially handle via UserInputService mappings, but the architectural
  pattern (lanes, grounded checks, gravity) won't map correctly

**Impact**: The character movement system won't work. Lane switching,
jumping, sliding, and ground detection all depend on CharacterController.

### GAP-6: No ScriptableObject / .asset Data Conversion

**Severity: MEDIUM**
**Trash Dash usage**: ConsumableDatabase (power-up definitions), ThemeData
(visual themes with track piece prefab references), MissionBase (achievement
definitions). These are `.asset` files containing serialized ScriptableObject data.

**What's missing**:
- `.asset` files are not in `config.SUPPORTED_ASSET_EXTENSIONS`
- No parsing of ScriptableObject data files
- No conversion to Roblox ModuleScript data tables

**Impact**: All data-driven systems (power-ups, themes, missions) lose their
configuration. Scripts that reference `[SerializeField]` ScriptableObject
fields will have no data to read.

### GAP-7: Object Pooling Pattern Breaks

**Severity: LOW**
**Trash Dash usage**: TrackManager and Coin.cs use Pooler.cs — objects are
deactivated/reactivated via SetActive() instead of Instantiate/Destroy.

**What the transpiler does**:
- `gameObject.SetActive` → `.Parent` (reparent to enable/disable)
- `Instantiate` → `.Clone`

**What actually breaks**:
- The pooling pattern relies on maintaining a collection of deactivated
  objects and cycling through them. The transpiled code will have the
  right API calls but the structural pattern (pool initialization,
  index tracking, capacity management) needs manual refactoring
- Roblox has no `SetActive(false)` — parts must be moved to `nil` parent
  (which also disconnects scripts) or to a storage container

**Impact**: Track generation loop will malfunction. Coins won't recycle
properly. The game's core loop depends on this pattern.

### GAP-8: Floating Origin / Origin Reset

**Severity: LOW (Trash Dash-specific)**
**Trash Dash usage**: TrackManager periodically resets world origin by shifting
all objects back by a threshold distance to maintain floating-point precision
for the endless runner.

**What breaks**: The transpiled code will attempt to shift all Parts by
CFrame offsets, but:
- Roblox uses double-precision coordinates (much larger range than Unity's
  floats), so origin reset may not be needed at all
- If StreamingEnabled is used, Roblox handles large worlds natively
- The C# code that iterates `FindObjectsOfType<Transform>()` won't have
  a clean Roblox equivalent

**Impact**: Minor — Roblox's coordinate system can handle much larger
distances than Unity, so this may be unnecessary.

### GAP-9: Additive Scene Loading / State Machine Architecture

**Severity: LOW**
**Trash Dash usage**: The shop is loaded as an additive scene. The game uses
a state machine (GameManager pushes/pops GameState, GameOverState, LoadoutState).

**What breaks**:
- `SceneManager.LoadScene` → `-- LoadScene: use TeleportService` (comment only)
- Additive scene loading has no Roblox equivalent
- The state machine pattern will transpile syntactically but the concept of
  managing multiple UI screens via scene loading doesn't map

**Impact**: The menu/shop/game-over flow won't work. Would need manual
redesign using ScreenGui visibility toggling in Roblox.

---

## Not Gaps (Explicitly Unsupported — Already Documented)

These are in `trash_dash_UNCONVERTED.md` and are known limitations:

| Feature | Status | Reference |
|---------|--------|-----------|
| Vertex colors | Known unsupported | UNCONVERTED.md §Vertex Colors |
| Custom shader effects (curve, blink, rotate) | Known unsupported | UNCONVERTED.md §World Curve, §Blinking |
| Unlit rendering mode | Known unsupported | UNCONVERTED.md §Unlit Materials |
| Particle blend modes (additive, premul) | Known unsupported | UNCONVERTED.md §Particle Blending |
| Ghost properties (shader-unread values) | Known handled | UNCONVERTED.md §Ghost Properties |
| Soft particles (_InvFade) | Known unsupported | UNCONVERTED.md §Soft Particles |

---

## Also Not Gaps (Third-Party Services — Out of Scope)

| Feature | Reason |
|---------|--------|
| Unity IAP integration | Roblox uses MarketplaceService — different business model |
| Unity Ads integration | No Roblox equivalent — different monetization model |
| Unity Analytics | Roblox has its own analytics |
| Addressable Asset System | Roblox pre-loads all assets — no dynamic loading needed |
| Unity Cloud Save | Would need DataStoreService — different API entirely |

---

## Resolution Summary

### Fixed (Implemented)

| Issue | Resolution |
|-------|------------|
| **BUG-1: Rotation not written** | Added quaternion→CFrame conversion in rbxl_writer.py; RbxPartEntry now carries rotation |
| **BUG-2: Scale not applied** | _node_to_part() now uses node.scale instead of hardcoded (4,1,4) |
| **GAP-2: ParticleSystem** | Added classID 198 parsing in scene_parser; converts startLifetime→Lifetime, startSpeed→Speed, startSize→Size, startColor→Color, emissionRate→Rate to Roblox ParticleEmitter child objects |
| **GAP-3: Audio/Sound** | Added classID 82 parsing; extracts volume, pitch, loop, spatial blend, min/max distance → Roblox Sound child objects (audio files need manual upload) |
| **GAP-4: Lights** | Added classID 108 parsing; Point→PointLight, Spot→SpotLight with color, intensity, range, shadows, angle |
| **GAP-6: ScriptableObject data** | New `scriptable_object_converter.py` parses .asset YAML → Luau data tables as ModuleScripts in ReplicatedStorage |

### Unconvertible (Documented Limitations)

| Issue | Why | Recommended Manual Workaround |
|-------|-----|-------------------------------|
| **GAP-1: Animation system** | Unity Animator uses state machines, blend trees, and bone-mapped keyframe data. Roblox uses a completely different animation system (AnimationController + uploaded AnimationTrack assets). Rig retargeting between Unity Humanoid and Roblox R15/R6 requires bone-by-bone mapping that cannot be done generically. The .anim keyframe format and the AnimatorController state machine (.controller) have no Roblox equivalent file format. | Export character animations from Unity as FBX files. Import into Roblox Studio's Animation Editor. Re-map to R15 rig manually. For simple transform animations (rotation, position), consider generating Luau TweenService scripts. |
| **GAP-5: CharacterController** | Unity's CharacterController (classID 143) provides ground detection, slope limits, step offsets, and Move()/SimpleMove() — Roblox Humanoid works fundamentally differently (automatic walking, jumping, climbing). Trash Dash's lane-based movement with swipe input is game-specific logic, not a generic component conversion. | Rewrite character movement in Luau using Humanoid:MoveTo() or CFrame manipulation. Map swipe/touch input via UserInputService. Roblox Humanoid handles jumping and gravity automatically. |
| **GAP-7: Object pooling** | This is a design pattern (Pooler.cs), not a component. Individual API calls transpile correctly (SetActive→Parent, Instantiate→Clone), but the structural pattern — pre-allocating a pool, tracking active/inactive objects, cycling indices — needs architectural rethinking for Roblox. | In Roblox, use a similar pattern: store inactive parts in ServerStorage, reparent to Workspace when needed. The transpiled SetActive→Parent mapping is functionally correct but the pool management code needs manual review. |
| **GAP-8: Floating origin** | Roblox uses double-precision floating-point coordinates (much larger range than Unity's single-precision floats). Trash Dash's origin reset technique is unnecessary in Roblox — the engine can handle coordinates far beyond what an endless runner would reach. | Remove or comment out the origin reset code. If using Roblox's StreamingEnabled for very large worlds, the engine handles this automatically. |
| **GAP-9: Additive scenes / state machine** | Roblox has no concept of additive scene loading. Each Roblox Place is self-contained. The state machine pattern (GameManager pushing/popping GameState, GameOverState, LoadoutState) doesn't break syntactically, but the scene loading calls (SceneManager.LoadScene) have no functional equivalent. | Replace scene loading with ScreenGui visibility toggling: each "scene" becomes a ScreenGui that is shown/hidden. The state machine logic can remain; only the transition mechanism changes. For the shop (additive scene), use a ScreenGui overlay. |
