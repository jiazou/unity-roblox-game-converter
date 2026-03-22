---
name: review-csharp-lua-conversion
description: Replace the regex-based C# to Luau transpiler with an AST-driven approach using tree-sitter
---

# Review & Rewrite C# → Luau Transpilation

Replace the fragile regex-based transpiler in `modules/code_transpiler.py` with an AST-driven approach using tree-sitter (already available in the codebase).

## Why

The current `_rule_based_transpile()` applies 73+ sequential regex substitutions to raw text. It's context-blind (transforms inside strings/comments), order-dependent, and produces broken output for common patterns like `Instantiate(prefab)`.

## What Already Exists

- **Tree-sitter C# parser**: Working (`_TS_AVAILABLE`, `_ts_parser`, `_ts_language`)
- **`_parse_csharp_ast()`**: Extracts metadata but isn't used for transformation
- **`api_mappings.py`**: Clean data tables — reuse as-is
- **50+ tests**: All must continue to pass

## Phases

### Phase 1: Audit Regex Rules
Categorize every regex into: AST-structural, token-level, or API mapping. Present categorization before proceeding.

### Phase 2: Build AST Emitter
Create `_ast_transpile()` that parses with tree-sitter, walks the syntax tree, and emits Luau. Falls back to regex for unhandled node types.

### Phase 3: Handle Hard Cases
Instantiate restructuring, GetComponent<T>, properties, coroutines, events, string interpolation, ternaries.

### Phase 4: Wire Into Pipeline
Call `_ast_transpile()` when tree-sitter is available, keep regex fallback. Same return signature.

### Phase 5: Test & Validate
All existing tests pass + new tests for previously broken patterns.

See `references/` for detailed node types, hard case examples, and constraints.

## Decision Points

1. After Phase 1: Review regex categorization
2. After Phase 2: Review core emitter + test results
3. After Phase 3: Review hard case before/after examples
4. After Phase 5: Final summary of AST vs regex coverage

## Constraints

- Do NOT modify `api_mappings.py`
- Do NOT change public API of `transpile_scripts()` or dataclass shapes
- Do NOT remove the regex fallback
- Preserve the AI transpilation path (`_ai_transpile()`)
- Keep `serialized_refs` handling identical
- Run tests after every major change
