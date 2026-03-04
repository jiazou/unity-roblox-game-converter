# Skill: Harden Asset Extraction

## Goal

Add per-file error recovery to `modules/asset_extractor.py` so that a single
corrupt file, broken symlink, or permission error does not crash the entire
asset extraction pipeline.

## Context

The `extract_assets()` function walks the `Assets/` directory and builds an
`AssetManifest` with metadata for every file.  The file-walk loop at lines
93-114 has zero error handling — `fpath.stat()` and `_sha256_of(fpath)` both
raise unhandled `OSError` on broken symlinks or permission-denied files.

## Fixes Required

### 1. Wrap the per-file body in try/except

**File**: `asset_extractor.py:93-114`
**Fix**: Add `try/except OSError` around the per-file processing.  On error,
append a warning to `manifest.warnings` (add a `warnings: list[str]` field to
`AssetManifest` if it does not exist) and `continue`.

### 2. Add a warnings field to AssetManifest

If `AssetManifest` does not already have a `warnings` field, add one so
callers can inspect extraction issues without the pipeline crashing.

## Verification

```bash
python -m pytest tests/test_asset_extractor.py tests/test_asset_extractor_detailed.py -v
```

Add tests for:
- Directory containing a broken symlink (should skip with warning, not crash)
- Unreadable file (should skip with warning, not crash)
- Normal operation unchanged (existing tests pass)

## References

- `docs/FRAGILITY_AUDIT.md` — P1a section
