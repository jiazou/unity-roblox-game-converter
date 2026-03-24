---
name: review-csharp-lua-conversion
description: "[ARCHIVED] The rule-based and AST transpilers have been removed. All C# → Luau transpilation now uses Claude AI."
---

# ARCHIVED

This skill is no longer applicable. The rule-based regex transpiler and AST-driven
transpiler have been removed from `modules/code_transpiler.py`. All C# → Luau
transpilation now uses Claude AI exclusively (requires an Anthropic API key).

Tree-sitter is still used for structural analysis (script type classification,
pattern detection) but not for code generation.
