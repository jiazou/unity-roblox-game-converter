# SKILL.md Refactor Proposal (v2)

**Status:** Proposal only — do not implement yet.

**Change from v1:** deeper analysis of the fragmentation risk surfaced several concrete mitigations that reshape the layout. Notably, Step 4.5 now splits into **6 files instead of 10** because certain topics (modules + bootstrap; divergence + scale) are always co-read and splitting them just forces two Reads where one suffices. The v2 layout also adds a machine-checkable validation plan, a house style guide, and explicit cross-reference rules.

## Problem

`SKILL.md` is 581 lines / ~60KB. It exceeds the Read tool's 10K-token single-read limit and consumes a large chunk of context whenever the skill is invoked, even for phases that only touch a narrow topic. In practice, the file gets compaction-truncated mid-conversation, so the agent loses critical guidance at exactly the phases where it's needed.

Secondary problem: the file has accumulated game-specific lore from the Trash Dash and SimpleFPS conversions (endless-runner lane offsets, `IndustrialWarehouse01`, `LoadoutState`, `tutorialThemeData`, `WeaponSlot`, `UpdateSpawnpoint`, etc.). These are concrete and useful, but they belong in examples, not in a general-purpose skill file.

## Goals

1. **Thin orchestrator.** The always-loaded `SKILL.md` is ~150 lines. It contains the phase workflow, the universal safety rules, and one-line teasers for each phase that the agent will see even if it skips the follow-up Read.
2. **Phase-local context.** Each phase loads only the reference material it actually needs. A phase-3 decision does not drag in 200 lines of bootstrap guidance.
3. **Topic isolation inside Step 4.5** — but not so granular that always-co-loaded topics force two Reads where one suffices.
4. **Game-agnostic reference docs.** Trash Dash / SimpleFPS specifics move to `references/examples/` and are referenced by targeted pointers, never bare "see examples/".
5. **Stable rules load eagerly.** Universal rules (visibility, Heartbeat, yielding, size limits, ScreenGui placement) live inline in `SKILL.md`. An agent that jumps phases still sees them.
6. **Failure-mode friendly.** When the agent hits a symptom (invisible mesh, nil method call, empty spawn array), it must be able to find the relevant rule in ≤2 Reads — via symptom indexes in the largest reference files.

## Non-goals

- Changing the conversion workflow or decision points.
- Changing `convert_interactive.py`.
- Deleting guidance. Every rule currently in `SKILL.md` lands somewhere in the new layout.
- Renaming the skill or changing how it is invoked.

---

## Deep dive: the 5 original risks + mitigations

### Risk 1: Fragmentation — the agent skips the Read directive

**The core threat.** If the agent reads `SKILL.md`, sees "Read `references/phase-3-materials.md` before proceeding", and skips it (for optimism, context-budget, or because the line got compacted), it has **strictly less context than today**. The refactor net-regresses.

Why an agent might skip:
- Optimism: "I know material mapping, I don't need 50 more lines."
- Invisible truncation: the phase directive was after a long command block and got lost.
- Implicit invocation: the skill is triggered mid-conversation from another task and the agent never re-reads SKILL.md.
- Nested calls: sub-agents inherit instructions but may not re-Read phase files.

**Mitigations:**

1. **Strong imperative language** on every phase stub. Not "Read X for details" (skippable) but:

   > **Before running the command below, `Read references/phase-3-materials.md`. Do not skip this — the decision points live there, not in this file.**

   This is the single biggest lever. Phrasing matters.

2. **One-line teasers for every phase.** In `SKILL.md`, every phase stub includes the single most critical rule as a one-liner, so that even if the Read is skipped, the agent has the anchor. For phase 3:

   > *Teaser:* SurfaceAppearance without a ColorMap makes the part white — only create it when `rdef.color_map` is present.

   The teaser is a compression loss, not a replacement. Its job is "be better than nothing" and to signal what kind of rules live behind the Read.

3. **Post-phase self-check.** At the end of each phase stub: "If you did not Read the phase reference, stop and do it before reporting results." Cheap, and the self-reference creates a second opportunity to catch the skip.

4. **Pinned line in SKILL.md intro.** First sentence under the workflow header:

   > For every phase, you MUST Read its reference file before taking action. Skipping the Read is a process violation, not an optimization.

5. **Acceptance test** (see Validation Plan below). After the refactor, we run `/convert-unity` on a known project and grep the tool-call transcript to verify the agent issued a `Read` on each expected phase file. If it skipped any, the language or structure is not strong enough and we iterate.

Combined, these mitigations should drive skip rate near zero. The teasers are the safety net if any skip slips through.

### Risk 2: `transpiler-gaps.md` is dense (~80 lines, 11 numbered items)

**Re-examining the 11 gaps** reveals they cluster into 3 groups:

- **Wiring gaps (construction/references):** #1 MonoBehaviour lifecycle, #9 ScriptableObject refs nil, #10 state-managed scene objects, #11 SetActive must use GameObjectUtil. These are "Unity Inspector did this, Luau must do it explicitly."
- **Property/accessor gaps:** #2 C# properties, #6 singleton accessor functions, #8 the silent-killer getter aliases. These are "C# → Luau syntax mismatch that silently returns functions instead of values."
- **API surface gaps:** #3 binary serialization, #4 cross-module exports, #5 GetComponent on clones, #7 lifecycle method table. These are "C# framework APIs have no Luau equivalent."

**Mitigations:**

1. **Regroup the file by cluster**, not by original numbering. Three subsections, each ~25 lines, each with its own heading so the agent can jump to the relevant cluster.

2. **Add a symptom index at the top of the file.** This turns it from a linear read into a debugging lookup:

   ```
   | Symptom | Section |
   |---|---|
   | "attempt to call a nil value" on a method | Wiring §1, §7 |
   | "attempt to get length of a function" | Properties §8 |
   | "attempt to perform arithmetic on a function" | Properties §8 |
   | Data reference unexpectedly nil | Wiring §9 |
   | Object vanishes after SetActive(false) | Wiring §11 |
   | Module export is nil at require site | API §4 |
   | Singleton returns a function, not the instance | Properties §6 |
   | Update() never fires | §7 (cross-ref phase-4.5-universal-rules) |
   ```

   With this, an agent debugging a specific error reads the table, jumps to the section, resolves the bug in 15 lines instead of 80.

3. **Do not split into 3 files.** Splitting would mean 3 Reads during module debugging instead of 1, and the clusters frequently cross-reference each other (a property problem often surfaces as a wiring problem). Keep as one file, navigable.

### Risk 3: Cross-references become cross-file

Current `SKILL.md` has many inline "see 4.5c" / "see 4.5g" references. After the split, these become pointers to other files. Naive conversion introduces two failures:

a) **Dangling reference.** "See `phase-4.5-scale.md`" — the reader doesn't know if that's essential or optional context, and may or may not Read it.
b) **Reference explosion.** If every topic file links to 3 others, a single phase can chain-load 5+ files before the agent has context to act.

**Mitigations:**

1. **Cross-reference policy: never a bare pointer.** Every cross-reference must include a one-sentence summary of what's in the target file so the reader gets the necessary fact inline, and the Read is optional for depth:

   > The bootstrap must wait for MeshLoader via polling (`Changed:Wait()` races — see `phase-4.5-universal-rules.md §MeshLoader` for the full pattern).

   vs. the bad version:

   > See `phase-4.5-universal-rules.md` for MeshLoader handling.

   The first version is self-contained; the Read is enrichment. The second forces a Read to get any information at all.

2. **Merge tight clusters instead of cross-referencing.** If two topics are always read together, they belong in one file. v1's layout had 10 phase-4.5 files, but on inspection:
   - Modules + bootstrap are always co-loaded (you rewrite modules *to be* wired by the bootstrap).
   - Divergence + scale are always co-loaded (both are "override Roblox defaults").
   - Game-loop + assets-visibility + the CRITICAL visibility rule are always co-loaded (they're the universal Luau runtime rules).

   Merging these collapses 10 files to 6 (see layout below), eliminating ~8 cross-references entirely.

3. **Dependency DAG in the overview.** For optional files (animation, runtime-content), `phase-4.5-overview.md` lists prerequisites: "Read `phase-4.5-universal-rules.md` before `phase-4.5-runtime-content.md`." This surfaces the implicit ordering.

### Risk 4: `examples/` is a new directory with no standing instruction to read it

An agent working on a brand-new game never needs examples/. But an agent converting a game similar to Trash Dash (endless runner) or SimpleFPS (FPS) loses valuable lore unless something points at it.

**Mitigations:**

1. **Targeted signposts only.** Every mention of examples/ names the specific file and the specific topic:

   > For a concrete scale-down procedure from an endless runner (with actual SCALE, GROUND_Y, and laneOffset values), see `examples/endless-runner-trash-dash.md §scale`.

   Never "see examples/" without a topic anchor.

2. **`examples/README.md` as an index.** One table mapping game → genre → mechanics illustrated:

   ```
   | File | Genre | Illustrates |
   |---|---|---|
   | endless-runner-trash-dash.md | endless runner | scale-down, lane system, procedural segment spawning, state machine |
   | fps-simple-fps.md | FPS | player spawn disambiguation, weapon slot, non-humanoid aiming |
   ```

   SKILL.md mentions this index once in the intro: "Before converting a game, skim `references/examples/README.md` — if your game matches a known genre, the example may save significant debugging time." That's the discovery path.

3. **Opt-in load, not opt-out.** Examples are never auto-loaded. The agent decides based on game genre. This matches the user's feedback memory "make autonomous decisions, don't ask at decision points" — the agent reads its own examples without asking.

### Risk 5: Auto-memory feedback on "decision frameworks, not checklists"

The feedback memory says skill updates must be decision frameworks, not prescriptive checklists. Splitting into many files risks either over-generalization (vague, no actionable content) or slipping back into checklist style (easier when the file is small).

**Mitigations:**

1. **House style for phase docs.** Every decision-bearing section follows a 3-part template:

   ```
   ### <Decision name>

   **Question:** What are you actually deciding?
   **Factors:** What inputs drive the decision? (Unity characteristics, game genre, target fidelity.)
   **Options:** N approaches, each with tradeoffs and a "pick this when" guide.
   ```

   This makes it structurally hard to write a checklist. A checklist has no "options"; a decision framework does.

2. **Review test.** When writing or editing a phase doc, ask: "If a reader makes a different decision than I would, are they still following the file?" If no, it's a checklist — rewrite.

3. **Preserve escape hatches.** Current SKILL.md has phrases like "not always needed — depends on how the original meshes were authored. Test visually before applying." These escape hatches are what distinguishes a framework from a checklist. The refactor must preserve them verbatim, not shave them off for brevity.

---

## Additional risks surfaced during deep dive

### Risk 6: Stale reference tracking

With 20+ files, it's easy for one to drift out of sync with `conversion_helpers.py` or with sibling docs. No single person can hold them all in mind.

**Mitigation:** single `references/INDEX.md` that lists each file with:
- Owner topic (1 line)
- Which source modules it describes (for grep)
- Last-modified date (manual, but good enough)

Not enforced, but a single pane for "is anything obviously stale?"

### Risk 7: Hitting the 10K-token Read limit again

If we let files grow, we'll hit the same wall in a year. The current `transpiler-gaps.md` estimate is ~80 lines / ~4K tokens — headroom exists but not infinite.

**Mitigation:** hard rule in `INDEX.md`:

> **File size ceiling: 150 lines or ~6K tokens, whichever is smaller.** When a file exceeds this, split it or tighten, do not exceed.

CI could enforce this with a simple `wc -l` check in a pre-commit hook, but that's out of scope. A commented reminder in each file is the minimum.

### Risk 8: Discoverability of new phase files mid-conversation

If the agent is resuming a conversation where the phase files weren't loaded, it may not know they exist (no Glob, no ls in working memory).

**Mitigation:** `SKILL.md` intro lists every reference filename inline (not paragraphs, just a tree). The tree is under ~20 lines, stays within the thin-orchestrator budget, and ensures the filenames are in context the moment SKILL.md is read.

### Risk 9: Decision-point bias toward asking the user

The user has feedback memories: "Never ask about folder paths" and "Make autonomous decisions during conversion, don't ask at decision points." Current SKILL.md has many "Ask the user" phrases. The refactor should take this opportunity to rewrite decision points as autonomous: "Agent decides based on factors X, Y, Z. Only escalate if genuinely ambiguous."

**Mitigation:** the house style template (Risk 5) already produces autonomous framing. Explicit rule: prefer "decide based on" over "ask the user". Only escalate when the factors genuinely don't disambiguate.

### Risk 10: Bridge and examples files falling behind the code

`bridge/` modules evolve (AnimatorBridge, TransformAnimator). If a phase doc references an old API, it misleads the agent.

**Mitigation:** each phase doc that references a bridge module names the file path (`bridge/TransformAnimator.lua`) so the agent can Read the current source to confirm the API. Phase docs give *intent*, source files are *authoritative*. This is already how the current SKILL.md works — just preserve the pattern.

---

## Revised layout (v2)

```
.claude/skills/convert-unity/
├── SKILL.md                                 # Thin orchestrator (~150 lines)
├── references/
│   ├── INDEX.md                             # File inventory, size ceiling rule
│   ├── phase-1-discovery.md                 # ~40 lines
│   ├── phase-2-inventory.md                 # ~40 lines
│   ├── phase-3-materials.md                 # ~70 lines (includes SurfaceAppearance rules)
│   ├── phase-4-transpilation.md             # ~40 lines
│   ├── phase-4.5-overview.md                # ~40 lines — router with dependency DAG
│   ├── phase-4.5-architecture-map.md        # ~45 lines — always read first
│   ├── phase-4.5-divergence-and-scale.md    # ~120 lines — merge of v1's divergence + scale
│   ├── phase-4.5-universal-rules.md         # ~110 lines — game-loop + assets-visibility + CRITICAL visibility rule; always read
│   ├── phase-4.5-animation.md               # ~55 lines — optional (only if game has animations)
│   ├── phase-4.5-runtime-content.md         # ~80 lines — optional (only if game spawns runtime content)
│   ├── phase-4.5-transpiler-gaps.md         # ~90 lines — symptom-indexed debugging ref (always-read during module writing)
│   ├── phase-4.5-module-rewrite.md          # ~130 lines — modules + bootstrap merged
│   ├── phase-5-assembly.md                  # ~40 lines — terrain, LFS, MCP painting
│   ├── phase-6-upload.md                    # ~40 lines — two-stage upload, Studio publish
│   ├── upload-patching.md                   # (existing — unchanged)
│   └── examples/
│       ├── README.md                        # Genre-indexed example catalog
│       ├── endless-runner-trash-dash.md     # TD-specific: lanes, segments, LoadoutState
│       └── fps-simple-fps.md                # SimpleFPS: spawn disambig, weapon slot
```

**File count:** 6 phase-4.5 files (down from v1's 10). Every other phase gets one file. Total: 13 phase files + overview + INDEX + examples/README + 2 example files + upload-patching = **20 files** in references/, including the 2 that already exist.

**Largest files under the ceiling:** module-rewrite (~130), divergence-and-scale (~120), universal-rules (~110), transpiler-gaps (~90). All comfortably under 150 lines / 6K tokens.

---

## Content remapping (current SKILL.md → new layout)

| Current lines | Topic | Target |
|---|---|---|
| 1–15 | Frontmatter, intro | `SKILL.md` |
| 19–27 | Step 0 preflight | `SKILL.md` (inline, too short to split) |
| 29–35 | Step 1 discovery | `SKILL.md` stub + `phase-1-discovery.md` |
| 37–43 | Step 2 inventory | `SKILL.md` stub + `phase-2-inventory.md` |
| 45–51 | Step 3 materials | `SKILL.md` stub + `phase-3-materials.md` |
| 500–511 | SurfaceAppearance, split meshes | `phase-3-materials.md` |
| 53–63 | Step 4 transpile | `SKILL.md` stub + `phase-4-transpilation.md` |
| 65–90 | 4.5a architecture map | `phase-4.5-architecture-map.md` |
| 92–166 | 4.5b divergence + 4.5c scale | `phase-4.5-divergence-and-scale.md` (merged) |
| 168–189 | 4.5d game loop + timing | `phase-4.5-universal-rules.md` (merged) |
| 191–222 | 4.5e assets + visibility + data | `phase-4.5-universal-rules.md` (merged) |
| 224–226, 231–234 | 4.5f input + physics | `phase-4.5-module-rewrite.md` (input wiring lives in bootstrap section) |
| 236–239 | 4.5f runtime content generation | `phase-4.5-runtime-content.md` |
| 243–278 | 4.5g animation, particles, player states | `phase-4.5-animation.md` |
| 280–299 | 4.5h module table + rules | `phase-4.5-module-rewrite.md` |
| 301–365 | 4.5h 11 semantic gaps | `phase-4.5-transpiler-gaps.md` (regrouped into 3 clusters + symptom index) |
| 366–413 | timing, spawning, movement, diagnostic | `phase-4.5-runtime-content.md` |
| 415–479 | 4.5i bootstrap | `phase-4.5-module-rewrite.md` |
| 481–511 | CRITICAL visibility rule + mesh/material issues | `phase-4.5-universal-rules.md` + partial in `phase-3-materials.md` (material_mapper) |
| 513–521 | key principles | `SKILL.md` (condensed into universal rules teaser) |
| 523–540 | Step 5 assembly | `SKILL.md` stub + `phase-5-assembly.md` |
| 542–562 | Step 6 upload | `SKILL.md` stub + `phase-6-upload.md` |
| 564–568 | Step 7 report | `SKILL.md` (inline) |
| 570–581 | Error handling, guidelines | `SKILL.md` (inline) |

Every rule in the current file has a home. Nothing gets deleted.

---

## Game-specific cleanup (unchanged from v1, reproduced here for completeness)

| Current text | Location | Action |
|---|---|---|
| `LoadoutState`, `GameState`, `GameOverState` state examples | 4.5a | Generalize names; move specifics → `examples/endless-runner-trash-dash.md`. |
| `GameState → TrackManager → CharacterInputController → Character` ownership | 4.5a | Generalize; move → example. |
| "endless runners" (5+ occurrences) | 4.5a, 4.5c, 4.5f, 4.5i | Generalize to "games with custom movement (auto-run, rail, grid, vehicle)". |
| `worldDistance`, `(1 + speedRatio)` timing | 4.5a, 4.5h | Generalize to "distance-based timing". |
| `IndustrialWarehouse01`, `SuburbsHouse01` | 4.5c | Move → example. Keep general rule "decoration positions are baked into prefabs". |
| `laneOffset`, lane stripes, `GROUND_Y = 0.625` | 4.5c | Move numerics → example. Keep general scale-down procedure with placeholder names. |
| `0.74-stud coin` | 4.5c | Keep principle; drop the number. |
| `Fishbones_TransformAnimConfig` | 4.5g | Generalize to `<TemplateName>_TransformAnimConfig`. |
| `ThemeDatabase.GetThemeData("Tutorial")`, `tutorialThemeData` | 4.5h #9 | Generalize to `<Database>.GetEntry(name)`. |
| `LoadoutState`/`GameState` + `menuEnvironment` | 4.5h #10 | Generalize to "menu vs gameplay state holds backdrop refs". |
| `SpawnPoint.cs`, `UpdateSpawnpoint`, `SetSpawnCFrame` | 4.5i | Move → `examples/fps-simple-fps.md`. Keep rule "grep for method name before calling". |
| Player prefab vs spawn marker | 4.5i | Move → fps example. Keep rule "scenes may contain a Model and Part sharing a name". |
| `WeaponSlot` | 4.5i | Move → fps example. |
| "track spawner needs porting, not floor added" | 4.5i principles | Generalize to "procedural generation system needs porting". |
| `ChangeLane`, `Jump`, `Slide` input method names | 4.5i | Generalize to "dispatch keys to controller methods (lane changes, jumps, etc.)". |

Rule of thumb: **if the reader would have to know the specific game to understand the sentence, it's game-specific.** Rewrite in terms of mechanics.

---

## SKILL.md shape (target)

```markdown
---
name: convert-unity
description: ...
argument-hint: <unity_project_path> <output_dir>
allowed-tools:
  - Bash(python3 convert_interactive.py *)
  - Bash(python -m pytest *)
  - Read
---

# Convert Unity Project to Roblox

Interactive, phase-based conversion. Pause at decision points for human judgment — do NOT run the pipeline blindly.

**For every phase below, you MUST `Read` the named reference file before taking action. Skipping the Read is a process violation. The teasers inlined here are not a substitute.**

## Universal rules (always apply)

- **Visibility.** No renderer in Unity = `Transparency=1` in Roblox. The pipeline handles this; never add workarounds that force child MeshParts visible.
- **Game loop.** `Update()` needs explicit `RunService.Heartbeat:Connect(...)`. Disconnect on cleanup.
- **Yielding.** `task.wait()` inside a signal callback (`Heartbeat`, `Touched`) silently stops execution. Wrap yielding work in `task.spawn(function() ... end)`.
- **Part size.** Any dimension > 2048 studs silently fails to render. Clamp or tile.
- **ScreenGui placement.** Put converted UIs in `ReplicatedStorage` with `Enabled=false`. Never in `StarterGui`.
- **Faithful port over workarounds.** If Unity generates content at runtime, the Roblox port must too. Don't substitute a runtime system with a static hack.
- **Bridge modules are reusable.** Never modify `bridge/*` for one game.

## Reference files

    references/
      INDEX.md
      phase-1-discovery.md         phase-4.5-animation.md
      phase-2-inventory.md         phase-4.5-runtime-content.md
      phase-3-materials.md         phase-4.5-transpiler-gaps.md
      phase-4-transpilation.md     phase-4.5-module-rewrite.md
      phase-4.5-overview.md        phase-5-assembly.md
      phase-4.5-architecture-map.md   phase-6-upload.md
      phase-4.5-divergence-and-scale.md
      phase-4.5-universal-rules.md
      upload-patching.md
      examples/README.md (genre index — skim if game matches a known genre)

## Workflow

### Step 0: Preflight
    python3 convert_interactive.py preflight <unity_project_path> <output_dir> --install 2>/dev/null

### Step 1: Discovery
**Read `references/phase-1-discovery.md` before running.**
*Teaser:* Multiple scenes → agent selects the primary gameplay scene; escalate only if genuinely ambiguous.

    python3 convert_interactive.py discover <unity_project_path> <output_dir> 2>/dev/null

### Step 2: Asset Inventory
**Read `references/phase-2-inventory.md` before running.**
*Teaser:* Duplicate GUIDs are usually harmless — keep the first occurrence and log.

    python3 convert_interactive.py inventory <unity_project_path> <output_dir> 2>/dev/null

### Step 3: Material Mapping
**Read `references/phase-3-materials.md` before running.**
*Teaser:* SurfaceAppearance without a ColorMap renders white — only create it when `rdef.color_map` is present.

    python3 convert_interactive.py materials <unity_project_path> <output_dir> 2>/dev/null

### Step 4: Code Transpilation
**Read `references/phase-4-transpilation.md` before running.**
*Teaser:* On `insufficient_credits`/`auth_failure`, do not retry — surface to user immediately.

    python3 convert_interactive.py transpile <unity_project_path> <output_dir> --api-key <key> 2>/dev/null

### Step 4.5: Game Logic Porting
**Read `references/phase-4.5-overview.md` first** — it is a router. It tells you which of the topic files to load based on the game's characteristics.
*Teaser:* Always load `architecture-map`, `universal-rules`, `transpiler-gaps`, `module-rewrite`. Load `animation`, `runtime-content`, `divergence-and-scale` only if the game needs them.

### Step 5: Assembly
**Read `references/phase-5-assembly.md` before running.**
*Teaser:* If terrain `.asset` is an LFS pointer, warn and ask user to `git lfs pull`.

    python3 convert_interactive.py assemble <unity_project_path> <output_dir> 2>/dev/null

### Step 6: Upload & Publish
**Read `references/phase-6-upload.md` before running.**
*Teaser:* Two-stage: assets via API, then the user must publish the place via Roblox Studio (File → Publish to Roblox). Never try to publish via API — scripts get stripped.

    python3 convert_interactive.py upload <output_dir> --roblox-api-key <key> ... 2>/dev/null

### Step 7: Final Report
    python3 convert_interactive.py report <output_dir> 2>/dev/null

## Error handling

If any phase fails, show the error and ask how to proceed (retry, skip, abort). Never silently swallow errors.

## If you skipped a Read
Stop. Read the phase reference file now, then re-check your decisions. The teasers are not the rules.
```

Line count target: ~150 lines. Within the thin-orchestrator budget.

---

## `phase-4.5-overview.md` shape (target)

```markdown
# Phase 4.5: Game Logic Porting — Router

Step 4.5 is the module-rewrite phase. It is a collection of independent concerns — read only what this game needs.

## Mandatory reading order

1. `phase-4.5-architecture-map.md` — produce the state/ownership/timing map. Everything below keys off this.
2. `phase-4.5-universal-rules.md` — game loop, yielding, visibility, assets, ScriptableObject data, ScreenGui placement. Applies to every game.
3. `phase-4.5-transpiler-gaps.md` — 11 ways transpiled Luau silently breaks. Has a symptom index at the top; read linearly first, then use as a debugging reference.
4. `phase-4.5-module-rewrite.md` — how to structure the rewrite into Luau modules and wire them in the bootstrap.

## Conditional reading

Load these only if the architecture map surfaces the relevant characteristic:

| Condition from architecture map | Read |
|---|---|
| Unity character height differs from Roblox default, OR custom camera/input/movement | `phase-4.5-divergence-and-scale.md` |
| Game has Mecanim Animator Controllers, legacy Animation components, or ParticleSystems | `phase-4.5-animation.md` |
| Game spawns content at runtime (enemies, level chunks, obstacle pools) | `phase-4.5-runtime-content.md` |

## Dependency DAG

- `divergence-and-scale` depends on `architecture-map` + `universal-rules`
- `runtime-content` depends on `universal-rules` + `module-rewrite`
- `animation` depends on `universal-rules`
- `module-rewrite` depends on `universal-rules` + `transpiler-gaps`

If you find yourself cross-referencing a file you haven't loaded, Read it.
```

---

## Validation plan (acceptance test)

Before merging the refactor, run this test to catch the fragmentation risk empirically:

1. **Baseline.** On a fresh clone at the current `SKILL.md`, run `/convert-unity` on Trash Dash and record the list of decisions made at each phase.
2. **Refactor branch.** Swap in the new layout. Run `/convert-unity` on the same Trash Dash project.
3. **Tool-call grep.** Look at the transcript. For each phase 1–6 and each step of 4.5, verify the agent issued a `Read` on the expected reference file before the corresponding `Bash` command.
4. **Decision equivalence.** Compare the decisions made at each phase to the baseline. Any divergence needs explanation — is it an improvement, a regression, or noise?
5. **Repeat with SimpleFPS** to catch game-specific regressions.

Pass criteria:
- 100% of phases have the expected Read in the transcript.
- No decision regressions (same or better choice at every decision point).
- No increase in number of "asked the user" interactions (decision-point bias check).

If the test fails on (3) — any Read skipped — the phase-stub language is not strong enough. Iterate the teasers/imperatives. This is the feedback loop that prevents Risk 1 from silently regressing the skill.

---

## House style for phase docs

Every decision-bearing section uses this template:

```markdown
### <Decision name>

**Question:** <What are you actually deciding?>

**Factors:** <Inputs that drive the decision — Unity characteristics, game genre, target fidelity.>

**Options:**

- **<Option A>** — <Tradeoff summary.> Pick this when <criterion>.
- **<Option B>** — <Tradeoff summary.> Pick this when <criterion>.
- **<Option C>** — <Tradeoff summary.> Pick this when <criterion>.

**Escape hatch:** <When none of the options fit, what to do.>
```

Non-decision sections (universal rules, reference tables, symptom indexes) do not need the template — but must still include escape hatches where applicable ("test visually before applying").

---

## Rollout plan

1. **Create v2 files without generalizing.** Split the current `SKILL.md` content into the 20 target files, preserving every rule byte-for-byte. Verify `wc -l` of all new files ≥ 581.
2. **Replace `SKILL.md`** with the thin orchestrator. Verify ~150 lines.
3. **Run the validation plan.** Baseline + refactor transcripts, diff the decisions.
4. **If pass:** generalize game-specific content per the cleanup table. Move specifics to `examples/`.
5. **Re-run validation** to confirm generalization didn't regress decisions.
6. **Only then delete** old content that's been fully migrated.
7. Update `MEMORY.md` if the refactor surfaces lessons worth remembering.

---

## Summary of v1 → v2 changes

| Dimension | v1 | v2 |
|---|---|---|
| SKILL.md size | ~120 lines | ~150 lines (adds teasers + reference file tree) |
| phase-4.5 file count | 10 | 6 (merged tight clusters) |
| Fragmentation mitigation | "Read X" directive | Strong imperative + one-line teaser + self-check + acceptance test |
| Transpiler-gaps structure | Linear 11 items | 3 clusters + symptom index table |
| Cross-reference policy | None | "Never bare pointers" + dependency DAG in overview |
| examples/ discovery | Reference by name | Targeted signposts + README index + SKILL.md intro pointer |
| Decision-point style | Unspecified | House style template with options + escape hatch |
| Validation | Manual smoke test | Transcript grep + decision equivalence check |
| Size ceiling | None | 150 lines / 6K tokens, documented in INDEX.md |
| Autonomous-decision bias | Unaddressed | Explicit: prefer "agent decides" over "ask user" |

The v2 layout is safer under fragmentation (teasers + acceptance test), cheaper in context (6 vs 10 files for phase 4.5), and more navigable (symptom index, dependency DAG). The non-goals and the content-preservation guarantee are unchanged.
