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
python3 convert_interactive.py transpile <unity_project_path> <output_dir> [--use-ai --api-key <key>] [--no-ai] 2>/dev/null
```

Handle structured errors: `"insufficient_credits"` / `"auth_failure"` — don't retry, offer `--no-ai`. If `"batch_review_suggested": true`, offer batch options.

**Decision point:** For each flagged script, show C# and Luau side-by-side. Ask: Accept, Retry with AI, Edit manually, or Skip?

After review, validate: `python3 convert_interactive.py validate <output_dir> 2>/dev/null`

### Step 4.5: Game Logic Porting (LLM Rewrite)

After transpilation, the rule-based output is syntactically correct but architecturally wrong — it translates line-by-line without understanding game patterns. This step uses the LLM (you) to produce game-specific scripts that preserve the original Unity game's architecture.

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

   For each pillar where the Unity game diverges from Roblox's default:
   - Identify exactly what the Unity code does (e.g., "TrackManager sets character position each frame from a spline curve")
   - Decide how to override the Roblox default (e.g., "Anchor HumanoidRootPart, set WalkSpeed=0, drive CFrame from script")
   - If the Unity system is too complex to port fully, design a simpler approximation that preserves the gameplay feel

   **This is a design decision, not a checklist.** Present the divergence table to the user and ask which approach they want for each pillar.

5. **Scale conversion** — Unity uses 1 unit ≈ 1 meter. Roblox characters are ~5.5 studs tall vs Unity's ~1.8 units. Determine the scale relationship between the imported scene geometry and Roblox's defaults, and decide whether to scale the world up, scale the character down, or apply a conversion factor to gameplay values. Present the tradeoffs to the user.

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

**Timing model preservation:**
- If Unity uses `trackManager.worldDistance` to measure jump/slide progress, the Roblox port must too
- If Unity scales durations by `(1 + speedRatio)`, the Roblox port must too
- Do NOT simplify world-distance timing into time-based timing — it changes gameplay feel

#### Phase C: Bootstrap Wiring

Write a `GameBootstrap.lua` (LocalScript in StarterPlayerScripts) that:
- Creates instances of each module
- Wires cross-references (same as Unity's Inspector references)
- Registers states with the StateMachine bridge
- Starts the state machine with the initial state
- Does NOT contain game logic — it's pure wiring

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

#### Key principles

- **Architecture preservation over code translation** — the goal is a Roblox game that is wired the same way the Unity game was, not a line-by-line translation
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
