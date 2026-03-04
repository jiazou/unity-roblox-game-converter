# Review & Rewrite C# → Luau Transpilation

A skill that replaces the fragile regex-based C# → Luau transpiler with a robust AST-driven approach using tree-sitter (already available in the codebase).

## Invocation

User-invocable: yes

## Instructions

You are refactoring the C# → Luau transpilation pipeline in `modules/code_transpiler.py`. The current `_rule_based_transpile()` function applies 73+ sequential regex substitutions to raw source text. This is fragile, context-blind, and produces broken output for many common patterns. Your job is to replace it with an AST-driven transpiler that uses tree-sitter (already imported in the module) to walk the C# syntax tree and emit Luau structurally.

### Background: Why the Regex Approach Is Fragile

The current `_rule_based_transpile()` (lines 317–614 of `modules/code_transpiler.py`) has these problems:

1. **Context-blind**: Regex operates on raw text, transforming code inside string literals and comments
2. **Order-dependent**: 73+ patterns with hidden coupling (earlier rules alter text for later rules)
3. **Structurally broken output**: e.g., `Instantiate(prefab)` → `.Clone(prefab)` (broken syntax, documented in `docs/UNSUPPORTED.md:426–448`)
4. **Nesting-blind**: Can't match braces to `end` blocks, nested ternaries, or nested generics
5. **Limited coverage**: Properties, LINQ, coroutines, delegates, events all fail

### What Already Exists

- **Tree-sitter C# parser**: Already imported and working (`_TS_AVAILABLE`, `_ts_parser`, `_ts_language` at lines 56–68)
- **`_parse_csharp_ast()`**: Extracts `CSharpClassInfo` (class name, base class, fields, methods, lifecycle hooks, API usage) — but only used for metadata, not transformation
- **`api_mappings.py`**: Clean data tables (`API_CALL_MAP`, `TYPE_MAP`, `LIFECYCLE_MAP`, `SERVICE_IMPORTS`) — these are fine as-is and should be reused
- **Test suite**: 50+ tests across `tests/test_code_transpiler.py` and `tests/test_code_transpiler_detailed.py` — all must continue to pass

### Step-by-Step Implementation Plan

#### Phase 1: Audit & Categorize Current Regex Rules

Before writing code, read `modules/code_transpiler.py` and categorize every regex in `_rule_based_transpile()` into:

- **AST-structural** (must be handled by tree walking): class/namespace stripping, method declarations, control flow (`if/else/for/while/foreach`), brace-to-`end` conversion, `[SerializeField]` handling, for-loop restructuring
- **Token-level** (safe as simple substitutions on non-string/non-comment text): `null` → `nil`, `!=` → `~=`, `&&` → `and`, `||` → `or`, `this.` → `self.`, semicolon stripping
- **API mapping** (data-driven lookups): Everything in `API_CALL_MAP`, `TYPE_MAP`, `LIFECYCLE_MAP`

Present this categorization to the user before proceeding.

#### Phase 2: Build the AST-Driven Emitter

Create a new function `_ast_transpile()` that:

1. **Parses** C# source with the existing tree-sitter parser
2. **Walks** the syntax tree recursively, emitting Luau for each node type
3. **Handles structural transformations** natively:
   - `compilation_unit` → strip usings, emit service imports
   - `namespace_declaration` → unwrap (emit children only)
   - `class_declaration` → unwrap if MonoBehaviour; emit as ModuleScript table if not
   - `method_declaration` → `local function name(params)...end`
   - `field_declaration` → `local name = value`
   - `if_statement` → `if condition then...elseif...else...end`
   - `while_statement` → `while condition do...end`
   - `for_statement` → `for i = start, stop do...end`
   - `foreach_statement` → `for _, item in collection do...end`
   - `block` / `{...}` → proper `end` placement (no heuristic brace matching)
   - `invocation_expression` → restructure calls like `Instantiate(prefab)` → `prefab:Clone()`
   - `[SerializeField]` attributes → `ServerStorage:WaitForChild()` (using `serialized_refs`)
4. **Applies token-level substitutions** only to identifier/literal nodes (NOT inside strings or comments)
5. **Applies API mappings** to `member_access_expression` and `invocation_expression` nodes (context-aware)
6. **Falls back to regex** for any node types not yet handled (emit raw text with existing regex pipeline), ensuring incremental adoption

Key tree-sitter C# node types to handle:
```
compilation_unit, using_directive, namespace_declaration, class_declaration,
method_declaration, field_declaration, property_declaration, constructor_declaration,
if_statement, else_clause, while_statement, for_statement, foreach_statement,
return_statement, expression_statement, local_declaration_statement,
invocation_expression, member_access_expression, object_creation_expression,
assignment_expression, binary_expression, unary_expression, parenthesized_expression,
identifier, string_literal, integer_literal, real_literal, boolean_literal, null_literal,
block, argument_list, parameter_list, variable_declaration, variable_declarator,
attribute_list, comment, type_argument_list
```

#### Phase 3: Handle the Hard Cases

These are the patterns that regex gets wrong and the AST approach must fix:

1. **`Instantiate()` restructuring**: Parse the argument list, emit `arg1:Clone()` + property assignments for position/rotation/parent
2. **`GetComponent<T>()`**: Parse the type argument, emit `:FindFirstChildOfClass("RobloxType")` using `TYPE_MAP`
3. **Property declarations**: Emit as getter/setter functions or direct field access depending on complexity
4. **Coroutine methods** (`IEnumerator` + `yield return`): Restructure as `task.spawn(function()...task.wait()...end)`
5. **Event subscriptions** (`event += handler`): Emit `:Connect(handler)`
6. **String interpolation** (`$"text {expr}"`): Emit `string.format("text %s", tostring(expr))` or `"text " .. tostring(expr)`
7. **Ternary expressions** in complex contexts: Emit `if cond then a else b` (Luau supports inline if-expressions)

#### Phase 4: Wire Into Existing Pipeline

1. Modify `_rule_based_transpile()` to call `_ast_transpile()` when tree-sitter is available
2. Keep the old regex path as fallback when tree-sitter is NOT available (preserving the existing `_TS_AVAILABLE` guard)
3. Maintain the same return signature: `(luau_source, confidence, warnings)`
4. Boost confidence scores for AST-driven output (it's inherently more reliable)
5. Preserve all existing function signatures — `transpile_scripts()`, `TranspiledScript`, `TranspilationResult` must not change

#### Phase 5: Test & Validate

1. Run the existing test suite: `python -m pytest tests/test_code_transpiler.py tests/test_code_transpiler_detailed.py -v`
2. **All existing tests must pass** — the AST approach must produce output compatible with current assertions
3. Add new tests for cases that regex got wrong:
   - `Instantiate()` produces valid `:Clone()` syntax
   - String literals are not transformed (e.g., `"int x = 5"` preserved)
   - Comments are not transformed
   - Nested control flow produces correct `end` placement
   - Properties are handled (at least partially)
   - Coroutine methods are structurally rewritten
4. Update `docs/UNSUPPORTED.md` to reflect which limitations are now resolved

### Important Constraints

- **Do NOT modify `api_mappings.py`** — the data tables are fine; only the consumption logic changes
- **Do NOT change the public API** of `transpile_scripts()` or the dataclass shapes
- **Do NOT remove the regex fallback** — it must remain for environments where tree-sitter is unavailable
- **Preserve the AI transpilation path** (`_ai_transpile()`) — it's orthogonal and unaffected
- **Keep the `serialized_refs` handling** — it must work identically in the AST path
- **Run tests after every major change** — don't batch up changes and test at the end

### Decision Points

Pause and ask the user at these points:

1. **After Phase 1**: "Here's how I've categorized the 73+ regex rules. Does this breakdown look right before I start building the AST emitter?"
2. **After Phase 2**: "The core AST emitter handles [N] node types. Here are the test results. Should I proceed to the hard cases, or do you want to review the approach first?"
3. **After Phase 3**: "I've handled Instantiate restructuring, GetComponent<T>, and [other hard cases]. Here are before/after examples. Any adjustments?"
4. **After Phase 5**: "All [N] existing tests pass plus [M] new tests. Here's a summary of what the AST approach now handles vs. what still falls back to regex. Ready to finalize?"

### Success Criteria

- All existing tests pass (zero regressions)
- `Instantiate()` produces valid `:Clone()` output (the documented MEDIUM-severity bug is fixed)
- String literals and comments are never transformed
- Nested control flow produces correct `end` block placement
- Confidence scores are equal or higher than the regex approach for equivalent input
- The regex fallback still works when tree-sitter is unavailable
