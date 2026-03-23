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

4. **Movement model** — How does the character move?
   - Does the world move and the character stays still? (common in endless runners)
   - Does the character move through a static world?
   - Does the TrackManager compute position from track segment curves?
   - Lane changes: smooth interpolation via `MoveTowards` or lerp?

**Decision point:** Present the architecture map to the user. Ask: "Does this match your understanding of the game? Any systems I'm missing or misreading?"

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

Example pattern:
```lua
local SM = require(ReplicatedStorage.UnityBridge.StateMachine)
local manager = SM.new()

-- Create components (mirrors Unity Inspector wiring)
local trackManager = TrackManager.new(trackConfig)
local charController = CharacterController.new(charConfig)
charController.trackManager = trackManager
trackManager.characterController = charController

-- Register states (mirrors GameManager.states array)
manager:AddState("Loadout", LoadoutState.new(trackManager))
manager:AddState("Game", GameState.new(trackManager, charController, ui))
manager:AddState("GameOver", GameOverState.new(trackManager))

manager:Start("Loadout")
```

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
