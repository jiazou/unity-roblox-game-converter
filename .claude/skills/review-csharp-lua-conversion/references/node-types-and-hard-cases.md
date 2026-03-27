# AST Node Types & Hard Cases

## Key tree-sitter C# node types to handle

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

## AST Emitter Mapping

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
- `[SerializeField]` attributes → `ReplicatedStorage.Templates:WaitForChild()` (using `serialized_refs`)

## Hard Cases (regex gets these wrong)

### 1. `Instantiate()` restructuring
Parse the argument list, emit `arg1:Clone()` + property assignments for position/rotation/parent.

### 2. `GetComponent<T>()`
Parse the type argument, emit `:FindFirstChildOfClass("RobloxType")` using `TYPE_MAP`.

### 3. Property declarations
Emit as getter/setter functions or direct field access depending on complexity.

### 4. Coroutine methods (`IEnumerator` + `yield return`)
Restructure as `task.spawn(function()...task.wait()...end)`.

### 5. Event subscriptions (`event += handler`)
Emit `:Connect(handler)`.

### 6. String interpolation (`$"text {expr}"`)
Emit `string.format("text %s", tostring(expr))` or `"text " .. tostring(expr)`.

### 7. Ternary expressions in complex contexts
Emit `if cond then a else b` (Luau supports inline if-expressions).

## Regex Rule Categories

- **AST-structural** (must be handled by tree walking): class/namespace stripping, method declarations, control flow, brace-to-`end` conversion, `[SerializeField]` handling, for-loop restructuring
- **Token-level** (safe as simple substitutions on non-string/non-comment text): `null` → `nil`, `!=` → `~=`, `&&` → `and`, `||` → `or`, `this.` → `self.`, semicolon stripping
- **API mapping** (data-driven lookups): Everything in `API_CALL_MAP`, `TYPE_MAP`, `LIFECYCLE_MAP`

## Success Criteria

- All existing tests pass (zero regressions)
- `Instantiate()` produces valid `:Clone()` output
- String literals and comments are never transformed
- Nested control flow produces correct `end` block placement
- Confidence scores are equal or higher than regex for equivalent input
- Regex fallback still works when tree-sitter is unavailable
