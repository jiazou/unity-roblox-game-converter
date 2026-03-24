# Game Logic Porting: Unity → Roblox

## Architecture

The converter handles game logic through two complementary systems:

### 1. Unity Bridge Layer (reusable Luau modules)

A set of Luau modules that implement common Unity patterns in Roblox. These live in `ReplicatedStorage/UnityBridge/` in the output .rbxl and are `require()`-ed by the ported game scripts.

The bridge is NOT a full Unity emulator. It provides the 20% of Unity APIs that cover 80% of game code — enough that an LLM rewrite can focus on game logic, not API translation.

**Modules:**

| Module | Unity Concept | Roblox Implementation |
|--------|--------------|----------------------|
| `MonoBehaviour` | Start/Update/OnDestroy lifecycle | Connect to RunService.Heartbeat, table of callbacks |
| `GameObject` | Instantiate, Destroy, Find, GetComponent | InsertService:LoadAsset, Instance.new, FindFirstChild |
| `Input` | GetKey, GetAxis, touch/swipe | UserInputService mapped to Unity key names |
| `Transform` | position, rotation, Translate, Rotate | CFrame wrappers |
| `Physics` | Raycast, CheckSphere, OnTriggerEnter | workspace:Raycast, GetTouchingParts, Touched event |
| `Coroutine` | StartCoroutine, yield, WaitForSeconds | task.spawn, task.wait |
| `Time` | deltaTime, time, timeScale | RunService.Heartbeat delta, os.clock |
| `StateMachine` | GameManager + AState (stack-based state machine) | Enter/Exit/Tick lifecycle, PushState/PopState/SwitchState |
| `Random` | Range, InitState | Random.new, math.random |
| `Addressables` | InstantiateAsync, LoadAssetAsync | InsertService:LoadAsset (with asset ID manifest) |
| `PlayerPrefs` | GetInt, SetInt, Save | DataStoreService or player:SetAttribute |

The bridge API should match Unity's naming so transpiled code needs minimal changes:
```lua
-- Unity C#: transform.position = new Vector3(0, 5, 0);
-- Bridge Luau: self.transform.position = Vector3.new(0, 5, 0)
```

### 2. LLM Script Rewriter (per-game, uses bridge as vocabulary)

A skill/prompt that takes:
- **Input**: Original Unity C# script + bridge module API reference
- **Output**: Roblox-native Luau script that uses bridge modules

The LLM handles the architectural adaptation that syntax translation cannot:
- MonoBehaviour class → Luau module with lifecycle hooks
- Inspector-serialized fields → config table or attributes
- Unity component queries → Roblox instance hierarchy traversal
- Event systems → Roblox BindableEvents or direct function calls
- State machines → Luau tables with enter/exit/tick methods

### How they connect

```
Unity C# Scripts
       ↓
  LLM Rewriter (uses bridge API as vocabulary)
       ↓
  Roblox Luau Scripts (require UnityBridge modules)
       ↓
  Bootstrap Script (wires lifecycle, loads assets, starts game)
       ↓
  Running Roblox Game
```

## Related docs

- `.claude/skills/review-csharp-lua-conversion/` — archived skill (rule-based and AST transpilers removed; all transpilation now uses Claude AI)
- `docs/FUTURE_IMPROVEMENTS.md` — caching, module splitting, serializer improvements
- `docs/MODULE_STATUS.md` — status of all pipeline modules
- `docs/UNSUPPORTED.md` — platform limitations catalog

## What already exists in the codebase

| Component | File | Status |
|-----------|------|--------|
| API mapping tables | `modules/api_mappings.py` | 130+ mappings, comprehensive |
| Lifecycle hook mapping | `api_mappings.py: LIFECYCLE_MAP` | 15 hooks mapped |
| Bootstrap script generator | `modules/conversion_helpers.py: generate_bootstrap_script()` | GameManager state machine wiring |
| AI transpiler (Claude) | `modules/code_transpiler.py: _ai_transpile()` | Claude API, high quality |

**Status**: Bridge Luau modules exist in `bridge/` (Coroutine, GameObjectUtil, Input, MonoBehaviour, Physics, StateMachine, Time). The API mappings in `api_mappings.py` are used by the AI transpiler as reference context; the bridge modules are the runtime counterpart.

**Remaining gap**: The assembly phase does not yet inject bridge modules into ReplicatedStorage/UnityBridge in the .rbxl. This is Phase 3 below.

## Implementation plan

### Phase 1: Bridge modules (reusable) — DONE
Luau modules in `bridge/`. Designed for any Unity game.

### Phase 2: LLM rewrite skill — DONE
The `/convert-unity` skill's Step 4.5 (Game Logic Porting) uses a three-phase approach:
1. **Architectural analysis** — map state machines, component ownership, timing models from original C#
2. **Module-per-component rewrite** — one Luau module per Unity class, preserving the same separation
3. **Bootstrap wiring** — a single entry-point script that creates and cross-references all modules

The skill explicitly prevents the "monolithic flattening" anti-pattern where all game systems get merged into one script. Game-specific output scripts are written to `<output_dir>/scripts/`.

### Phase 3: Assembly integration — TODO
- Assembly phase injects bridge modules from `bridge/` into `ReplicatedStorage/UnityBridge/` in the .rbxl
- `rbxl_writer.py` needs folder creation logic for the UnityBridge subfolder
- LLM-rewritten scripts are placed in `<output_dir>/scripts/` and assembled normally
- Bootstrap script wires everything together

### Where game-specific scripts live

Game-specific scripts (e.g., GameBootstrap, CharacterController) are **not** part of this converter repo. They are LLM-generated output that lives in the game's output directory (`<output_dir>/scripts/`). The converter repo only contains:
- `bridge/` — reusable Unity API shims (injected into every conversion)
- `modules/` — Python pipeline code
- `.claude/skills/` — skills that orchestrate the LLM rewriting

## Lessons learned (Trash Dash port)

1. **Don't flatten the architecture.** The first attempt merged GameManager (state machine), TrackManager (world movement), and CharacterInputController (input/physics) into a single 282-line GameBootstrap.lua. This made the code unreadable and impossible to maintain. The fix: one Luau module per Unity class, with a thin bootstrap that wires them together.

2. **Preserve the timing model.** Unity's Trash Dash uses world-distance-based jump/slide timing (`worldDistance - jumpStart`) / `correctJumpLength`), NOT time-based. Jump/slide lengths scale by `(1 + speedRatio)` so they feel consistent at all speeds. Simplifying this to time-based (`jumpTime / jumpDuration`) changes gameplay feel.

3. **The state machine is reusable.** Unity's GameManager (stack-based state machine with Enter/Exit/Tick and PushState/PopState/SwitchState) appears in many Unity games. This became the `StateMachine` bridge module.

4. **Component ownership graphs matter.** In Unity: `GameState` → `TrackManager` → `CharacterInputController` → `Character`. The Roblox port must wire the same references during bootstrap. Inspector-assigned references become constructor wiring.

5. **Game-specific scripts don't belong in this repo.** They're LLM-generated output artifacts that go to `<output_dir>/scripts/`.

## Key design decisions

1. **Bridge modules are runtime Luau, not transpiler rules.** The AI transpiler produces code that calls bridge APIs. This separates "what Unity API does" from "how to translate syntax."

2. **LLM rewrite is per-script, not per-line.** The LLM sees the full script context and produces an architecturally adapted version, not a line-by-line translation.

3. **Bridge modules are optional.** Simple scripts that don't use Unity APIs can be transpiled directly. The bridge is for scripts that need runtime behavior (Update loops, physics, input).

4. **Asset loading is decoupled.** The MeshLoader/InsertService approach handles asset loading. Game scripts reference assets by name, and the bridge resolves names to loaded instances.
