# Convert Unity Project to Roblox

An interactive skill that guides the conversion of a Unity game project into a Roblox place (.rbxl). The conversion is non-linear — it requires human decisions at multiple checkpoints.

## Invocation

User-invocable: yes

## Instructions

You are orchestrating the Unity → Roblox game converter. This is a multi-phase pipeline where each phase may surface issues that need human judgment. Do NOT run the entire pipeline blindly — pause at each decision point and present findings to the user.

### Overview of Phases

1. **Discovery** — Scan the Unity project, parse scenes and prefabs
2. **Asset Inventory** — Catalog assets and resolve GUIDs
3. **Material Mapping** — Convert Unity materials to Roblox equivalents
4. **Code Transpilation** — Convert C# scripts to Luau
5. **Assembly** — Build the .rbxl file
6. **Upload** (optional) — Push to Roblox Cloud

### Step-by-step Workflow

#### Step 0: Gather Inputs

Ask the user for:
- The path to the Unity project (the folder containing `Assets/`, `ProjectSettings/`, etc.)
- The desired output directory for the Roblox files
- Whether they want AI-assisted C# → Luau transpilation (requires Anthropic API key)

If the user provided these as arguments (e.g. `/convert-unity ./MyGame ./output`), parse them from the args instead of asking.

Validate that the Unity project path exists and contains an `Assets/` directory. If not, report the issue and ask the user to correct it.

#### Step 1: Discovery — Parse Scenes & Prefabs

Run Phase 1 of the pipeline using `convert_interactive.py`:

```bash
cd <project-root> && python convert_interactive.py discover <unity_project_path>
```

This outputs a JSON summary to stdout. Present the results to the user:
- Number of scenes found and their names
- Number of prefabs found
- Number of material GUIDs referenced
- Any parse errors encountered

**Decision point:** If there are multiple scenes, ask which scenes to include. If there are parse errors, ask if the user wants to continue or investigate.

#### Step 2: Asset Inventory & GUID Resolution

```bash
python convert_interactive.py inventory <unity_project_path>
```

Present results:
- Total assets found, broken down by type (textures, meshes, audio, etc.)
- Total size
- GUID resolution stats (resolved, duplicates, orphans)

**Decision point:** If there are duplicate GUIDs or orphan .meta files, warn the user and ask how to proceed. If the project is very large, confirm they want to continue with full conversion.

#### Step 3: Material Mapping

```bash
python convert_interactive.py materials <unity_project_path> <output_dir> [--referenced-guids <comma-separated-guids>]
```

Present results:
- Total materials processed
- How many fully converted, partially converted, and unconvertible
- Texture operations performed
- If an UNCONVERTED.md was generated, read and summarize it for the user

**Decision point:** If there are unconvertible materials or partial conversions, present the specifics and ask the user:
- Accept as-is and continue?
- Want to provide manual mappings for specific materials?
- Skip certain materials entirely?

#### Step 4: Code Transpilation

```bash
python convert_interactive.py transpile <unity_project_path> [--use-ai] [--api-key <key>]
```

Present results:
- Total scripts found
- How many succeeded vs flagged for review
- Strategy used (AI vs rule-based) per script

**Decision point — this is the most interactive step:**
- For each flagged script (low confidence), show the user:
  - The original C# source (abbreviated if long)
  - The generated Luau code
  - The specific warnings/issues
  - Ask: Accept, Retry with AI, Edit manually, or Skip?
- If there are many flagged scripts (>5), offer a batch option: "Accept all", "Skip all flagged", or "Review one by one"
- For scripts with residual C# patterns (class keywords, curly braces), highlight these as needing attention

After the user reviews flagged scripts, run Luau validation:
```bash
python convert_interactive.py validate <output_dir>
```

Report validation errors and let the user decide how to handle them.

#### Step 5: Assembly — Build .rbxl

```bash
python convert_interactive.py assemble <unity_project_path> <output_dir> [--decimate] [--state-file <path>]
```

Present results:
- Number of parts written
- Number of scripts embedded
- Output file path and size
- Any warnings from the writer

**Decision point:** If mesh decimation was enabled and some meshes were significantly reduced or skipped, present the details and ask if the user wants to adjust quality settings and re-run.

#### Step 6: Upload (Optional)

Ask the user if they want to upload to Roblox Cloud. If yes, they need:
- Roblox Open Cloud API key (with `asset:read`, `asset:write`, and `place:write` scopes)
- Universe ID
- Place ID
- Creator ID (their Roblox user ID or group ID)

The upload step handles three asset categories:

1. **Sprites/Images** — Sliced sprite PNGs from `<output_dir>/sprites/` are uploaded as Decal assets
2. **Audio** — Audio files from `<output_dir>/audio/` are uploaded as Audio assets
3. **Place file** — The .rbxl is uploaded to the specified place

**Important:** Sprites and audio must be uploaded *before* the place file, because the .rbxl needs to be patched with the resulting `rbxassetid://` URLs.

```bash
python convert_interactive.py upload <output_dir> [--roblox-api-key <key>] [--universe-id <id>] [--place-id <id>] [--creator-id <id>] [--creator-type User|Group]
```

Present results:
- Number of sprites uploaded and their asset IDs
- Number of audio files uploaded and their asset IDs
- Whether the .rbxl was patched with the new asset IDs
- Place upload success/failure and version number

**Decision point:** If some asset uploads fail (rate limits, size limits, format issues), ask the user:
- Retry failed uploads?
- Continue without those assets (they'll show as placeholder in-game)?
- Abort and fix the issues first?

After a successful upload, the .rbxl in the output directory will have been rewritten with real `rbxassetid://` URLs, so the user can also open it in Roblox Studio with working references.

#### Step 7: Final Report

```bash
python convert_interactive.py report <output_dir>
```

Read the generated report and present a summary to the user. Highlight:
- Overall success/failure
- Key metrics (assets, materials, scripts, parts)
- Any remaining warnings or errors
- Suggestions for manual follow-up (flagged scripts, unconverted materials)

### Error Handling

- If any phase command fails, show the error to the user and ask how to proceed
- Offer to retry, skip the phase, or abort the conversion
- Never silently swallow errors — every issue is a potential decision point

### State Management

The interactive pipeline writes intermediate state to `<output_dir>/.convert_state.json`. This allows:
- Resuming a partially completed conversion
- Re-running individual phases with different settings
- If state exists from a previous run, ask the user if they want to resume or start fresh

### Tips for the Operator (Claude)

- Be concise in summaries but thorough when presenting decision points
- When showing code (C# or Luau), use fenced code blocks with language tags
- For large lists (many materials, many scripts), summarize counts first, then offer to drill into specifics
- Remember the user's earlier decisions — if they said "accept all partial materials", don't re-ask for the same category
- If the Unity project is a well-known game template (e.g., Trash Dash), mention that you recognize it and highlight known conversion considerations from the docs
