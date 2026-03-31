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

#### Step 4.5a: Architecture Map

Read all C# scripts in `<unity_project_path>/Assets/Scripts/` and produce:

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
   - **World-distance-based**: e.g., jump/slide measured by `worldDistance` traveled, not elapsed time. Many endless runners scale by `(1 + speedRatio)`. The Roblox port MUST preserve this.
   - **Coroutine-based**: `StartCoroutine` + `yield return` for sequenced events (map to `task.spawn` + `task.wait`)

**Decision point:** Present the architecture map to the user. Ask: "Does this match your understanding of the game?"

#### Step 4.5b: Character, Camera & Movement Divergence

Unity is a blank canvas: no default character, camera, input, or physics. Roblox provides all of these. For each pillar below, read the Unity C# code and answer: **"Does the Unity game do this itself?"** Then decide: **"Does Roblox's default do the same thing, or do we need to override it?"**

**Character:**
- Unity: No character exists until you Instantiate one and attach scripts
- Roblox: Player gets a Humanoid rig with health, collision, animation
- Override when: the game uses a custom character controller, non-humanoid avatar, or no visible character

**Camera:**
- Unity: No camera behavior until you write a script or attach a component
- Roblox: Third-person follow camera that orbits the character
- Override when: the game uses fixed camera, rail camera, top-down, isometric, or any non-orbit view

**Input → Movement:**
- Unity: No movement until you write `Update()` + `transform.Translate()` or a CharacterController
- Roblox: WASD/mobile stick moves the character, Space jumps, Humanoid handles it all
- Override when: the game uses custom movement (auto-run, on-rails, grid-based, turn-based, vehicle, etc.)

**Character positioning:**
- Unity: `Transform.position` is set by the scene or by code. No "default spawn."
- Roblox: Spawns at a `SpawnLocation` or the origin
- Override: After anchoring HRP and disabling default movement, set `hrp.CFrame` to the game's starting location. Without this, the avatar floats at the default spawn point.

For each pillar where the Unity game diverges:
- Identify exactly what the Unity code does (e.g., "TrackManager sets character position each frame from a spline curve")
- Decide how to override the Roblox default (e.g., "Anchor HumanoidRootPart, set WalkSpeed=0, drive CFrame from script")
- If too complex to port fully, design a simpler approximation that preserves gameplay feel

**This is a design decision, not a checklist.** Present to the user and ask which approach they want for each pillar.

#### Step 4.5c: Scale & Positioning

Unity uses 1 unit ≈ 1 meter. Roblox avatars are ~5.5 studs tall vs Unity's ~1.8 units. The converter passes positions 1:1 (no scale transform), so the Roblox avatar is ~4x larger than a typical Unity character.

**Decision framework — pick one:**
- **Scale character down** (preferred for dense scene geometry like endless runners): `character:ScaleTo(SCALE)` with `SCALE = unity_character_height / roblox_avatar_height` (typically 0.2–0.3). Also adjust: `laneOffset`, `groundY`, camera offset, road/lane stripe geometry.
- **Scale world up**: Multiply all positions/sizes by a uniform factor. Simpler but requires re-running the converter and may break mesh proportions.
- **Hybrid**: Scale gameplay values without changing visual scale. Quickest hack but produces visual mismatch.

**Implementation for "scale character down":**
1. Measure Unity character height from collider or mesh bounds
2. Compute `SCALE = unity_height / roblox_height`
3. Bootstrap: `character:ScaleTo(SCALE)`, wait `task.wait(0.1)` for physics, then anchor HRP
4. `GROUND_Y = default_hrp_height × SCALE` (e.g., 2.5 × 0.25 = 0.625)
5. Pass `groundY` to character controller; pass Unity's original `laneOffset` to TrackManager
6. Scale camera offset proportionally
7. Scale road/lane stripe widths to match Unity lane geometry
8. **Do NOT scale runtime-spawned content by default.** When the character is scaled down, both the character and the converted world geometry are at Unity scale — the character was the only thing out of proportion. Cloned templates from ReplicatedStorage are already at the correct Unity scale. Scaling them by the character scale factor makes them too small (e.g., a 0.74-stud coin scaled by 0.25 becomes 0.18 studs — nearly invisible). **Only scale spawned content if the Unity game explicitly scales instantiated objects in code**, or if the template dimensions are clearly mismatched with the scene geometry. **`Model:ScaleTo()` only works on Models, not individual BaseParts.** If you do need to scale, use a helper:
   ```lua
   if clone:IsA("Model") then clone:ScaleTo(SCALE)
   elseif clone:IsA("BasePart") then clone.Size = clone.Size * SCALE end
   ```

**Pipeline detail:** Unity stores transforms as local-space. The converter computes world-space positions recursively (`world_pos = parent_pos + parent_rot * local_pos`). If objects cluster at the origin, check `conversion_helpers.py:_compute_world_transform()`.

**Decision point:** Present scale approach. Ask which strategy the user wants.

#### Step 4.5d: Game Loop & Timing Rules

These are universal mechanical rules needed before writing any module code.

**Game loop wiring:**
- Unity implicitly calls `Update()`, `FixedUpdate()`, `LateUpdate()` every frame on all active MonoBehaviours
- Roblox has no implicit per-frame callbacks. A method named `Update()` that isn't connected to anything will never execute.
- **Always override.** Add `RunService.Heartbeat:Connect(function(dt) obj:Update(dt) end)`. Without this, the game appears frozen — no movement, no spawning, no scoring. Disconnect in cleanup paths (`End()`, `OnDisable()`, `Destroy()`).

**Threading / yielding:**
- Unity coroutines (`yield return`) run cooperatively within the main thread. `Update()` never yields.
- Roblox signal callbacks (`Heartbeat:Connect`, `Touched:Connect`) **cannot yield**. `task.wait()` inside a callback silently stops execution — no error, no warning.
- **Rules:** (1) No-yield methods → plain functions. (2) Yielding methods → `task.spawn(function() ... end)`. (3) **Never use `coroutine.wrap` + `task.wait()` together** — `coroutine.wrap` creates a raw Lua coroutine, not a Roblox thread. If the body contains `task.wait()`, it will not resume properly.

**Array indexing (0-based vs 1-based):**
- The transpiler converts access (`arr[i]` → `arr[i + 1]`), but must NOT convert default/initial values of index variables.
- If C# has `usedTheme = 0` and the transpiler changes it to `1`, then `themes[usedTheme + 1]` becomes `themes[2]` — off-by-one returning `nil`.
- **Rule:** Index variables keep their C# value (0-based); the +1 lives only in array subscript expressions.

**Part size limits:**
- Roblox Parts **silently fail to render** if any dimension exceeds 2048 studs. No error, no warning.
- Ground planes, roads, terrain boundaries from Unity often exceed this. Either clamp to 2048 and tile, or use Roblox Terrain.

#### Step 4.5e: Assets, Visibility & Data

**Asset loading (MeshLoader):**
- `MeshId` is read-only at runtime. Meshes must be loaded via `InsertService:LoadAsset(assetId)`. Clone the MeshPart from the loaded Model into the scene.
- The pipeline generates a MeshLoader script that replaces placeholder MeshParts with loaded clones.
- **The bootstrap MUST wait for MeshLoader completion** before entering gameplay. Without this, all cloned objects have placeholder geometry (gray boxes). **Use polling, not `Changed:Wait()`** — the MeshLoader (ServerScript) may set the BoolValue to `true` before the bootstrap (LocalScript) starts listening, causing `Changed:Wait()` to hang forever. Correct pattern:
  ```lua
  local done = ReplicatedStorage:WaitForChild("MeshLoaderDone", 120)
  if done and done:IsA("BoolValue") and not done.Value then
      while not done.Value do task.wait(0.1) end
  end
  ```
- **Skinned meshes** (FBX with bone data from SkinnedMeshRenderer) are invisible as static MeshParts. The pipeline strips skinning data during FBX→GLB conversion. If a mesh is invisible despite correct MeshId/Size/Transparency, check `assimp info <file>.fbx` for `Bones: N > 0`.

**Object visibility:**
- Unity: only GameObjects with MeshRenderer or SkinnedMeshRenderer are visible. Everything else is invisible by design.
- Roblox: every Part is visible by default.
- **Always override.** The pipeline sets `Transparency=1` on objects without a renderer. SpriteRenderer objects (decals, shadows, glow) are 2D overlays — also hidden. Built-in Quad/Plane primitives are almost always effect surfaces and are hidden automatically. Trigger colliders, inactive GameObjects, disabled renderers, and UI subtrees are all handled.
- If opaque gray rectangles block the view: check (1) SpriteRenderer nodes not hidden, (2) Quad/Plane surfaces not hidden, (3) MeshLoader race condition.

**ScriptableObject data:**
- The converter transpiles `.asset` files to `_Data.lua` ModuleScripts, but data still contains raw GUIDs and `nil` placeholders.
- GUIDs must be mapped to Template names in ReplicatedStorage. The data-loading code must find the data modules and be called before game start.

**Database initialization order:**
- If the bootstrap skips UI states (loadout/shop screens), database initialization those states trigger will be missed. Scripts get `nil`.
- The bootstrap must call all `LoadDatabase()` functions explicitly before the game state. Check every singleton's `Create()`/`Init()` for database loading side effects.

**ScreenGui placement:**
- `StarterGui` children are auto-cloned to PlayerGui on every character spawn.
- **Always** place converted ScreenGuis in `ReplicatedStorage` with `Enabled = false`. The state machine parents GUIs to `PlayerGui` when needed. Never place converted UIs in StarterGui.

#### Step 4.5f: Input, Physics & Runtime Content

**Input wiring:**
- Unity polls input via `Input.GetKeyDown()` in `Update()`. No setup required.
- Roblox uses `UserInputService.InputBegan`/`InputEnded` signals. No polling API. The transpiler does NOT create signal connections.
- The bootstrap must connect signals to dispatch input to controller methods (e.g., A/D → `ChangeLane()`, Space → `Jump()`). Map `Input.GetKeyDown(KeyCode.X)` to `Enum.KeyCode.X`. Without this, the game appears frozen to player input.

**Physics:**
- Unity: Rigidbody is opt-in, gravity/collision configured per-object
- Roblox: All parts have physics, character has Humanoid physics with WalkSpeed/JumpPower
- Override when: the game positions objects directly via CFrame/Transform rather than through physics forces

**Runtime content generation:**
- Many Unity games generate content at runtime (procedural levels, spawned obstacles, track segments). The transpiler often strips or stubs spawning logic because it depends on Inspector-serialized prefab references and object pooling.
- After transpilation, verify the core game loop actually spawns content — check for empty `m_Segments` arrays, missing `Instantiate` calls, nil prefab references. This is the **#1 reason** a converted game "runs" (score ticks, character moves) but looks empty.
- Porting pattern: convert prefab templates to Models in ReplicatedStorage/Templates, replace `Instantiate()` with `:Clone()`, resolve ScriptableObject GUIDs to Template names, wire spawning check into Heartbeat. See Step 4.5h for the full spawning system porting guide.

**Decision point:** Present the full divergence analysis (steps 4.5b–f) to the user.

#### Step 4.5g: Animation, Particles & Implementability

1. **Transform animation detection** — Two distinct paths:
   - **Legacy Animation** (classID 111): `.anim` files driving looping transforms (spin, bob, tilt). Auto-generated by `convert_transform_animations()`.
   - **Mecanim Animator on skinned meshes**: Pipeline strips skinning data, searches for animation FBXes (`<Name>_Run.fbx`, `_Walk.fbx`, `_Idle.fbx`, `_Anim.fbx`), extracts Hips bone root motion via `extract_fbx_root_motion()`. Generates `*_RootMotionConfig` ModuleScript. Spawning code checks `HasRootMotion`/`RootMotionConfig` attributes and creates a `TransformAnimator` per clone. The result is a looping bob/sway — not full skeletal animation, but convincing for small fast-moving obstacles.

2. **Particle emission classification** — For each ParticleSystem, determine if it's continuous (ambient) or burst-triggered (collection sparkles, death effects). Burst particles have `rateOverTime ≈ 0` with burst entries (`m_Bursts` array or old-format `cnt0`-`cnt3`). The converter sets burst emitters to `Enabled = false` with a `BurstCount` IntValue. Game scripts must call `emitter:Emit(burstCount)` at the right moment.

3. **Wiring transform animations to spawned content.** The converter auto-generates `*_TransformAnimConfig` ModuleScripts and the `TransformAnimator` bridge module into ReplicatedStorage. But this only provides the data and the runtime engine — the game scripts that **spawn** animated objects must wire them up. After cloning a template that has a corresponding animation config, attach a `TransformAnimator`:
   ```lua
   local TransformAnimator = require(ReplicatedStorage:WaitForChild("TransformAnimator"))
   local MyObjectConfig = require(ReplicatedStorage:WaitForChild("MyObject_TransformAnimConfig"))
   -- After cloning and positioning:
   local animator = TransformAnimator.new(clone, MyObjectConfig)
   -- Store the animator reference for cleanup:
   table.insert(spawnedObjects, { model = clone, animator = animator })
   ```
   On cleanup (object moves behind player), call `animator:Destroy()` before destroying the clone. The TransformAnimator auto-ticks via a shared Heartbeat connection — no per-frame update call needed. **To identify which templates need animation:** check ReplicatedStorage for `*_TransformAnimConfig` modules whose name prefix matches a template name (e.g., `Fishbones_TransformAnimConfig` → template containing "Fishbones" mesh). The config module name comes from the Unity `.anim` file name or the Animation component's GameObject name.

4. **Implementability check** — For each Unity system, assess whether it can be ported as-is or needs simplification. A working simple version beats a broken complex one. If a system cannot be ported fully, implement an approximation and document what's missing.

#### Step 4.5h: Module-per-Component Rewrite

For each major game system, write a **separate Luau module** that mirrors its Unity counterpart:

| Unity class | Roblox module | Bridge modules used |
|---|---|---|
| `GameManager` + `AState` subclasses | State modules + bootstrap wiring via `StateMachine` | `StateMachine` |
| `TrackManager` | `TrackManager.lua` | `GameObjectUtil`, `Time` |
| `CharacterInputController` | `CharacterController.lua` | `Input`, `Physics` |
| Game-specific MonoBehaviours | One module per behaviour | `MonoBehaviour` |
| Legacy Animation on non-skeletal objects (collectibles, power-ups) | Auto-generated `*_TransformAnimConfig` ModuleScript | `TransformAnimator` |
| Mecanim Animator on skinned meshes (animals, characters) | Auto-generated `*_RootMotionConfig` ModuleScript from animation FBX Hips bone | `TransformAnimator` |
| ParticleSystem (burst effects) | ParticleEmitter with `Enabled=false` + `BurstCount` tag | Game scripts call `:Emit()` |

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

   **Critical: `Update()`/`FixedUpdate()` require explicit Heartbeat wiring** — see Step 4.5d.

8. **C# property getters transpiled as function aliases — the silent killer.** C# properties like `public float speed { get { return _speed; } }` get transpiled as a getter method (`getSpeed()`) plus a class-level alias: `MyClass.speed = MyClass.getSpeed`. This makes `instance.speed` return the *function itself*, not the value. **This must be applied to EVERY class with properties, not just the main class.** If ClassA has `__index` metamethods but ClassB (used by ClassA) doesn't, `classB.worldLength` returns nil even though `getWorldLength()` exists. Every property-style access silently returns a truthy function reference instead of the actual data. This causes cascading failures:
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

9. **Inspector-serialized ScriptableObject references are nil at runtime.** In Unity, a MonoBehaviour field like `public ThemeData tutorialThemeData` is populated by dragging a ScriptableObject asset onto it in the Inspector. At runtime, the field has a valid reference. In Roblox, the transpiler converts this to `self.tutorialThemeData = config.tutorialThemeData` — but the config never has this value because there's no Inspector. The field stays nil, and any code path that reads it crashes. **Fix:** For data references that point to ScriptableObjects now converted to `_Data` ModuleScripts, wire them through the database lookup: `self.tutorialThemeData = ThemeDatabase.GetThemeData("Tutorial")`. For Inspector refs to prefabs/GameObjects, resolve through the Templates folder in ReplicatedStorage. The bootstrap or the module constructor must do this wiring — the transpiler cannot, because the mapping from GUID to name requires the scene file.

10. **State-managed scene objects require explicit wiring.** Unity state machines (e.g., `LoadoutState`/`GameState`) toggle scene objects' visibility as part of state transitions — a menu backdrop is shown during the loadout screen and hidden when gameplay starts. These scene object references come from Inspector serialization (`public GameObject menuEnvironment`), so they're nil in Roblox. Unlike data references (#9), these are **3D objects already in workspace** that need to be found by name and passed through config. **Fix:** The bootstrap must `workspace:FindFirstChild("ObjectName")` for each state-managed scene object and pass it to the state's config table. The state's `Enter()`/`Exit()` calls `GameObjectUtil.SetActive(obj, true/false)` which toggles `Transparency` and `CanCollide` — the object stays in workspace, never gets reparented. **Never use `obj.Parent = nil` to hide objects** — this nulls the parent and causes cascading errors when other code reads `.Parent`. To identify which objects need wiring: look for `public GameObject` fields on state classes that aren't prefabs or UI — they're scene environment objects toggled by `SetActive(true/false)` in `Enter()`/`Exit()`.

11. **SetActive must use GameObjectUtil, never Parent assignment.** Unity's `GameObject.SetActive(bool)` toggles visibility. The transpiler must convert `obj.SetActive(false)` → `GameObjectUtil.SetActive(obj, false)`, which sets `Transparency=1` and `CanCollide=false`. **Never emit** `obj.Parent = nil` or `obj.Parent = ReplicatedStorage` as a visibility toggle — this detaches the object from the scene tree, and any subsequent code that reads `obj.Parent` (including the MeshLoader replacement pattern) gets nil, causing silent failures or crashes. The bridge module `GameObjectUtil` must be required at the top of any module that calls SetActive.

**Timing model preservation:**
- If Unity uses `trackManager.worldDistance` to measure jump/slide progress, the Roblox port must too
- If Unity scales durations by `(1 + speedRatio)`, the Roblox port must too
- Do NOT simplify world-distance timing into time-based timing — it changes gameplay feel

**Porting procedural content / runtime spawning systems:**

Many Unity games generate gameplay content at runtime — spawned enemies, level chunks, projectile pools, procedural terrain, collectible placements. This is the #1 system that **does not survive transpilation** because it depends on Inspector-serialized prefab references, Addressables async loading, and object pooling — none of which have Roblox equivalents. The transpiled code keeps the scoring/movement logic but the spawning methods become empty shells with nil references.

**Why it breaks:** Prefab references are Inspector-serialized AssetReferences or Addressable keys (nil in Roblox). Object pooling libraries are not transpiled. ScriptableObject data that maps themes/levels to prefab lists contains raw GUIDs. The transpiled manager keeps `Update()` ticking but spawn methods have zero functional code.

**What spatial data does NOT survive conversion:**
- **Path/spline data** (child Transforms defining waypoints or curves) — the converter strips non-rendered objects (`Transparency=1, CanCollide=false`). If the Unity game uses child Transforms as waypoints for movement paths, those waypoints become invisible anchored Parts with no distinguishing features. **Do not write auto-discovery code** that walks a Model's children looking for waypoints — it will find rendering geometry instead.
- **Normalized position values** (e.g., obstacle spawn positions stored as 0–1 t-values along a path) — these only make sense with the original path geometry. If the path is lost, these values are meaningless.
- **Collider-only geometry** (trigger volumes, invisible walls) — stripped or made transparent. If gameplay depends on trigger placement within prefabs, that spatial data must be manually extracted.

**What DOES survive:**
- **Template Models** in ReplicatedStorage/Templates preserve their Unity prefab names and visible mesh hierarchy. The converter names them from the prefab's root GameObject name.
- **UnityLayer attributes** set by the converter on Parts (e.g., layer 8 for collectibles, layer 9 for obstacles). Use `part:GetAttribute("UnityLayer")` for collision classification — do NOT invent custom tagging systems (BoolValues, CollectionService tags) that duplicate what the converter already provides.
- **ScriptableObject data** converted to `_Data.lua` ModuleScripts — but contains raw GUIDs that must be resolved to Template names.

**Porting pattern:**

1. **Identify templates.** The pipeline produces Models in `ReplicatedStorage/Templates` from Unity prefabs. Each Model keeps its Unity prefab name. **Never auto-discover templates** by scanning for child structure patterns or name substrings — use the known prefab names from the Unity project. Build a lookup table mapping names (or Unity GUIDs from the data modules) to template references.

2. **Extract per-template metadata from Unity prefab YAML.** Read `.prefab` files to determine: template dimensions/length, sub-object spawn positions, which sub-templates can appear within a template. Hardcode this metadata in a Luau table — it cannot be derived at runtime because the spatial data (waypoints, normalized positions) is lost during conversion.

3. **Write spawn logic that `:Clone()`s templates** and positions them in world space. Replace Unity's `Instantiate()` with `:Clone()` + `Parent = workspace`. Resolve ScriptableObject GUID references to Template names (see semantic gap #9).

4. **Implement cleanup.** When spawned content moves past a threshold distance from the player, `:Destroy()` it. No need to port Unity's object pooling — Roblox's instance creation is fast enough. If the clone has a `TransformAnimator`, call `animator:Destroy()` before destroying the clone to unregister from the shared Heartbeat.

   **Wire transform animations on spawned clones.** Check ReplicatedStorage for `*_TransformAnimConfig` modules that match template names (see Step 4.5g item 3). After cloning and positioning a template, attach a `TransformAnimator.new(clone, config)`. Without this, converted collectibles and obstacles that had spin/bob/tilt animations in Unity will be static in Roblox.

5. **Wire into the game loop.** Spawning checks must run every frame via the Heartbeat connection, not as a one-time setup.

6. **Create ground/environment surfaces explicitly if needed.** Unity games often have invisible ground planes, procedurally generated floors, or terrain that doesn't convert as renderable geometry. If the game world appears to have no floor, create a simple Part as a ground surface. But only do this when the Unity game's ground is genuinely missing — if Unity generates ground at runtime, port the generation system rather than substituting a static surface.

**Movement model — account for lost spatial data:**
- If Unity moves objects along spline paths (waypoints as child Transforms), those waypoints are lost. Determine the *effective* movement from the Unity code: is it straight-line, curved, grid-based? Port the effective movement, not the spline interpolation mechanism.
- If Unity uses path interpolation (`GetPointAt(t)`) but the path is a straight line, replace with direct position arithmetic. If the path is genuinely curved, the curve control points must be manually extracted and hardcoded.

**Movement direction — match the converter's coordinate system:**
- The converter places objects at their Unity world positions with 1:1 coordinate mapping. Unity's forward axis is +Z. The converter preserves this, so converted scene objects are arranged along +Z.
- The game loop's movement direction **must match** the axis the converted objects are placed along. If the converter placed track segments at increasing +Z positions, the character must move in the +Z direction — not -Z.
- **Character facing:** If the character should face +Z (forward in Unity), set `CFrame.Angles(0, math.pi, 0)` since Roblox's default front face is -Z.
- **Camera placement:** Use absolute world-space offsets (e.g., `characterPos + Vector3.new(0, height, -behindDistance)`) rather than rotation-relative offsets (e.g., `charCF.LookVector * distance`). Rotation-relative offsets break when the character has a fixed facing rotation, because the LookVector points in the character's local forward — which may be opposite to the world movement direction.

**Diagnostic:** If a converted game "runs" (score increments, character animates) but the world is empty — no spawned content, no obstacles, no collectibles — the spawning system was not ported. Check the manager's spawn arrays: if they stay empty, spawning is broken.

#### Step 4.5i: Bootstrap Wiring

Write a `GameBootstrap.lua` (LocalScript in StarterPlayerScripts) that:
- Creates instances of each module — **always pass `{}` even if no config is needed** (constructors expect a table, not nil)
- Wires cross-references **after** construction (same as Unity's Inspector references — components are created first, then linked)
- Registers states with the StateMachine bridge
- Starts the state machine with the initial state
- Does NOT contain game logic — it's pure wiring
- To determine what to wire: read the `.unity` scene file for serialized field references (e.g., `characterController: {fileID: XXXX}` tells you TrackManager needs a reference to CharacterInputController)
- **Uses the player's Roblox avatar** as the game character when appropriate (e.g., endless runners, platformers). Wait for `player.Character`, get `HumanoidRootPart`, disable default movement (`WalkSpeed=0`, `JumpPower=0`, `JumpHeight=0`). If Step 4.5c chose "scale character down", call `character:ScaleTo(SCALE)` **before** anchoring (scaling requires a brief physics settle — `task.wait(0.1)` after scaling). **Never call `Humanoid:ApplyDescription()` or `Humanoid:ApplyDescriptionReset()` from a LocalScript** — these are server-only APIs and will error on the client, crashing the bootstrap. Then anchor HRP, set initial `CFrame` using the computed `GROUND_Y`, and pass both `transform` and `groundY` to the character controller. Only create a placeholder Part if the game uses a non-humanoid avatar.
- **Wires input** via `UserInputService.InputBegan` — the transpiler does NOT create input bindings. Map Unity's `Input.GetKeyDown` keycodes to Roblox `Enum.KeyCode` and dispatch to controller methods (`ChangeLane`, `Jump`, `Slide`, etc.).
- **Wires collision signals** for any module that defines `OnTriggerEnter`, `OnTriggerExit`, `OnCollisionEnter`, or `OnCollisionExit`. Unity's engine calls these implicitly on any MonoBehaviour attached to a GameObject with a collider. Roblox requires explicit collision wiring. **Choose the right mechanism based on how the part moves:**
  - **Physics-driven parts** (unanchored, moved by forces): use `.Touched`/`.TouchEnded` signals.
  - **CFrame-driven parts** (anchored, moved by setting CFrame each frame): `.Touched` is **unreliable** — Roblox's physics engine doesn't fire touch events for parts moved via CFrame. Use `workspace:GetPartsInPart(part, overlapParams)` in a per-frame `Heartbeat` loop instead. This is the common case for converted games where the character controller directly sets position.

  For the per-frame overlap pattern, use an `alreadyHit` set to prevent duplicate triggers per object, and filter out the character's own parts via `OverlapParams.FilterDescendantsInstances`. **Skip fully transparent parts** (`Transparency >= 1.0`) — Unity obstacle prefabs contain shadow planes and invisible collision boxes that don't have colliders in Unity, but `GetPartsInPart` picks them up in Roblox. Without this filter, the player takes damage from invisible geometry. **The bootstrap only wires the signal — the transpiled method decides what to do.** Never add game-specific collision filtering in the bootstrap.

**Scene object classification — menu vs gameplay environment.**
Unity scenes contain objects meant for different contexts: menu backgrounds, editor-only preview instances, and gameplay environment (road-side buildings, terrain). The converter places ALL scene objects into Workspace, but only gameplay environment objects should remain visible during gameplay.

- **Menu/UI scene objects** (e.g., title screen backdrops, menu cameras, character preview platforms): hide by setting `Transparency=1, CanCollide=false` on all descendant BaseParts. Identify these by name patterns from the Unity scene hierarchy — they often contain "Menu", "UI", "Background", "Title" in their name. Read the Unity scene YAML to confirm which root GameObjects are menu-only.
- **Editor preview instances** (prefab instances placed in the scene for the developer to see in the editor, but spawned dynamically at runtime): hide these too. Common pattern: a single instance of a collectible prefab (e.g., "Pickup") placed at the origin — this is a preview, not gameplay content.
- **Gameplay environment** (buildings, terrain, decorations along the play area): keep visible. These form the visual backdrop of the game.
- **Broken visual artifacts** (objects that render as white boxes or gray rectangles in Roblox due to missing textures, failed mesh loading, or stripped effects like LightCones/Glow planes): remove from both Workspace and Templates to prevent them from appearing in spawned segments.

The bootstrap should handle cleanup by name — iterate over known menu object names and hide them, rather than using broad pattern matching that might catch gameplay objects.

**Module export unwrapping — CRITICAL.** The transpiler is inconsistent about how modules export their classes. Some return the class directly (`return MyClass`), others wrap it in a table (`return { MyClass = MyClass, SomeEnum = SomeEnum }`). The bootstrap **must not assume** which style a module uses. Before writing `require()` calls, inspect each module's `return` statement. Use a defensive unwrap helper:

```lua
local function unwrap(mod, name)
    if type(mod) == "table" and mod[name] then return mod[name] end
    return mod
end

local SomeModule = unwrap(require(ReplicatedStorage:WaitForChild("SomeModule")), "SomeModule")
```

Why: if you write `local Foo = require(...)` and the module returns `{ Foo = Foo }`, then `Foo.new()` calls the wrapper table (which has no `.new`), producing "attempt to call a nil value". This is silent until runtime and affects every module whose return style doesn't match the bootstrap's assumption.

**Implement the platform divergence decisions from Steps 4.5b–f.** For each pillar where the Unity game diverges from Roblox's defaults, the bootstrap must apply the appropriate override. Apply the scale conversion decision from Step 4.5c.

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
