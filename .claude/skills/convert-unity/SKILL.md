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
