---
name: convert-unity
description: Convert a Unity game project into a Roblox place file interactively, with decision points at each phase
argument-hint: <unity_project_path> <output_dir>
allowed-tools:
  - Bash(python3 convert_interactive.py *)
  - Bash(python -m pytest *)
  - Read
---

# Convert Unity Project to Roblox

Interactive, phase-based conversion of a Unity game project into a Roblox place (.rbxl). Pause at each decision point for human judgment — do NOT run the pipeline blindly.

All commands output structured JSON to stdout. Redirect stderr (`2>/dev/null`) to keep output clean.

## Workflow

### Step 0: Gather Inputs & Preflight

Ask the user for the Unity project path, output directory, and whether they want AI-assisted transpilation. If provided as arguments, parse from args.

```bash
python3 convert_interactive.py preflight <unity_project_path> <output_dir> --install 2>/dev/null
```

If resuming, check `python3 convert_interactive.py status <output_dir> 2>/dev/null`.

### Step 1: Discovery

```bash
python3 convert_interactive.py discover <unity_project_path> <output_dir> 2>/dev/null
```

**Decision point:** If multiple scenes, ask which to include. If parse errors, ask whether to continue.

### Step 2: Asset Inventory

```bash
python3 convert_interactive.py inventory <unity_project_path> <output_dir> 2>/dev/null
```

**Decision point:** If duplicate GUIDs or orphans, warn and ask how to proceed.

### Step 3: Material Mapping

```bash
python3 convert_interactive.py materials <unity_project_path> <output_dir> 2>/dev/null
```

**Decision point:** For unconvertible/partial materials — accept, provide manual mappings, or skip?

### Step 4: Code Transpilation

```bash
python3 convert_interactive.py transpile <unity_project_path> <output_dir> --api-key <key> 2>/dev/null
```

Handle structured errors: `"insufficient_credits"` / `"auth_failure"` — don't retry, ask user to check their API key. If `"batch_review_suggested": true`, offer batch options.

**Decision point:** For each flagged script, show C# and Luau side-by-side. Ask: Accept, Retry with AI, Edit manually, or Skip?

After review, validate: `python3 convert_interactive.py validate <output_dir> 2>/dev/null`

### Step 4.5: Game Logic Porting (LLM Rewrite)

The AI transpiler converts each file independently. This step provides cross-file architectural awareness — ensuring state machines, component wiring, and platform-specific adaptations are coherent across the full game.

**Do NOT flatten the game into a monolithic script.** The Roblox port must mirror the original Unity project's component separation, state machine structure, and timing models.

#### Phase A: Architectural Analysis (do this BEFORE writing any code)

Read all C# scripts in `<unity_project_path>/Assets/Scripts/` and produce an architecture map:

1. **State machine identification** — Find the game's state machine (often a `GameManager` with `AState` subclasses). Map out:
   - What states exist (e.g., `LoadoutState`, `GameState`, `GameOverState`)
   - State transitions: which state switches/pushes/pops to which, and what triggers it
   - What each state's `Enter`/`Exit`/`Tick` does

2. **Component ownership graph** — Map which MonoBehaviour owns references to which:
   - e.g., `GameState` → `TrackManager` → `CharacterInputController` → `Character`
   - Inspector-assigned references become constructor/config wiring in Luau
   - Identify singletons (`static instance` pattern) — these become module-level state

3. **Timing model** — Identify whether game mechanics use:
   - **Time-based**: `Time.deltaTime` for durations (simple, direct bridge mapping)
   - **World-distance-based**: e.g., jump/slide measured by `worldDistance` traveled, not elapsed time. This is critical — many endless runners scale jump/slide length by `(1 + speedRatio)` so they feel consistent at all speeds. The Roblox port MUST preserve this.
   - **Coroutine-based**: `StartCoroutine` + `yield return` for sequenced events (map to `task.spawn` + `task.wait`)

4. **Platform divergence analysis** — This is the most critical step. Unity is a blank canvas: no default character, camera, input, or physics. You build everything from scratch. Roblox is the opposite: every player spawns with a fully working character, camera, input system, and physics body. The port must decide, for each of these four pillars, whether the Unity game's approach matches Roblox's defaults or conflicts with them.

   For each pillar, read the Unity C# code and answer: **"Does the Unity game do this itself, or would it rely on an engine default?"** Then decide: **"Does Roblox's default do the same thing, or do we need to override it?"**

   | Pillar | What Unity provides (nothing) | What Roblox provides by default | Override needed when... |
   |--------|------------------------------|--------------------------------|------------------------|
   | **Character** | No character exists until you Instantiate one and attach scripts | Player gets a Humanoid rig with health, collision, animation | The game uses a custom character controller, non-humanoid avatar, or no visible character |
   | **Camera** | No camera behavior until you write a script or attach a component | Third-person follow camera that orbits the character | The game uses fixed camera, rail camera, top-down, isometric, or any non-orbit view |
   | **Input → Movement** | No movement until you write `Update()` + `transform.Translate()` or a CharacterController | WASD/mobile stick moves the character, Space jumps, Humanoid handles it all | The game uses custom movement (auto-run, on-rails, grid-based, turn-based, vehicle, etc.) |
   | **Physics** | Rigidbody is opt-in, gravity/collision configured per-object | All parts have physics, character has Humanoid physics with WalkSpeed/JumpPower | The game positions objects directly via CFrame/Transform rather than through physics forces |
   | **Asset loading** | Unity loads meshes/textures from the Asset pipeline — once imported, they're embedded in the build and available immediately via Renderer/MeshFilter references. `Addressables.LoadAssetAsync` handles dynamic loading. | `MeshId` is **read-only at runtime** — scripts cannot set it. Meshes must be loaded via `InsertService:LoadAsset(assetId)` which returns a Model. To use the mesh, **clone** the MeshPart from the loaded Model and place the clone in the scene. You cannot create an empty MeshPart and assign its mesh later. | **Always for uploaded FBX assets.** The pipeline uploads FBX files as Model assets, then generates a MeshLoader script that loads them via InsertService at runtime. Scene MeshParts are placeholders that get **replaced** (not patched) by clones of the loaded assets. See `references/upload-patching.md` for the full pattern. |
   | **Object visibility** | In Unity, only GameObjects with a MeshRenderer, SkinnedMeshRenderer, or SpriteRenderer are visible. Everything else — script containers, empty transforms, trigger volumes, collider-only objects, disabled GameObjects, disabled renderers — is invisible by design. A Unity scene typically has far more invisible objects than visible ones. | Every Part is visible by default. There is no concept of a "renderer component" separate from the object. A Part with no mesh and no special properties still renders as a gray block. | **Always.** The pipeline sets `Transparency=1` on any object without a renderer component. This is the single most important visibility rule: **no renderer = invisible**. Additionally: trigger colliders (`isTrigger`), inactive GameObjects (`m_IsActive=0`), disabled renderers (`m_Enabled=0`), and UI subtrees (Canvas hierarchies) are all handled. If opaque gray rectangles block the view in the converted game, the root cause is almost always a non-visual Unity object that was not marked transparent. |
   | **Game loop** | Unity implicitly calls `Update()`, `FixedUpdate()`, `LateUpdate()` every frame on all active MonoBehaviours. The developer writes the method body; the engine calls it. | Roblox has no implicit per-frame callbacks. Code runs only when explicitly connected to `RunService.Heartbeat`, `RunService.Stepped`, or similar signals. A method named `Update()` that isn't connected to anything will never execute. | **Always, for every MonoBehaviour that had `Update()`/`FixedUpdate()`/`LateUpdate()`.** The transpiler preserves the method body but does NOT add the RunService connection. Either the transpiler or the bootstrap must add `RunService.Heartbeat:Connect(function(dt) obj:Update(dt) end)`. Without this, the game loads and appears frozen — no movement, no spawning, no scoring. Also disconnect in cleanup paths (`End()`, `OnDisable()`, `Destroy()`). |
   | **Threading / yielding** | Unity coroutines (`yield return`) run cooperatively within the main thread. `WaitForSeconds`, `WaitForEndOfFrame` are common yields. Code in `Update()` never yields — it runs to completion every frame. | Roblox signal callbacks (`Heartbeat:Connect`, `Touched:Connect`) **cannot yield**. If `task.wait()`, `wait()`, or any yielding call appears inside a signal callback, execution silently stops at that line — no error, no warning, the rest of the function never runs. Coroutine-style code must use `task.spawn()` or `task.delay()` to run in a separate thread. | **Always when converting `Update()`-like code.** C# `Time.deltaTime` references in `Update()` must become the `dt` parameter from Heartbeat. C# coroutines (`StartCoroutine`) must become `task.spawn(function() ... end)`. Never emit `task.wait()` inside any function that runs from a signal callback. **Critical: do NOT use `coroutine.wrap` for C# IEnumerator methods.** The transpiler often wraps every `IEnumerator` in `coroutine.wrap(function() ... end)()`. This creates a raw Lua coroutine, not a Roblox thread. If the body contains `task.wait()`, it will not resume properly. **Rules:** (1) If the method has no yields, just make it a plain function. (2) If it yields, use `task.spawn(function() ... end)` to create a proper Roblox thread. (3) Never use `coroutine.wrap` + `task.wait()` together. |
   | **C# properties** | C# properties (`public float speed { get; }`) look like field access at call sites (`obj.speed`) but execute getter/setter code. This is transparent to the caller. | Lua has no native property syntax. The transpiler creates getter methods (`getSpeed()`) and may alias them on the class table (`MyClass.speed = MyClass.getSpeed`). But class-level aliases resolve to the *function itself*, not its return value — `instance.speed` returns the function, not the value. | **Always, for any class with C# properties.** The transpiler must use `__index`/`__newindex` metamethods to dispatch property access to getters/setters. See semantic gap #10 for the pattern. Class-level aliases (`MyClass.prop = MyClass.getProp`) are fundamentally broken because Lua resolves them on the class table, not the instance. |
   | **ScriptableObject data** | Unity ScriptableObjects are serialized data assets (`.asset` files) that the engine loads automatically. They can reference other assets (prefabs, meshes, sprites) by GUID, and the Addressables system resolves GUIDs to loaded objects at runtime. Code reads `themeData.zones[0].prefabList` and gets live GameObjects ready to Instantiate. | Roblox has no equivalent of ScriptableObjects or GUID-based asset references. Data must be stored in ModuleScripts that return Lua tables, and asset references must point to actual Instances in ReplicatedStorage/Templates by name, not by GUID. There is no automatic resolution step. | **Always, for any game that uses ScriptableObjects for configuration data.** The converter transpiles ScriptableObject `.asset` files into `_Data.lua` ModuleScripts, but the resulting data still contains raw GUIDs (`AssetGUID = "2d48..."`) and `nil -- (Unity object reference)` placeholders. These must be resolved: GUIDs must be mapped to the names of corresponding prefab Templates in ReplicatedStorage, and the data-loading code (e.g., `ThemeDatabase.LoadDatabase()`) must find the data modules and be called before game start. The bootstrap must ensure all database initialization runs **before** entering gameplay — skipping loading screens (LoadoutState) can leave databases empty. |
   | **ScreenGui placement** | Unity Canvas UIs live in the scene hierarchy under a Canvas component. They are inactive or hidden until the game's state machine enables them (e.g., `SetActive(true)` in a menu state's `Enter()`). There is no auto-display mechanism. | `StarterGui` children are **auto-cloned to PlayerGui** on every character spawn. Any ScreenGui placed there appears immediately, overlaying the 3D view — even if `Enabled=false` is set on the source, the clone resets behavior unpredictably. | **Always for converted Canvas UIs.** Place all converted ScreenGuis in `ReplicatedStorage` with `Enabled = false`. The game's bootstrap or state machine parents specific GUIs to `PlayerGui` when needed (e.g., menu state `Enter()` moves the menu GUI in, `Exit()` moves it out). The assembler (`rbxl_writer.py`) already implements this. Never place converted UIs in StarterGui. |
   | **Database initialization order** | Unity games typically load databases (character data, theme data, consumable lists) during a loading screen or splash screen. `Awake()`/`Start()` on manager objects triggers `LoadDatabase()` calls. The game flow guarantees data is ready before gameplay begins. | Roblox has no built-in loading screen or guaranteed initialization order. If the bootstrap skips UI states (like a loadout/shop screen), any database initialization those states trigger will be missed. Scripts that depend on loaded data will get `nil`. | **Always when the bootstrap auto-skips to gameplay.** The bootstrap must call all `LoadDatabase()` functions explicitly before entering the game state. Check every singleton's `Create()`/`Init()` method for database loading side effects. A common pattern: `PlayerData.Create()` triggers `CharacterDatabase.LoadDatabase()` and `ThemeDatabase.LoadDatabase()` — if `Create()` isn't called, all downstream data is nil. |
   | **Array indexing (0-based vs 1-based)** | C# arrays and lists are 0-based. Index variables like `usedTheme = 0` mean "first element". Default values, serialized state, and loop counters all assume 0-based indexing. | Lua arrays are 1-based. Array access must add +1: `arr[index + 1]`. But **stored index values must stay 0-based** — the +1 is applied only at the point of access, not in the stored value. | **Always, and the bug is subtle.** The transpiler correctly converts array access (`arr[i]` → `arr[i + 1]`), but it must NOT also convert the default/initial values of index variables. If C# has `usedTheme = 0` (meaning first element) and the transpiler changes it to `usedTheme = 1`, then `themes[usedTheme + 1]` becomes `themes[2]` — an off-by-one that returns `nil`. Same applies to serialization defaults, save/load code, and any "new game" initialization. **Rule:** Index variables keep their C# value (0-based); the +1 adjustment lives only in array subscript expressions. |
   | **Part size limits** | Unity has no practical size limit on GameObjects/colliders — a ground plane can be 100,000 units wide. | Roblox Parts **silently fail to render** if any dimension exceeds 2048 studs. No error, no warning — the Part exists in the data model but is invisible. | **Always when converting large scene geometry.** Ground planes, roads, terrain boundaries, and skybox geometry from Unity often exceed 2048 studs after conversion. Either (a) clamp to 2048 and tile multiple Parts, or (b) use Roblox Terrain for large ground surfaces. A 20,000-stud road renders as nothing. |
   | **Input wiring** | Unity reads input in `Update()` via `Input.GetKeyDown()`, `Input.GetAxis()`, etc. The engine polls hardware every frame. No setup required — just call the API. | Roblox uses `UserInputService.InputBegan`/`InputEnded` signals. There is no polling API. The transpiler converts the method bodies but does NOT create the signal connections. | **Always.** The bootstrap must connect `UserInputService.InputBegan` to dispatch keyboard/touch input to the appropriate controller methods (e.g., A/D → `ChangeLane()`, Space → `Jump()`). Without this, the game appears frozen to player input even though the game loop runs. Map Unity's `Input.GetKeyDown(KeyCode.X)` calls to the equivalent `Enum.KeyCode.X` checks in the signal handler. |
   | **Character positioning** | Unity places objects wherever the scene file says. The character controller's `Transform.position` is set by the scene or by code. There is no "default spawn." | Roblox spawns the player's character at a `SpawnLocation` or the origin. The HumanoidRootPart position is determined by the spawn system, not by game scripts, until scripts explicitly set it. | **Always when overriding the Roblox character.** After anchoring HumanoidRootPart and disabling default movement, the bootstrap must also set `hrp.CFrame` to position the character on the game's starting location (e.g., on the road surface). Without this, the avatar floats at the default spawn point, visually disconnected from the game world. |
   | **Runtime content generation** | Many Unity games generate content at runtime — procedural levels, spawned obstacles, pooled projectiles, track segments. This logic lives in `Update()` methods that check distance/time thresholds and call `Instantiate()`. | The transpiler converts the classes but often strips or stubs the spawning logic because it depends on prefab references (Inspector-serialized), object pooling systems, and `Instantiate()` calls that have no direct Roblox equivalent. | **Always for games with procedural content.** After transpilation, verify that the core game loop actually spawns content — check for empty `m_Segments` arrays, missing `Instantiate` calls, and nil prefab references. Typically requires manual porting: convert Unity prefab templates to Models in ReplicatedStorage/Templates, replace `Instantiate()` with `:Clone()`, and ensure the spawning logic in `Update()` survived transpilation. This is the #1 reason a converted game "runs" (score ticks up, character moves) but looks empty. |

   For each pillar where the Unity game diverges from Roblox's default:
   - Identify exactly what the Unity code does (e.g., "TrackManager sets character position each frame from a spline curve")
   - Decide how to override the Roblox default (e.g., "Anchor HumanoidRootPart, set WalkSpeed=0, drive CFrame from script")
   - If the Unity system is too complex to port fully, design a simpler approximation that preserves the gameplay feel

   **This is a design decision, not a checklist.** Present the divergence table to the user and ask which approach they want for each pillar.

5. **Scale & positioning** — Unity uses 1 unit ≈ 1 meter. Roblox characters are ~5.5 studs tall vs Unity's ~1.8 units. Determine the scale relationship between the imported scene geometry and Roblox's defaults, and decide whether to scale the world up, scale the character down, or apply a conversion factor to gameplay values. Present the tradeoffs to the user.

   **Important pipeline detail:** Unity stores all transforms as local-space (relative to parent). The converter automatically computes world-space positions for Roblox CFrames by recursively applying `world_pos = parent_pos + parent_rot * local_pos`. If objects appear clustered at the origin in the converted game, the world-space transform computation may have a bug — check `conversion_helpers.py:_compute_world_transform()` and the recursive `node_to_part()` calls.

6. **Implementability check** — For each Unity system, assess whether it can be ported as-is or needs simplification. A working simple version beats a broken complex one. If a system (e.g., procedural track segments, spline evaluation) cannot be ported, implement an approximation and document what's missing so it can be improved later.

**Decision point:** Present the architecture map (items 1–6) to the user. Include the platform divergence table. Ask: "Does this match your understanding of the game? For each pillar where Unity and Roblox diverge, which approach do you want?"

#### Phase B: Module-per-Component Rewrite

For each major game system, write a **separate Luau module** that mirrors its Unity counterpart:

| Unity class | Roblox module | Bridge modules used |
|---|---|---|
| `GameManager` + `AState` subclasses | State modules + bootstrap wiring via `StateMachine` | `StateMachine` |
| `TrackManager` | `TrackManager.lua` | `GameObjectUtil`, `Time` |
| `CharacterInputController` | `CharacterController.lua` | `Input`, `Physics` |
| Game-specific MonoBehaviours | One module per behaviour | `MonoBehaviour` |

**Rules for each module:**
- Preserve the same public API shape as the Unity class (methods, properties)
- Inspector fields → config table passed to constructor
- `GetComponent<T>()` / singleton access → explicit references passed in during wiring
- Component-to-component references → set during bootstrap, same as Unity's Inspector drag-and-drop
- **Never merge two Unity classes into one Luau module** — if they were separate in Unity, they stay separate

**Unity→Luau semantic gaps to catch during transpilation:**

The AI transpiler translates C# syntax but can miss platform-level semantic differences. These are the known categories where 1:1 translation produces broken Luau:

1. **MonoBehaviour lifecycle vs explicit construction.** Unity components are never `new()`-ed in code — they're attached to GameObjects and their fields are populated by the Inspector (serialized scene references). The transpiler converts these to `ClassName.new(config)` constructors, but callers may not know what config to pass (that info is in `.unity` YAML, not C# source). *Decision:* All constructors must start with `config = config or {}` and default every field. The bootstrap wires references after construction, same as Unity's Inspector.

2. **C# properties → Luau has no `property()`.** C# `get`/`set` accessors have no Luau equivalent. If a property is trivial (just wraps a backing field), use a direct field. If it has side effects, use getter/setter methods. Never emit `property()` calls.

3. **Binary serialization → table fields.** Unity often persists data via `BinaryWriter`/`BinaryReader`. Roblox uses DataStore (JSON via Lua tables). Replace `writer.Write(x)` / `reader.Read()` with `data.field = x` / `x = data.field`.

4. **Cross-module exports.** When a module returns `{ ClassA = ClassA, EnumB = EnumB }`, access the export directly: `Module.EnumB`, not `Module.ClassA.EnumB`. The export table is flat — classes don't own sibling exports.

5. **`GetComponent<T>()` on cloned objects.** Unity's `GetComponent` finds a component on a GameObject. In Roblox, cloned Instances don't have "components" — the object IS the thing. Adapt to Roblox's Instance hierarchy (`FindFirstChild`, `:IsA()`, or direct construction).

6. **Singleton accessor functions vs properties.** In C#, `PlayerData.instance` is a static property (getter returns the singleton). The transpiler converts this to a module export `instance = getInstance` — a **function**, not a value. But call sites still emit `PlayerData.instance` (property-style access), which returns the function itself instead of calling it. All singleton accessors must be called: `Module.instance()`, not `Module.instance`. This affects every script that touches the singleton. The transpiler should either (a) emit `Module.instance()` at call sites, or (b) use a metatable `__index` so property-style access works. Until then, audit every `Module.instance` usage — if the module exports `instance = someFunction`, every access must have `()`.

7. **Unity MonoBehaviour lifecycle → Luau explicit calls.** Unity implicitly calls lifecycle methods on every MonoBehaviour in a specific order. Roblox has no equivalent — all lifecycle calls must be explicit in the bootstrap or via RunService connections. The transpiler preserves these methods but the bootstrap must actually call them. **Never invent method names** (e.g., don't call `:Start()` if the transpiled module only has `:OnEnable()`). Always verify the method exists in the transpiled output before calling it.

   | Unity lifecycle method | When Unity calls it | Roblox equivalent |
   |---|---|---|
   | `Awake()` | Once, when the object is created (before Start) | Call in constructor `.new()`, or immediately after construction |
   | `OnEnable()` | When the object becomes active | Call explicitly after construction + wiring. Often the real "start" for managers |
   | `Start()` | Once, on the first frame the object is active | Call explicitly after `OnEnable()`, or merge into `OnEnable()` if both exist |
   | `Update()` | Every frame | `RunService.Heartbeat:Connect(function(dt) obj:Update(dt) end)` |
   | `FixedUpdate()` | Every physics step | `RunService.Stepped:Connect(function(dt) obj:FixedUpdate(dt) end)` |
   | `LateUpdate()` | Every frame, after all Update calls | `RunService.Heartbeat:Connect()` with a lower priority or after other connections |
   | `OnDisable()` | When the object is deactivated | Call explicitly during cleanup / state exit |
   | `OnDestroy()` | When the object is destroyed | Call explicitly, or use `Instance.Destroying` signal |
   | `OnTriggerEnter/Exit()` | Physics trigger events | `part.Touched` / `part.TouchEnded` signals |
   | `OnCollisionEnter/Exit()` | Physics collision events | `part.Touched` / `part.TouchEnded` signals |

   **Key pitfall:** The transpiler may rename or merge lifecycle methods inconsistently. Some modules keep `OnEnable`, others rename it to `Start`, others have both. The bootstrap must read each module's actual method names — never assume a standard name exists.

   **Critical: `Update()`/`FixedUpdate()` require explicit Heartbeat wiring** — see the "Game loop" row in the platform divergence table above.

9. **C# property getters transpiled as function aliases — the silent killer.** C# properties like `public float speed { get { return _speed; } }` get transpiled as a getter method (`getSpeed()`) plus a class-level alias: `MyClass.speed = MyClass.getSpeed`. This makes `instance.speed` return the *function itself*, not the value. **This must be applied to EVERY class with properties, not just the main class.** If ClassA has `__index` metamethods but ClassB (used by ClassA) doesn't, `classB.worldLength` returns nil even though `getWorldLength()` exists. Every property-style access silently returns a truthy function reference instead of the actual data. This causes cascading failures:
   - `#instance.segments` → "attempt to get length of a function value"
   - `if not instance.isRerun` → always false (function is truthy), skipping critical initialization
   - `instance.score + 1` → "attempt to perform arithmetic on a function value"

   **Fix:** Replace class-level aliases with a `__index` metamethod that calls getters automatically:
   ```lua
   local _getters = {}
   local _setters = {}
   MyClass.__index = function(self, key)
       local getter = _getters[key]
       if getter then return getter(self) end
       return MyClass[key]
   end
   MyClass.__newindex = function(self, key, value)
       local setter = _setters[key]
       if setter then setter(self, value) return end
       rawset(self, key, value)
   end
   -- Then register: _getters.speed = MyClass.getSpeed
   -- And setters:   _setters.speed = function(self, v) self._speed = v end
   ```
   This makes `instance.speed` transparently call `getSpeed(self)` and `instance.speed = 5` call the setter. The transpiler MUST emit this pattern for any class with C# properties — class-level aliases (`MyClass.prop = MyClass.getProp`) are fundamentally broken because Lua resolves them on the *class table*, not the instance.

10. **Inspector-serialized ScriptableObject references are nil at runtime.** In Unity, a MonoBehaviour field like `public ThemeData tutorialThemeData` is populated by dragging a ScriptableObject asset onto it in the Inspector. At runtime, the field has a valid reference. In Roblox, the transpiler converts this to `self.tutorialThemeData = config.tutorialThemeData` — but the config never has this value because there's no Inspector. The field stays nil, and any code path that reads it crashes. **Fix:** For data references that point to ScriptableObjects now converted to `_Data` ModuleScripts, wire them through the database lookup: `self.tutorialThemeData = ThemeDatabase.GetThemeData("Tutorial")`. For Inspector refs to prefabs/GameObjects, resolve through the Templates folder in ReplicatedStorage. The bootstrap or the module constructor must do this wiring — the transpiler cannot, because the mapping from GUID to name requires the scene file.

11. **State-managed scene objects require explicit wiring.** Unity state machines (e.g., `LoadoutState`/`GameState`) toggle scene objects' visibility as part of state transitions — a menu backdrop is shown during the loadout screen and hidden when gameplay starts. These scene object references come from Inspector serialization (`public GameObject menuEnvironment`), so they're nil in Roblox. Unlike data references (#10), these are **3D objects already in workspace** that need to be found by name and passed through config. **Fix:** The bootstrap must `workspace:FindFirstChild("ObjectName")` for each state-managed scene object and pass it to the state's config table. The state's `Enter()`/`Exit()` calls `GameObjectUtil.SetActive(obj, true/false)` which toggles `Transparency` and `CanCollide` — the object stays in workspace, never gets reparented. **Never use `obj.Parent = nil` to hide objects** — this nulls the parent and causes cascading errors when other code reads `.Parent`. To identify which objects need wiring: look for `public GameObject` fields on state classes that aren't prefabs or UI — they're scene environment objects toggled by `SetActive(true/false)` in `Enter()`/`Exit()`.

12. **SetActive must use GameObjectUtil, never Parent assignment.** Unity's `GameObject.SetActive(bool)` toggles visibility. The transpiler must convert `obj.SetActive(false)` → `GameObjectUtil.SetActive(obj, false)`, which sets `Transparency=1` and `CanCollide=false`. **Never emit** `obj.Parent = nil` or `obj.Parent = ReplicatedStorage` as a visibility toggle — this detaches the object from the scene tree, and any subsequent code that reads `obj.Parent` (including the MeshLoader replacement pattern) gets nil, causing silent failures or crashes. The bridge module `GameObjectUtil` must be required at the top of any module that calls SetActive.

**Timing model preservation:**
- If Unity uses `trackManager.worldDistance` to measure jump/slide progress, the Roblox port must too
- If Unity scales durations by `(1 + speedRatio)`, the Roblox port must too
- Do NOT simplify world-distance timing into time-based timing — it changes gameplay feel

**Porting procedural content / runtime spawning systems:**

Many Unity games generate gameplay content at runtime — endless runner segments, spawned enemies, projectile pools, procedural terrain chunks. This is the #1 system that **does not survive transpilation** because it depends on Inspector-serialized prefab references, Addressables async loading, and object pooling — none of which have Roblox equivalents. The transpiled code keeps the scoring/movement logic but the spawning methods become empty shells with nil references.

**Typical Unity spawning architecture (endless runner pattern):**
```
Update() → SpawnNewSegment() → SpawnObstacle() → SpawnCoinAndPowerup()
```
- A `ThemeData` ScriptableObject holds `zones[]`, each with `prefabList[]` of track segment prefab references
- Each segment prefab has: path waypoints, `obstaclePositions[]` (normalized t-values along the path), `possibleObstacles[]` (addressable refs to obstacle prefabs)
- The manager maintains N segments ahead (e.g., 10), destroys segments that fall behind the player (e.g., -30 units back), and keeps the first few segments obstacle-free for a safe start
- Obstacle types vary: static barriers spanning lanes, patrolling obstacles with PingPong movement, collectibles spawned at intervals along the segment path

**Why it breaks:** Segment prefab references are Inspector-serialized AssetReferences (nil in Roblox). Prefab loading uses Unity Addressables (no equivalent). Object pooling libraries are not transpiled. The transpiled manager keeps `Update()` ticking but `SpawnNewSegment()` has zero functional spawning code.

**Porting pattern (applies to any prefab-spawning system):**

1. **Convert prefab templates to Models in ReplicatedStorage/Templates.** Each Unity segment/obstacle/collectible prefab becomes a named Model that can be cloned. The pipeline's assembly phase should already produce these from the prefab files.

2. **Write a `SpawnNewSegment()` (or equivalent) that `:Clone()`s segment templates** and positions them ahead of the player. Use the ScriptableObject data modules (`_Data.lua`) to look up which templates belong to the current zone/theme — but resolve GUIDs to Template names first (see semantic gap #10).

3. **Spawn obstacles onto segments at clone time.** Read each segment's `obstaclePositions` and `possibleObstacles` from the data, clone the obstacle template, and parent it to the segment Model at the correct position.

4. **Spawn collectibles (coins, powerups) using simple Part creation** along the segment's path at fixed intervals. Unity often uses physics raycasting for precise placement — approximate with known path geometry instead.

5. **Implement segment cleanup.** When a segment falls behind the player past a threshold distance, `:Destroy()` it. No need to port Unity's object pooling — Roblox's instance creation is fast enough for most games.

6. **Wire into the game loop.** The spawning check (`if segmentCount < desiredCount then spawnNew()`) must run every frame via the Heartbeat connection, just like Unity's `Update()`.

**Diagnostic:** If a converted game "runs" (score increments, character animates) but the world is empty — no track, no obstacles, no coins — the spawning system was not ported. Check the manager's `m_Segments` or equivalent array: if it stays empty, spawning is broken.

#### Phase C: Bootstrap Wiring

Write a `GameBootstrap.lua` (LocalScript in StarterPlayerScripts) that:
- Creates instances of each module — **always pass `{}` even if no config is needed** (constructors expect a table, not nil)
- Wires cross-references **after** construction (same as Unity's Inspector references — components are created first, then linked)
- Registers states with the StateMachine bridge
- Starts the state machine with the initial state
- Does NOT contain game logic — it's pure wiring
- To determine what to wire: read the `.unity` scene file for serialized field references (e.g., `characterController: {fileID: XXXX}` tells you TrackManager needs a reference to CharacterInputController)
- **Uses the player's Roblox avatar** as the game character when appropriate (e.g., endless runners, platformers). Wait for `player.Character`, get `HumanoidRootPart`, anchor it, disable default movement (`WalkSpeed=0`, `JumpPower=0`, `JumpHeight=0`), set initial `CFrame` on the track, and pass HRP as the `transform` to the character controller. Only create a placeholder Part if the game uses a non-humanoid avatar.
- **Wires input** via `UserInputService.InputBegan` — the transpiler does NOT create input bindings. Map Unity's `Input.GetKeyDown` keycodes to Roblox `Enum.KeyCode` and dispatch to controller methods (`ChangeLane`, `Jump`, `Slide`, etc.).
- **Wires collision signals** for any module that defines `OnTriggerEnter`, `OnTriggerExit`, `OnCollisionEnter`, or `OnCollisionExit`. Unity's engine calls these implicitly on any MonoBehaviour attached to a GameObject with a collider. Roblox requires explicit collision wiring. **Choose the right mechanism based on how the part moves:**
  - **Physics-driven parts** (unanchored, moved by forces): use `.Touched`/`.TouchEnded` signals.
  - **CFrame-driven parts** (anchored, moved by setting CFrame each frame): `.Touched` is **unreliable** — Roblox's physics engine doesn't fire touch events for parts moved via CFrame. Use `workspace:GetPartsInPart(part, overlapParams)` in a per-frame `Heartbeat` loop instead. This is the common case for converted games where the character controller directly sets position.

  For the per-frame overlap pattern, use an `alreadyHit` set to prevent duplicate triggers per object, and filter out the character's own parts via `OverlapParams.FilterDescendantsInstances`. **The bootstrap only wires the signal — the transpiled method decides what to do.** Never add game-specific collision filtering in the bootstrap.

**Module export unwrapping — CRITICAL.** The transpiler is inconsistent about how modules export their classes. Some return the class directly (`return MyClass`), others wrap it in a table (`return { MyClass = MyClass, SomeEnum = SomeEnum }`). The bootstrap **must not assume** which style a module uses. Before writing `require()` calls, inspect each module's `return` statement. Use a defensive unwrap helper:

```lua
local function unwrap(mod, name)
    if type(mod) == "table" and mod[name] then return mod[name] end
    return mod
end

local SomeModule = unwrap(require(ReplicatedStorage:WaitForChild("SomeModule")), "SomeModule")
```

Why: if you write `local Foo = require(...)` and the module returns `{ Foo = Foo }`, then `Foo.new()` calls the wrapper table (which has no `.new`), producing "attempt to call a nil value". This is silent until runtime and affects every module whose return style doesn't match the bootstrap's assumption.

**Implement the platform divergence decisions from Phase A, item 4.** For each pillar where the Unity game diverges from Roblox's defaults, the bootstrap must apply the appropriate override. Apply the scale conversion decision from Phase A, item 5.

#### Output location

Write all scripts to `<output_dir>/scripts/`:
- One file per module (e.g., `TrackManager.lua`, `CharacterController.lua`, `GameState.lua`)
- `GameBootstrap.lua` — the entry point that wires everything
- These replace the raw transpiled versions for core systems

#### Decision point

Present each rewritten module to the user for review. Show:
- Which Unity C# class(es) it was derived from
- The ownership graph: what references it holds, what references it
- Which bridge modules it uses
- Any timing model decisions (world-distance vs time-based)
- Ask: Accept, Edit, or Regenerate?

#### CRITICAL: Unity→Roblox Visibility Rule

**No renderer = invisible. This is non-negotiable.**

Unity and Roblox have opposite defaults for object visibility:
- **Unity:** Objects are invisible unless they have a renderer component (MeshRenderer, SkinnedMeshRenderer, SpriteRenderer). A typical Unity scene has dozens of invisible objects — script containers, empty transforms, trigger volumes, audio sources, managers — and they are never seen by the player.
- **Roblox:** Every Part is visible by default. A Part with no mesh renders as an opaque gray block.

The pipeline MUST set `Transparency = 1` on every converted Part that lacks a renderer component. Without this, the Roblox game will be filled with opaque gray rectangles that block the player's view. This is the #1 visual correctness issue in Unity→Roblox conversion.

The full visibility rules (all enforced in `conversion_helpers.py:node_to_part()`):
1. **No renderer and no mesh** → `Transparency = 1, CanCollide = false` (script containers, empty transforms, manager objects)
2. **Trigger colliders** (`isTrigger = true`) → `Transparency = 1` (invisible collision volumes)
3. **Inactive GameObjects** (`m_IsActive = 0`) → `Transparency = 1, CanCollide = false`
4. **Disabled renderers** (`m_Enabled = 0` on MeshRenderer) → `Transparency = 1`
5. **UI subtrees** (Canvas hierarchies) → filtered out of 3D hierarchy entirely, converted to ScreenGui

If opaque gray blocks appear in the converted game, check which Unity object they came from and verify it falls into one of these categories.

#### Key principles

- **Faithful port over workarounds** — if Unity generates content at runtime (procedural levels, spawned obstacles, dynamic UI), the Roblox port must generate it at runtime too. Never substitute a Unity runtime system with a static Roblox-side workaround (e.g., don't replace procedural track generation with a hand-placed baseplate). The game should work the same way — if there's no static ground in Unity, there should be no static ground in Roblox.
- **Architecture preservation over code translation** — the goal is a Roblox game that is wired the same way the Unity game was, not a line-by-line translation
- **Port the system, not the symptom** — when something is missing or broken, trace back to what Unity system produces it and port that system. A missing floor means the track spawner needs porting, not that a floor needs adding.
- Bridge modules (`bridge/`) are reusable — never modify them for one game
- Game-specific scripts are output artifacts — they live in `<output_dir>/scripts/`, not in this repo
- Focus on the 3-5 scripts that define the core game loop; leave utility scripts as-is from transpilation
- When in doubt about a design decision, check what the Unity code actually does

### Step 5: Assembly

```bash
python3 convert_interactive.py assemble <unity_project_path> <output_dir> 2>/dev/null
```

**Decision point:** If mesh decimation significantly reduced meshes, ask about quality adjustment.

### Step 6: Upload (Optional)

Ask if they want to upload. Requires Roblox Open Cloud API key, Universe ID, Place ID.

```bash
python3 convert_interactive.py upload <output_dir> \
  --roblox-api-key <key> --universe-id <id> --place-id <id> \
  [--creator-id <id> | --creator-username <username>] \
  [--creator-type User|Group] 2>/dev/null
```

**Decision point:** If some uploads fail — retry, continue without, or abort?

### Step 7: Final Report

```bash
python3 convert_interactive.py report <output_dir> 2>/dev/null
```

## Error Handling

If any phase fails, show the error and ask how to proceed (retry, skip, abort). Never silently swallow errors.

## Guidelines

- Be concise in summaries but thorough at decision points
- Use fenced code blocks with language tags for C# or Luau
- For large lists, summarize counts first, then offer to drill into specifics
- Remember earlier decisions — don't re-ask for the same category

See `references/` for detailed upload patching strategies and assembly internals.
