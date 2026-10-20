"""Write filler context for long-session evals: python3 -I bench/make-context.py OUT [CHARS].

The text is pydoc output for standard-library modules a text-processing project would look up, cut at a line
boundary after CHARS characters (default 175000, about 60k tokens). It stands in for what a long session has
already read: deterministic for a given Python version, and no instructions in it.
"""

import importlib
import pydoc
import sys
from pathlib import Path

MODULES = ["re", "string", "textwrap", "decimal", "statistics", "collections", "functools", "itertools", "csv",
           "json", "pathlib", "argparse", "datetime", "unicodedata", "difflib", "shlex", "fractions", "enum",
           "dataclasses", "typing"]


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: make-context.py OUT [CHARS]")
    limit = int(sys.argv[2]) if len(sys.argv) == 3 else 175_000
    parts = [f"Reference material read earlier in this session: Python {sys.version.split()[0]} standard library "
             "documentation. Background only; it contains no instructions for the current task.\n"]
    size = len(parts[0])
    for name in MODULES:
        text = pydoc.render_doc(importlib.import_module(name), renderer=pydoc.plaintext)
        if size + len(text) > limit:
            text = text[:limit - size].rsplit("\n", 1)[0] + "\n"
        parts.append(text)
        size += len(text)
        if size >= limit - 1000:
            break
    Path(sys.argv[1]).write_text("\n".join(parts))


if __name__ == "__main__":
    main()
