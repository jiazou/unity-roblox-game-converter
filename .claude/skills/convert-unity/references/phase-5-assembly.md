# Phase 5: Assembly

Builds the `.rbxl` XML, generates the terrain loader, and wires the bootstrap.

## Command

```bash
python3 convert_interactive.py assemble <unity_project_path> <output_dir> 2>/dev/null
```

## Terrain handling

The assembly phase auto-detects Unity TerrainData assets (binary `.asset` files containing heightmaps). If found, it:

1. Extracts the heightmap (uint16 array), terrain dimensions, and layer names.
2. Downsamples to a 65×65 grid for performance.
3. Generates a `TerrainLoader` ServerScript that uses `Terrain:FillBlock()` with elevation-based materials (Sand < 5 studs, Grass < 20, Ground < 50, Rock ≥ 50).
4. Adds a water base surrounding the terrain.
5. Saves `terrain_data.json` to the output directory for optional MCP-based painting.

## LFS requirement

If the terrain `.asset` file is a Git LFS pointer (starts with `version https://git-lfs`), the converter warns but cannot extract terrain data. The user must run `git lfs install && git lfs pull` to download the binary.

## MCP-based alternative

When Roblox Studio is connected via MCP, terrain can be painted directly using `execute_luau` with the heightmap data. This produces smoother terrain than the loader-script approach because it runs at edit-time rather than at game startup.

**Procedure:** Read `terrain_data.json` from the output directory, generate Luau `Terrain:FillBlock()` calls in chunks (max ~10KB per MCP call), and execute them sequentially.

## Decision: mesh decimation quality

**Question:** If the assembly phase decimated meshes, was the reduction acceptable?

**Factors:**
- Reduction ratio per mesh. >80% simplification on a hero asset is probably too aggressive.
- Whether the decimated meshes are primary gameplay focus (character, key props) or background geometry.
- Roblox upload budget for triangle count.

**Options:**
- **Accept the decimation.** Default for background geometry.
- **Adjust quality.** Re-run with looser targets for hero assets, tighter for background.
- **Skip decimation.** Only if upload size is not a concern.

**Escape hatch:** The assembly report lists per-mesh reduction percentages — use it to triage.

## Decision: terrain verification

If terrain was found and processed, open the assembled `.rbxl` in Studio and verify visually. The agent can proceed without Studio, but terrain issues (wrong scale, wrong materials, missing water) are much easier to catch at this stage than post-upload.
