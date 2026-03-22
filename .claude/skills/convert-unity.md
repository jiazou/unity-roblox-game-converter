# Convert Unity Project to Roblox

An interactive skill that guides the conversion of a Unity game project into a Roblox place (.rbxl). The conversion is non-linear — it requires human decisions at multiple checkpoints.

## Invocation

User-invocable: yes

## Instructions

You are orchestrating the Unity → Roblox game converter. This is a multi-phase pipeline where each phase may surface issues that need human judgment. Do NOT run the entire pipeline blindly — pause at each decision point and present findings to the user.

All commands output structured JSON to stdout. Redirect stderr (`2>/dev/null`) to keep output clean.

### Step-by-step Workflow

#### Step 0: Gather Inputs & Preflight

Ask the user for:
- The path to the Unity project (the folder containing `Assets/`, `ProjectSettings/`, etc.)
- The desired output directory for the Roblox files
- Whether they want AI-assisted C# → Luau transpilation (requires Anthropic API key)

If the user provided these as arguments (e.g. `/convert-unity ./MyGame ./output`), parse them from the args instead of asking.

Run preflight to validate the project and install dependencies:
```bash
python3 convert_interactive.py preflight <unity_project_path> <output_dir> --install 2>/dev/null
```
This checks Python version, installs missing packages, and validates the Unity project path. If `success` is false, report the issues to the user before continuing.

If resuming a previous conversion, check state:
```bash
python3 convert_interactive.py status <output_dir> 2>/dev/null
```
If `resumable` is true, tell the user which phases are complete and offer to resume from `next_phase`.

#### Step 1: Discovery — Parse Scenes & Prefabs

```bash
python3 convert_interactive.py discover <unity_project_path> <output_dir> 2>/dev/null
```

Present: scene count/names, prefab count, material GUIDs, parse errors.

**Decision point:** If multiple scenes, ask which to include. If parse errors, ask whether to continue.

#### Step 2: Asset Inventory & GUID Resolution

```bash
python3 convert_interactive.py inventory <unity_project_path> <output_dir> 2>/dev/null
```

Present: asset breakdown by type, total size, GUID resolution stats.

**Decision point:** If duplicate GUIDs or orphans, warn and ask how to proceed.

#### Step 3: Material Mapping

```bash
python3 convert_interactive.py materials <unity_project_path> <output_dir> 2>/dev/null
```

Present: conversion stats, unconvertible materials, texture operations. If UNCONVERTED.md was generated, read and summarize it.

**Decision point:** For unconvertible/partial materials, ask: accept as-is, provide manual mappings, or skip?

#### Step 4: Code Transpilation

```bash
python3 convert_interactive.py transpile <unity_project_path> <output_dir> [--use-ai --api-key <key>] [--no-ai] 2>/dev/null
```

Always prefer `--use-ai` when the user has a funded Anthropic API key.

The output JSON includes structured error detection:
- `"error_type": "insufficient_credits"` or `"auth_failure"` — do NOT retry the same key. Inform the user and offer `--no-ai`.
- `"batch_review_suggested": true` — offer batch options ("Accept all", "Skip all", "Review one by one") instead of reviewing each script individually.

**Decision point — this is the most interactive step:**
- For each flagged script (low confidence), show the original C# and generated Luau side-by-side, plus warnings. Ask: Accept, Retry with AI, Edit manually, or Skip?

After review, run validation:
```bash
python3 convert_interactive.py validate <output_dir> 2>/dev/null
```

Report validation errors. The validator is context-aware — it only flags C#-style block braces, not Luau table constructors.

#### Step 5: Assembly — Build .rbxl

```bash
python3 convert_interactive.py assemble <unity_project_path> <output_dir> [--preview-mode] [--no-preview-mode] 2>/dev/null
```

The assembly phase:
- Converts scene nodes to Roblox Parts/MeshParts
- Generates prefab packages and embeds them in ServerStorage (enabled by default)
- Builds a `mesh_texture_map` linking mesh IDs to texture filenames for the upload patcher
- **Preview mode** (on by default): copies all prefabs from ServerStorage into Workspace, disables scripts and ScreenGuis. This makes the converted place immediately viewable in Roblox Studio without requiring working game logic. Use `--no-preview-mode` for production output where scripts manage the scene.

Present: parts written, scripts embedded, packages generated, preview info, file size, warnings.

**Decision point:** If mesh decimation was enabled and meshes were significantly reduced, ask about quality adjustment.

#### Step 6: Upload (Optional)

Ask the user if they want to upload to Roblox Cloud. If yes, they need:
- Roblox Open Cloud API key (with `asset:read`, `asset:write`, and `place:write` scopes)
- Universe ID and Place ID (must already exist)
- Creator ID or username

```bash
python3 convert_interactive.py upload <output_dir> \
  --roblox-api-key <key> --universe-id <id> --place-id <id> \
  [--creator-id <id> | --creator-username <username>] \
  [--creator-type User|Group] 2>/dev/null
```

The upload command handles everything automatically:
1. Uploads textures, sprites, and audio (polls async operations for asset IDs)
2. Patches the .rbxl with `rbxassetid://` URLs using four strategies:
   - Replaces `rbxassetid://` placeholders and `-- TODO: upload` comments
   - Replaces local filesystem paths by matching filenames
   - Replaces bare texture filenames in SurfaceAppearance ColorMap values (e.g. `BrickWall_color.png` → `rbxassetid://12345`)
   - Injects new SurfaceAppearance on MeshParts by scanning Unity project for mesh→material relationships
3. Converts XML to binary .rbxl format
4. Uploads the place file

The output JSON includes structured error types:
- `"error_type": "place_not_published"` — the user must open Roblox Studio, open the place, and publish an initial version before the API can accept uploads.

**Decision point:** If some uploads fail, ask: retry, continue without those assets, or abort?

#### Step 7: Final Report

```bash
python3 convert_interactive.py report <output_dir> 2>/dev/null
```

Present: overall success, key metrics, remaining warnings, manual follow-up suggestions.

### Error Handling

- If any phase fails, show the error and ask how to proceed (retry, skip, abort)
- Never silently swallow errors — every issue is a potential decision point

### Tips for the Operator (Claude)

- Be concise in summaries but thorough at decision points
- Use fenced code blocks with language tags when showing C# or Luau
- For large lists, summarize counts first, then offer to drill into specifics
- Remember earlier decisions — don't re-ask for the same category
- If the Unity project is a well-known template (e.g., Trash Dash), mention known conversion considerations
