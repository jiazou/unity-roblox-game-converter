# Skill: Fix Luau Validator Comment/String Stripping

## Goal

Fix false positives in `modules/code_validator.py` caused by incorrect
handling of Luau long strings and comment stripping order.

## Context

The code validator checks transpiled Luau for block-keyword balance, residual
C# syntax, and curly braces.  Before checking, it strips comments and string
literals so they don't trigger false positives.  Two bugs in the stripping
logic cause false positives that undermine the validator's gating role.

## Fixes Required

### 1. Handle Luau level-N long strings

**File**: `code_validator.py:68-77`
**Problem**: Only `[[...]]` (level 0) is stripped.  Luau supports `[=[...]=]`,
`[==[...]==]`, etc.  A long string like `[=[function foo()]=]` is not stripped,
causing a false block-balance error.
**Fix**: Use a regex that matches any long-string level:
`\[(=*)\[.*?\]\1\]` (with `re.DOTALL`).

### 2. Fix comment stripping order

**File**: `code_validator.py:68-77`
**Problem**: Single-line `--` comment stripping runs before `--[[ ]]` block
comment removal.  For `--[[ function foo() ]]`, the `--` strip removes the
prefix, leaving `[[ function foo() ]]`, and the block-string strip may not
clean it up correctly.
**Fix**: Strip block comments (`--[[ ]]` and `--[=[ ]=]`) BEFORE stripping
single-line `--` comments.

## Verification

```bash
python -m pytest tests/test_code_validator.py tests/test_code_validator_detailed.py -v
```

Add tests for:
- Luau source with `[=[function end]=]` long string (should NOT cause balance error)
- Luau source with `--[[ if then ]]` block comment (should NOT cause balance error)
- Normal validation behavior unchanged

## References

- Luau long string syntax: https://luau-lang.org/syntax#string-literals
- `docs/FRAGILITY_AUDIT.md` — P2a section
