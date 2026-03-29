# Plan: Transform Animation + Particle Burst in Converter Pipeline

## Context

The converter handles Mecanim Animators (skeletal animation via `animation_converter.py`) and continuous ParticleSystem emission (via `convert_particle_components()`). But two common Unity patterns produce no output:

1. **Transform animations** -- .anim files that loop position/rotation/scale on non-skeletal objects (coin spin+bob, power-up icon rotation). These use Unity's Legacy Animation component (classID 111) or are script-driven. The converter doesn't recognize CID 111 at all.
2. **Burst particles** -- ParticleSystem components with `rateOverTime=0` and burst entries (pickup sparkles, death explosion). The converter treats all particles as continuous emitters.

The goal is to handle these generically in the pipeline (not game-specific), and update the skill so future conversions detect and convert them automatically.

## Implementation

### 1. Register CID 111 (Legacy Animation) -- `modules/unity_yaml_utils.py`

- Add `CID_LEGACY_ANIMATION = 111` after line 51
- Add to `KNOWN_COMPONENT_CIDS` set (~line 99)
- Add to `COMPONENT_CID_TO_NAME` dict (~line 144): `111: "Animation"`

### 2. Extend `parse_anim_file()` to extract keyframe data -- `modules/animation_converter.py`

Add new dataclasses:
```python
@dataclass
class AnimKeyframe:
    time: float
    value: tuple[float, ...]  # (x,y,z) for pos/euler/scale, (x,y,z,w) for quat

@dataclass
class TransformCurve:
    path: str  # "" = self, "Child/Name" = relative
    curve_type: str  # "position", "rotation", "euler", "scale"
    keyframes: list[AnimKeyframe]
```

Add `transform_curves: list[TransformCurve]` field to `AnimationClipInfo`.

In `parse_anim_file()`, after collecting bone_paths, also iterate `m_Curve` entries within each curve to extract `time` and `value` (dict with x,y,z keys). Store in `transform_curves`.

### 3. Add transform animation classification + config generation -- `modules/animation_converter.py`

New functions:
```python
def is_transform_only_anim(clip: AnimationClipInfo) -> bool:
    """True when all curves target self ("") or simple children, no humanoid bones."""

def generate_transform_anim_config(clip: AnimationClipInfo) -> str:
    """Generate a Luau config table from keyframe data."""

@dataclass
class TransformAnimationResult:
    config_modules: list[tuple[str, str]]  # (name, luau_source)
    bridge_needed: bool
    warnings: list[str]
    anims_found: int
    anims_converted: int

def convert_transform_animations(
    parsed_scenes, guid_index, project_root
) -> TransformAnimationResult:
    """Scan for Legacy Animation components, parse referenced .anim files,
    generate TransformAnimator configs for transform-only clips."""
```

Classification: animation is "transform-only" when all `path` values are `""` (self) or don't match any entry in `UNITY_TO_R15_BONE_MAP`.

Config output format (consumed by TransformAnimator.lua):
```lua
return {
    loop = true,
    duration = 2.0,
    curves = {
        position = { {time=0, value=Vector3.new(0,0.5,0)}, ... },
        euler = { {time=0, value=Vector3.new(0,0,33.458)}, ... },
    },
}
```

### 4. Create `bridge/TransformAnimator.lua`

New bridge module following AnimatorBridge pattern:
- `TransformAnimator.new(part, config)` -- stores base CFrame, parses config
- Shared `Heartbeat` connection batching all instances (same pattern as AnimatorBridge)
- Each frame: compute `elapsed % duration`, lerp between surrounding keyframes, compose CFrame
- `TransformAnimator:Destroy()` -- cleanup, restore base CFrame
- Linear interpolation for MVP (tangent/Hermite can be added later using slope data already in config)

### 5. Extend particle burst detection -- `modules/conversion_helpers.py`

In `convert_particle_components()` (~line 259), add:
- Read `looping` from root ParticleSystem props (0 = one-shot)
- Read `playOnAwake` (0 = triggered by script)
- Read burst data: `m_Bursts` list (new format) or `cnt0`-`cnt3` (old format)
- Classify: `is_burst = (rate < 0.01) and (burst_count > 0 or not looping)`
- Append 2 new fields to the tuple: `emission_mode` ("continuous"/"burst"), `burst_count`

Add `"Animation"` to `_CONVERTED_COMPONENTS` (line 38).
Add suggestion in `_COMPONENT_SUGGESTIONS`: `"Animation": "Auto-converted via TransformAnimator..."`.

### 6. Update particle XML writing -- `modules/rbxl_writer.py`

In `_make_particle_emitter()` (~line 408):
- Accept 2 additional params: `emission_mode`, `burst_count`
- When `emission_mode == "burst"`: set `Rate=0`, `Enabled=false`
- Add IntValue child `BurstCount` with the count (game scripts call `:Emit(count)`)
- Update call site (~line 580) to unpack 13-tuple

### 7. Wire into orchestrator -- `converter.py`

After the existing animation conversion block (~line 293), add:
```python
# Transform animation conversion (Legacy Animation → config + bridge)
transform_result = animation_converter.convert_transform_animations(
    parsed_scenes, guid_index, unity_path,
)
# Add config modules + TransformAnimator.lua bridge (same pattern as AnimatorBridge)
```

### 8. Update skill -- `.claude/skills/convert-unity/SKILL.md`

Add to Phase A architectural analysis (after item 4, ~line 100):

**5. Transform animation detection** -- Scan for Legacy Animation components (classID 111) and .anim files that drive simple transform loops (spin, bob, tilt) on non-skeletal objects. The converter auto-generates TransformAnimator configs; verify keyframe data.

**6. Particle emission classification** -- For each ParticleSystem, determine if continuous or burst-triggered. Burst particles (rateOverTime=0 with burst entries) are set to Enabled=false; game scripts must call `:Emit()` at the right moment.

Add to Phase B module table:
| Legacy Animation on non-skeletal objects | Auto-generated configs + `TransformAnimator.lua` | `TransformAnimator` |

### 9. Tests

Extend `tests/test_animation_converter.py`:
- Test keyframe extraction from real .anim (Fishbones.anim format)
- Test `is_transform_only_anim()` classification
- Test `generate_transform_anim_config()` output format
- Test `convert_transform_animations()` end-to-end

Extend `tests/test_conversion_helpers.py`:
- Test burst particle detection (rateOverTime=0, cnt0>0)
- Test continuous particle unchanged by new fields

## Critical files
- `modules/animation_converter.py` -- keyframe extraction + config generation
- `modules/unity_yaml_utils.py` -- CID 111 registration
- `modules/conversion_helpers.py` -- particle burst + Animation component tracking
- `modules/rbxl_writer.py` -- burst particle XML
- `bridge/TransformAnimator.lua` -- new runtime bridge
- `converter.py` -- orchestrator wiring
- `.claude/skills/convert-unity/SKILL.md` -- skill guidance

## Verification
1. Run `python -m pytest tests/test_animation_converter.py -v` -- new keyframe + config tests pass
2. Run `python -m pytest tests/test_conversion_helpers.py -v` -- burst particle tests pass
3. Run `python -m pytest tests/ -v` -- full suite passes, no regressions
4. Manual: run converter on Trash Dash, verify TransformAnimator configs generated for Fishbones.anim
