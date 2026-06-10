import ast
import inspect
import re
import sys
import textwrap
import typing as t

import discord
from redbot.core import commands


def dotted_name(node: ast.AST) -> t.Optional[str]:
    """Return a dotted name for a Name/Attribute node, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def parse_instantiated_names(source: str) -> list[str]:
    """All callee names of Call nodes in the source (recursively), deduped, order-preserved."""
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = dotted_name(node.func)
            if name and name not in names:
                names.append(name)
    return names


def resolve_name(name: str, namespace: dict) -> t.Optional[object]:
    """Resolve a possibly-dotted name against a namespace dict. Returns None if unresolved."""
    parts = name.split(".")
    obj = namespace.get(parts[0])
    if obj is None:
        return None
    for attr in parts[1:]:
        obj = getattr(obj, attr, None)
        if obj is None:
            return None
    return obj


def is_ui_class(obj: object) -> bool:
    return isinstance(obj, type) and issubclass(obj, (discord.ui.View, discord.ui.Modal))


STOP_MODULES = ("discord.", "redbot.")


def is_stop_class(cls: type) -> bool:
    """True for framework base classes we should not expand (discord.ui.*, object, redbot)."""
    if cls is object:
        return True
    module = getattr(cls, "__module__", "") or ""
    return module.startswith(STOP_MODULES)


def class_source_with_bases(cls: type) -> str:
    """Source of cls plus each base in its MRO until a framework/stop class. Skips unavailable."""
    chunks: list[str] = []
    seen: set[str] = set()
    for klass in cls.__mro__:
        if is_stop_class(klass):
            continue
        key = f"{klass.__module__}.{klass.__qualname__}"
        if key in seen:
            continue
        seen.add(key)
        try:
            chunks.append(inspect.getsource(klass))
        except (OSError, TypeError):
            chunks.append(f"# Source unavailable for {klass.__qualname__}")
    return "\n\n".join(chunks)


# Matches emoji=<expr> or label=<expr> where <expr> is a bare identifier or dotted name
# (NOT a quoted string literal). e.g. emoji=C.PLUS, label=SOME_CONST
LABEL_CONST_RE = re.compile(r"\b(?:emoji|label)\s*=\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)")


def resolve_label_constants(source: str, namespace: dict) -> dict[str, str]:
    """Find emoji=/label= identifier args and resolve them to their string values via namespace."""
    legend: dict[str, str] = {}
    for name in LABEL_CONST_RE.findall(source):
        if name in legend:
            continue
        value = resolve_name(name, namespace)
        if isinstance(value, str) and value:
            legend[name] = value
    return legend


def class_namespace(cls: type) -> dict:
    """Module globals of a class, for resolving names referenced inside its source."""
    module = sys.modules.get(getattr(cls, "__module__", ""))
    return vars(module) if module is not None else {}


def collect_ui_classes(
    source: str,
    namespace: dict,
    visited: set[str],
    depth: int,
    max_depth: int,
) -> list[type]:
    """Recursively gather UI classes launched from source, depth-first, deduped via visited."""
    found: list[type] = []
    if depth > max_depth:
        return found
    for name in parse_instantiated_names(source):
        obj = resolve_name(name, namespace)
        if not isinstance(obj, type) or not is_ui_class(obj):
            continue
        key = f"{obj.__module__}.{obj.__qualname__}"
        if key in visited:
            continue
        visited.add(key)
        found.append(obj)
        child_source = class_source_with_bases(obj)
        found.extend(
            collect_ui_classes(child_source, class_namespace(obj), visited, depth + 1, max_depth)
        )
    return found


def expand_command_ui_source(
    command: "commands.Command",
    *,
    max_depth: int = 2,
    per_class_chars: int = 4000,
    total_chars: int = 12000,
) -> str:
    """Expand a command's callback into the UI classes it launches, for menu walkthroughs."""
    try:
        callback_source = inspect.getsource(command.callback)
    except (OSError, TypeError) as e:
        return f"Could not fetch source for '{command.qualified_name}': {e}"

    namespace = getattr(command.callback, "__globals__", {})
    visited: set[str] = set()
    ui_classes = collect_ui_classes(callback_source, namespace, visited, depth=1, max_depth=max_depth)

    header = f"Command: [p]{command.qualified_name}\nLaunch source:\n```python\n{callback_source}\n```\n"

    if not ui_classes:
        return header + "\nNo interactive UI detected for this command."

    legend: dict[str, str] = {}
    class_sources: list[tuple[type, str]] = []
    for cls in ui_classes:
        src = class_source_with_bases(cls)
        class_sources.append((cls, src))
        for key, value in resolve_label_constants(src, class_namespace(cls)).items():
            legend.setdefault(key, value)

    parts: list[str] = [header]
    if legend:
        legend_lines = "\n".join(f"{k} = {v}" for k, v in legend.items())
        parts.append(f"Button/label constants resolved:\n{legend_lines}\n")

    used = sum(len(p) for p in parts)
    for cls, src in class_sources:
        if len(src) > per_class_chars:
            src = src[:per_class_chars] + "\n# ... class source truncated ..."
        block = f"\n# === {cls.__qualname__} ({cls.__module__}) ===\n```python\n{src}\n```\n"
        if used + len(block) > total_chars:
            parts.append("\n# ... remaining UI classes truncated (output budget reached) ...")
            break
        parts.append(block)
        used += len(block)

    if len(visited) > len(class_sources):
        parts.append(
            f"\n# Note: some nested menus omitted (depth cap {max_depth} or output budget reached)."
        )

    return "".join(parts)
