# Phase 6: Upload & Publish

Upload is a **two-stage** process: API-based asset upload, then manual Studio publish.

## Stage 1 — Asset upload via API

Uploads meshes, textures, and audio to Roblox via Open Cloud. Requires an API key. Patches the `.rbxl` with uploaded asset IDs.

```bash
python3 convert_interactive.py upload <output_dir> \
  --roblox-api-key <key> \
  [--creator-id <id> | --creator-username <username>] \
  [--creator-type User|Group] 2>/dev/null
```

For internals of how asset-ID patching works (ordering, XML patching, MeshLoader injection), read `upload-patching.md`.

## Stage 2 — Place publish via Roblox Studio

**The Open Cloud API strips `Script.Source` from uploaded binary files for security.** The final place MUST be published through Roblox Studio to preserve script source code (TerrainLoader, MeshLoader, GameBootstrap, all controllers).

**Instruct the user to:**

1. Open the patched `.rbxl` in Roblox Studio.
2. Use **File > Publish to Roblox** (NOT "Save to Roblox" — that saves without publishing).

**Never attempt to publish the place via the API** — it will silently produce a broken game with empty scripts.

## Decision: asset upload failures

**Question:** If some asset uploads fail mid-stage, what should the agent do?

**Factors:**
- Failure type. Rate-limit errors are transient; content-policy rejections are permanent.
- How critical the failing assets are. Hero meshes matter; background props don't.
- How many assets failed (percentage of total).

**Options:**
- **Retry.** Transient errors (network, rate limit) — wait and retry once.
- **Continue without.** Low failure rate on non-critical assets; the game still works.
- **Abort.** High failure rate or critical assets failing — investigate before proceeding.

**Escape hatch:** The uploader writes a per-asset status log. Inspect it before deciding.
