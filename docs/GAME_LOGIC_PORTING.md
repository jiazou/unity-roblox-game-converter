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

- `.claude/skills/review-csharp-lua-conversion/` — AST-driven transpilation approach using tree-sitter (syntax translation, complements this doc's architectural adaptation)
- `docs/FUTURE_IMPROVEMENTS.md` — caching, module splitting, serializer improvements
- `docs/MODULE_STATUS.md` — status of all pipeline modules
- `docs/UNSUPPORTED.md` — platform limitations catalog

## What already exists in the codebase

| Component | File | Status |
|-----------|------|--------|
| API mapping tables | `modules/api_mappings.py` | 130+ mappings, comprehensive |
| Lifecycle hook mapping | `api_mappings.py: LIFECYCLE_MAP` | 15 hooks mapped |
| Bootstrap script generator | `modules/conversion_helpers.py: generate_bootstrap_script()` | GameManager state machine wiring |
| Rule-based transpiler | `modules/code_transpiler.py` | 73+ regex rules, ~70% accuracy |
| AST-based transpiler | `modules/code_transpiler.py: _ast_transpile()` | tree-sitter, partial |
| AI-assisted transpiler | `modules/code_transpiler.py: _ai_transpile()` | Claude API, high quality but syntax-only |

**Gap**: No bridge Luau modules exist yet. The API mappings in `api_mappings.py` are used by the transpiler for text substitution but aren't runtime modules. The bootstrap script generator handles one specific pattern (GameManager state machine) but isn't general-purpose.

## Implementation plan

### Phase 1: Bridge modules (reusable)
Write the Luau modules listed above. Test with Trash Dash but design for any Unity game.

### Phase 2: LLM rewrite skill
Create a skill that reads a C# script, the bridge API, and the scene context (what GameObjects exist, what components they have) and produces a working Luau rewrite.

### Phase 3: Integration
- Assembly phase injects bridge modules into ReplicatedStorage
- LLM rewrites each script during the transpile phase (alongside or instead of regex/AST)
- Bootstrap script wires everything together
- MeshLoader handles asset loading at runtime

## Key design decisions

1. **Bridge modules are runtime Luau, not transpiler rules.** The transpiler produces code that calls bridge APIs. This separates "what Unity API does" from "how to translate syntax."

2. **LLM rewrite is per-script, not per-line.** The LLM sees the full script context and produces an architecturally adapted version, not a line-by-line translation.

3. **Bridge modules are optional.** Simple scripts that don't use Unity APIs can be transpiled directly. The bridge is for scripts that need runtime behavior (Update loops, physics, input).

4. **Asset loading is decoupled.** The MeshLoader/InsertService approach handles asset loading. Game scripts reference assets by name, and the bridge resolves names to loaded instances.
