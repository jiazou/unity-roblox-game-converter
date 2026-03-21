"""
code_validator.py — Validates generated Luau code for syntactic correctness.

Performs static analysis on transpiled Luau scripts to catch common errors
before they reach Roblox Studio. Checks include:

  - Balanced block keywords (function/do/if/while/for matched with end)
  - No residual C# syntax (braces, semicolons, class keyword, using directives)
  - Balanced parentheses and brackets
  - Basic Luau keyword validity

No other module is imported here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationIssue:
    """A single issue found during Luau code validation."""
    line: int          # 1-indexed, 0 if file-level
    column: int        # 1-indexed, 0 if unknown
    severity: str      # "error" | "warning"
    code: str          # short identifier, e.g. "E001"
    message: str


@dataclass
class ValidationResult:
    """Outcome of validating a single Luau script."""
    source_name: str
    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0


# ---------------------------------------------------------------------------
# Block-keyword matching
# ---------------------------------------------------------------------------

# Luau keywords that open a block requiring `end`
_BLOCK_OPENERS = re.compile(
    r"""
    \b(?:
        function\s*[\w.:]*\s*\(     |   # function declarations
        if\b.*\bthen\b              |   # if ... then
        for\b.*\bdo\b              |   # for ... do
        while\b.*\bdo\b            |   # while ... do
        repeat\b                        # repeat ... until
    )
    """,
    re.VERBOSE,
)

# `end` keyword anywhere (not just start of line — catches inline `if x then return end`)
_END_KW = re.compile(r"\bend\b")

# `until` closes a `repeat` block (instead of `end`)
_UNTIL_KW = re.compile(r"\buntil\b")


def _strip_comments_and_strings(source: str) -> str:
    """Remove Luau comments and string literals to avoid false positives."""
    # Remove block comments first: --[[ ... ]] and --[=[ ... ]=] (any level)
    result = re.sub(r"--\[(=*)\[.*?\]\1\]", "", source, flags=re.DOTALL)
    # Remove single-line comments (after block comments to avoid partial stripping)
    result = re.sub(r"--[^\n]*", "", result)
    # Remove multi-line long strings [[ ... ]], [=[ ... ]=], etc. (any level)
    result = re.sub(r"\[(=*)\[.*?\]\1\]", '""', result, flags=re.DOTALL)
    # Remove double-quoted strings (handle escaped quotes)
    result = re.sub(r'"(?:[^"\\]|\\.)*"', '""', result)
    # Remove single-quoted strings
    result = re.sub(r"'(?:[^'\\]|\\.)*'", "''", result)
    return result


# ---------------------------------------------------------------------------
# C# residue detection
# ---------------------------------------------------------------------------

_CSHARP_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"^\s*using\s+[\w.]+\s*;", re.MULTILINE),
     "E010", "Residual C# 'using' directive"),
    (re.compile(r"\bclass\s+\w+"),
     "E011", "Residual C# 'class' keyword"),
    (re.compile(r"\bnamespace\s+\w+"),
     "E012", "Residual C# 'namespace' keyword"),
    (re.compile(r"\b(?:public|private|protected|internal)\s+(?:static\s+)?(?:void|int|float|string|bool)\b"),
     "E013", "Residual C# access modifier / type declaration"),
    (re.compile(r"\bnew\s+\w+\s*\("),
     "W010", "Possible C# 'new' constructor call (Luau uses .new())"),
]

# Curly braces that look like C# blocks (after control-flow keywords, etc.)
# We only flag braces that follow patterns indicating C# block syntax,
# NOT valid Luau table constructors (e.g., {}, {1,2,3}, setmetatable({}, mt)).
# Valid Luau contexts for '{': after '=', ',', '(', 'return', or at line start.
# Flag `{` after C# control/declaration keywords. Three patterns:
# 1. `if/for/while/catch(...)  {` — keyword with closing `)` then `{`
# 2. `class/struct/interface/namespace/enum Name {` — declaration then `{`
# 3. `if/else/try/finally expr {` — keyword without parens, `{` at end of line
#    (but NOT when `{` follows `or`, `=`, `(`, `,` — those are Luau tables)
_CSHARP_OPEN_BRACE = re.compile(
    r"(?:"
    r"(?:(?:^|;)\s*(?:if|else\s*if|for|foreach|while|switch|catch)\b[^{\n]*\))\s*\{"
    r"|"
    r"(?:(?:^|;)\s*(?:class|struct|interface|namespace|enum)\b[^{\n]*)\{"
    r"|"
    r"(?:(?:^|;)\s*(?:if|else|try|finally|do)\b(?![^{\n]*(?:or|=|,|\()\s*\{)[^{\n]*)\{"
    r")",
    re.MULTILINE,
)
# Only flag closing braces followed by C# keywords (else/catch/finally).
# Standalone `}` on its own line is ambiguous — could be a Luau table close.
_CSHARP_CLOSE_BRACE = re.compile(
    r"^\s*\}\s*(?:else|catch|finally)\b",
    re.MULTILINE,
)

# Semicolons at end of line (C# artifact)
_TRAILING_SEMICOLON = re.compile(r";\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Parenthesis / bracket balance
# ---------------------------------------------------------------------------

def _check_balance(source: str) -> list[ValidationIssue]:
    """Check that parentheses and brackets are balanced."""
    issues: list[ValidationIssue] = []
    pairs = {"(": ")", "[": "]"}
    stack: list[tuple[str, int, int]] = []

    for line_idx, line in enumerate(source.splitlines(), 1):
        for col_idx, ch in enumerate(line, 1):
            if ch in pairs:
                stack.append((ch, line_idx, col_idx))
            elif ch in pairs.values():
                if not stack:
                    issues.append(ValidationIssue(
                        line=line_idx, column=col_idx, severity="error",
                        code="E020",
                        message=f"Unmatched closing '{ch}'",
                    ))
                else:
                    opener, _, _ = stack[-1]
                    if pairs.get(opener) == ch:
                        stack.pop()
                    else:
                        issues.append(ValidationIssue(
                            line=line_idx, column=col_idx, severity="error",
                            code="E021",
                            message=f"Mismatched bracket: expected '{pairs[opener]}', got '{ch}'",
                        ))
                        stack.pop()

    for opener, ln, col in stack:
        issues.append(ValidationIssue(
            line=ln, column=col, severity="error",
            code="E022",
            message=f"Unclosed '{opener}'",
        ))

    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_luau(source: str, source_name: str = "<script>") -> ValidationResult:
    """
    Validate a Luau source string for common issues.

    Checks:
      1. Block keyword balance (function/if/for/while/repeat vs end/until)
      2. No residual C# syntax
      3. Balanced parentheses and brackets
      4. No stray curly braces
      5. No trailing semicolons

    Args:
        source: Luau source code to validate.
        source_name: Display name for the script (used in reporting).

    Returns:
        ValidationResult with any issues found.
    """
    result = ValidationResult(source_name=source_name)
    stripped = _strip_comments_and_strings(source)

    # 1. Block keyword balance
    #    Luau ternary expressions (`local x = if a then b else c`) use
    #    `if...then` without a matching `end`.  Discount any `if...then`
    #    that also has `else` on the same line but no `end` — that's a
    #    ternary, not a block opener.
    openers = len(_BLOCK_OPENERS.findall(stripped))
    for line in stripped.splitlines():
        if (re.search(r"\bif\b.*\bthen\b", line)
                and re.search(r"\belse\b", line)
                and not re.search(r"\bend\b", line)):
            openers -= 1  # ternary if, not a block
    ends = len(_END_KW.findall(stripped))
    untils = len(_UNTIL_KW.findall(stripped))
    closers = ends + untils

    if openers > closers:
        result.issues.append(ValidationIssue(
            line=0, column=0, severity="error", code="E001",
            message=f"Unbalanced blocks: {openers} openers but only {closers} closers "
                    f"(missing {openers - closers} 'end' keyword(s))",
        ))
    elif closers > openers:
        result.issues.append(ValidationIssue(
            line=0, column=0, severity="warning", code="W001",
            message=f"More closers ({closers}) than openers ({openers}) — "
                    f"possible extra 'end' keyword(s)",
        ))

    # 2. C# residue detection
    for pattern, code, msg in _CSHARP_PATTERNS:
        for match in pattern.finditer(stripped):
            line_num = stripped[:match.start()].count("\n") + 1
            severity = "error" if code.startswith("E") else "warning"
            result.issues.append(ValidationIssue(
                line=line_num, column=0, severity=severity, code=code,
                message=f"{msg}: '{match.group().strip()}'",
            ))

    # 3. Curly braces that look like C# blocks (not Luau table constructors)
    for match in _CSHARP_OPEN_BRACE.finditer(stripped):
        line_num = stripped[:match.start()].count("\n") + 1
        result.issues.append(ValidationIssue(
            line=line_num, column=0, severity="error", code="E030",
            message="C#-style opening brace '{' found — Luau uses 'do/then...end' blocks",
        ))
    for match in _CSHARP_CLOSE_BRACE.finditer(stripped):
        line_num = stripped[:match.start()].count("\n") + 1
        result.issues.append(ValidationIssue(
            line=line_num, column=0, severity="error", code="E030",
            message="C#-style closing brace '}' found — Luau uses 'do/then...end' blocks",
        ))

    # 4. Trailing semicolons
    semicolons = list(_TRAILING_SEMICOLON.finditer(stripped))
    if semicolons:
        # Report first few, not all (can be noisy)
        for match in semicolons[:5]:
            line_num = stripped[:match.start()].count("\n") + 1
            result.issues.append(ValidationIssue(
                line=line_num, column=0, severity="warning", code="W030",
                message="Trailing semicolon (valid but non-idiomatic in Luau)",
            ))
        if len(semicolons) > 5:
            result.issues.append(ValidationIssue(
                line=0, column=0, severity="warning", code="W031",
                message=f"... and {len(semicolons) - 5} more trailing semicolons",
            ))

    # 5. Parenthesis/bracket balance
    result.issues.extend(_check_balance(stripped))

    # Tally
    result.error_count = sum(1 for i in result.issues if i.severity == "error")
    result.warning_count = sum(1 for i in result.issues if i.severity == "warning")
    result.valid = result.error_count == 0

    return result
