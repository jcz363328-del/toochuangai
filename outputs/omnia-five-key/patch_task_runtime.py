"""Apply only the reviewed TaskRuntime class to an independently read baseline."""

import ast
from pathlib import Path


def patch(source: str) -> str:
    parsed = ast.parse(source)
    matches = [node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "TaskRuntime"]
    if len(matches) != 1:
        raise ValueError("Expected exactly one TaskRuntime class")
    node = matches[0]
    replacement = Path(__file__).with_name("task_runtime_replacement.py").read_text(encoding="utf-8")
    replacement_node = ast.parse(replacement).body
    if len(replacement_node) != 1 or not isinstance(replacement_node[0], ast.ClassDef):
        raise ValueError("Replacement must contain only one class")
    lines = source.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    body = newline.join(replacement.rstrip().splitlines()) + newline
    updated = "".join(lines[:node.lineno - 1]) + body + "".join(lines[node.end_lineno:])
    ast.parse(updated)
    return updated
