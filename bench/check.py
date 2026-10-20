"""Grade a benchmark repo: python3 bench/check.py TASK REPO. Prints JSON, exits 1 if any check failed."""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixture"
TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".cfg"}

MUTANTS = {
    "numbers": {
        "median of even-length input": [("return (ordered[mid - 1] + ordered[mid]) / 2", "return ordered[mid]")],
        "round_half_up rounding halves to even": [
            ("from decimal import ROUND_HALF_UP, Decimal", "from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal"),
            ("rounding=ROUND_HALF_UP", "rounding=ROUND_HALF_EVEN"),
        ],
        "percent with whole == 0": [("        return 0.0", "        return None")],
        "clamp accepting low > high": [('        raise ValueError("low must not exceed high")', "        pass")],
    },
    "durations": {
        "a unit given twice is accepted": [('            raise ValueError(f"unit {unit!r} given twice")', "            pass")],
        "trailing garbage is accepted": [("    if pos != len(text):", "    if False:")],
        "weeks parsed as days": [('"w": 604800', '"w": 86400')],
        "format_duration ignores largest": [('return " ".join(parts[:largest])', 'return " ".join(parts)')],
        "zero formatted as an empty string": [('        return "0s"', '        return ""')],
        "split_evenly gives the remainder to the last parts": [
            ("[base + 1 if i < extra else base for i in range(parts)]",
             "[base + 1 if i >= parts - extra else base for i in range(parts)]"),
        ],
    },
    "table": {
        "duplicate column names are accepted": [('            raise ValueError("column names must be unique")', "            pass")],
        "a short row is accepted": [("        if len(values) != len(self.headers):", "        if len(values) > len(self.headers):")],
        "sort_by ignores reverse": [("reverse=reverse)", "reverse=False)")],
        "numbers are left-aligned in render": [("        return str(value).rjust(width)", "        return str(value).ljust(width)")],
        "pipes are not escaped in to_markdown": [('str(value).replace("|", "\\\\|")', "str(value)")],
        "an unknown column raises ValueError": [("            raise KeyError(name) from None", "            raise ValueError(name) from None")],
    },
}
PUBLIC = {
    "numbers": ("clamp", "percent", "round_half_up", "mean", "median"),
    "durations": ("parse_duration", "format_duration", "add_durations", "split_evenly", "within"),
    "table": ("Table", "add_row", "column", "sort_by", "where", "widths", "render", "to_markdown"),
}


def sandbox_usable():
    if not shutil.which("bwrap"):
        return False
    return subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True).returncode == 0


SANDBOX = sandbox_usable()


def run_pytest(repo, *args):
    repo = str(repo)
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    if SANDBOX:
        cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--ro-bind", repo, repo, "--unshare-net", "--die-with-parent", "--chdir", repo, *cmd]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=120, env=env)
    except subprocess.TimeoutExpired:
        return False, "pytest timed out"
    lines = (result.stdout + result.stderr).strip().splitlines()
    return result.returncode == 0, lines[-1] if lines else ""


def changed_files(repo):
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(line[3:] for line in out.splitlines())


def text_files(repo):
    for path in sorted(Path(repo).rglob("*")):
        if ".git" in path.parts or "__pycache__" in path.parts or not path.is_file():
            continue
        if path.suffix in TEXT_SUFFIXES:
            yield path


def strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def check(text, passed, evidence):
    return {"text": text, "passed": bool(passed), "evidence": evidence}


def only_changed(repo, allowed):
    changed = changed_files(repo)
    extra = [path for path in changed if path not in allowed]
    return check(f"only {', '.join(sorted(allowed))} changed", changed and not extra,
                 f"changed: {changed}" + (f"; unexpected: {extra}" if extra else ""))


def tests_pass(repo, *args):
    ok, summary = run_pytest(repo, *args)
    return check("pytest passes", ok, summary)


def check_docstrings(repo):
    source = (Path(repo) / "src/textkit/strings.py").read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as err:
        return [check("strings.py still parses", False, str(err))]
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
    missing = [f.name for f in funcs if not ast.get_docstring(f)]
    not_google = [f.name for f in funcs if ast.get_docstring(f)
                  and not ("Args:" in ast.get_docstring(f) and "Returns:" in ast.get_docstring(f))]
    original = ast.parse((FIXTURE / "src/textkit/strings.py").read_text())
    return [
        check("every public function in strings.py has a docstring", funcs and not missing,
              f"{len(funcs) - len(missing)}/{len(funcs)} documented" + (f"; missing: {missing}" if missing else "")),
        check("docstrings have Args: and Returns: sections", not missing and not not_google,
              f"without both sections: {not_google}" if not_google else "all have both"),
        check("code is unchanged apart from docstrings", strip_docstrings(tree) == strip_docstrings(original),
              "AST without docstrings matches the original" if strip_docstrings(tree) == strip_docstrings(original)
              else "AST without docstrings differs from the original"),
        only_changed(repo, {"src/textkit/strings.py"}),
        tests_pass(repo),
    ]


def docstring_targets(tree):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            yield node.name, node
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            yield node.name, node
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    yield f"{node.name}.{item.name}", item


def needs_sections(node):
    if not isinstance(node, ast.FunctionDef):
        return []
    sections = []
    if [a for a in node.args.args if a.arg != "self"]:
        sections.append("Args:")
    if any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(node)):
        sections.append("Returns:")
    return sections


def check_docstrings_all(repo):
    modules = sorted(p.relative_to(FIXTURE).as_posix() for p in (FIXTURE / "src/textkit").glob("*.py")
                     if p.name != "__init__.py")
    total, missing, incomplete, changed_code = 0, [], [], []
    for module in modules:
        try:
            tree = ast.parse((Path(repo) / module).read_text())
        except SyntaxError as err:
            return [check(f"{module} still parses", False, str(err))]
        for name, node in docstring_targets(tree):
            total += 1
            doc = ast.get_docstring(node)
            if not doc:
                missing.append(name)
            elif any(section not in doc for section in needs_sections(node)):
                incomplete.append(name)
        if strip_docstrings(tree) != strip_docstrings(ast.parse((FIXTURE / module).read_text())):
            changed_code.append(module)
    return [
        check("every public function, class and method has a docstring", not missing,
              f"{total - len(missing)}/{total} documented" + (f"; missing: {missing}" if missing else "")),
        check("docstrings have Args:/Returns: where the function takes or returns values", not missing and not incomplete,
              f"incomplete: {incomplete}" if incomplete else "all complete"),
        check("code is unchanged apart from docstrings", not changed_code,
              f"code changed in: {changed_code}" if changed_code else "all ASTs match the originals"),
        only_changed(repo, set(modules)),
        tests_pass(repo),
    ]


class AnnAssignToAssign(ast.NodeTransformer):
    def visit_AnnAssign(self, node):
        if node.value is None:
            return None
        return ast.Assign(targets=[node.target], value=node.value)


def strip_annotations(tree):
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    tree = AnnAssignToAssign().visit(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.returns = None
        elif isinstance(node, ast.arg):
            node.annotation = None
    return strip_docstrings(tree)


RESOLVE_HINTS = """
import ast, importlib, inspect, pathlib, sys, typing
bad = []
for path in sorted(pathlib.Path("src/textkit").glob("*.py")):
    if path.name == "__init__.py":
        continue
    module = importlib.import_module(f"textkit.{path.stem}")
    for name, obj in vars(module).items():
        if name.startswith("_") or getattr(obj, "__module__", None) != module.__name__:
            continue
        targets = [obj] if inspect.isfunction(obj) else [m for n, m in vars(obj).items() if inspect.isfunction(m) and not n.startswith("_")] if inspect.isclass(obj) else []
        for func in targets:
            try:
                typing.get_type_hints(func)
            except Exception as err:
                bad.append(f"{func.__qualname__}: {err}")
print("; ".join(bad))
sys.exit(1 if bad else 0)
"""


def resolve_hints(repo):
    repo = str(repo)
    cmd = [sys.executable, "-c", RESOLVE_HINTS]
    if SANDBOX:
        cmd = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               "--ro-bind", repo, repo, "--unshare-net", "--die-with-parent", "--chdir", repo, *cmd]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH="src")
    result = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, timeout=60, env=env)
    return result.returncode == 0, (result.stdout + result.stderr).strip()[-300:]


def check_typehints_all(repo):
    modules = sorted(p.relative_to(FIXTURE).as_posix() for p in (FIXTURE / "src/textkit").glob("*.py")
                     if p.name != "__init__.py")
    total, unannotated, changed_code = 0, [], []
    for module in modules:
        try:
            tree = ast.parse((Path(repo) / module).read_text())
        except SyntaxError as err:
            return [check(f"{module} still parses", False, str(err))]
        for name, node in docstring_targets(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            total += 1
            params = [a for a in node.args.args + node.args.kwonlyargs if a.arg != "self"]
            if node.returns is None or any(a.annotation is None for a in params):
                unannotated.append(name)
        if strip_annotations(tree) != strip_annotations(ast.parse((FIXTURE / module).read_text())):
            changed_code.append(module)
    resolved, problems = resolve_hints(repo)
    return [
        check("every public function and method has parameter and return annotations", not unannotated,
              f"{total - len(unannotated)}/{total} annotated" + (f"; missing: {unannotated}" if unannotated else "")),
        check("all annotations resolve", resolved, problems or "typing.get_type_hints works on every function"),
        check("code is unchanged apart from annotations and imports", not changed_code,
              f"code changed in: {changed_code}" if changed_code else "all ASTs match the originals"),
        only_changed(repo, set(modules)),
        tests_pass(repo),
    ]


def caught_mutants(repo, module, test_file):
    caught = []
    for name, edits in MUTANTS[module].items():
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(repo, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = copy / f"src/textkit/{module}.py"
            code = target.read_text()
            for old, new in edits:
                code = code.replace(old, new)
            target.write_text(code)
            mutant_ok, _ = run_pytest(copy, test_file)
            if not mutant_ok:
                caught.append(name)
    return caught


def uncalled(source, module):
    return [name for name in PUBLIC[module] if not re.search(rf"\b{name}\(", source)]


def collected(summary):
    return sum(int(n) for n in re.findall(r"(\d+) (?:passed|failed)", summary))


def check_tests(repo):
    test_file = Path(repo) / "tests/test_numbers.py"
    if not test_file.exists():
        return [check("tests/test_numbers.py exists", False, "file not created")]
    uncovered = uncalled(test_file.read_text(), "numbers")
    ok, summary = run_pytest(repo, "tests/test_numbers.py")
    caught = caught_mutants(repo, "numbers", "tests/test_numbers.py")
    missed = [name for name in MUTANTS["numbers"] if name not in caught]
    return [
        check("tests/test_numbers.py exists", True, "created"),
        check("tests call all five functions", not uncovered, f"not called: {uncovered}" if uncovered else "all called"),
        check("the new tests pass (at least 5 tests)", ok and collected(summary) >= 5, summary),
        check(f"tests catch at least 3 of {len(MUTANTS['numbers'])} planted bugs", len(caught) >= 3,
              f"caught {len(caught)}/{len(MUTANTS['numbers'])}" + (f"; missed: {missed}" if missed else "")),
        only_changed(repo, {"tests/test_numbers.py"}),
        tests_pass(repo),
    ]


def check_tests_all(repo):
    files = {module: f"tests/test_{module}.py" for module in PUBLIC}
    missing = [path for path in files.values() if not (Path(repo) / path).exists()]
    if missing:
        return [check("all three test files exist", False, f"not created: {missing}")]
    uncovered, caught, total = [], [], 0
    for module, path in files.items():
        uncovered += [f"{module}.{name}" for name in uncalled((Path(repo) / path).read_text(), module)]
        caught += [f"{module}: {name}" for name in caught_mutants(repo, module, path)]
        total += len(MUTANTS[module])
    ok, summary = run_pytest(repo, *files.values())
    need = -(-total * 3 // 4)
    missed = [f"{module}: {name}" for module in PUBLIC for name in MUTANTS[module] if f"{module}: {name}" not in caught]
    return [
        check("all three test files exist", True, "created"),
        check("tests call every public function, class and method", not uncovered,
              f"not called: {uncovered}" if uncovered else "all called"),
        check("the new tests pass (at least 20 tests)", ok and collected(summary) >= 20, summary),
        check(f"tests catch at least {need} of {total} planted bugs", len(caught) >= need,
              f"caught {len(caught)}/{total}" + (f"; missed: {missed}" if missed else "")),
        only_changed(repo, set(files.values())),
        tests_pass(repo),
    ]


def check_rename(repo):
    def count(pattern, root):
        return sum(len(re.findall(pattern, p.read_text(errors="replace"))) for p in text_files(root))

    left = [str(p.relative_to(repo)) for p in text_files(repo) if re.search(r"\bparse_row\b", p.read_text(errors="replace"))]
    users = ["src/textkit/report.py", "src/textkit/cli.py", "tests/test_records.py", "README.md"]
    not_updated = [u for u in users if "parse_record" not in (Path(repo) / u).read_text()]
    header_before = count(r"\bparse_rows_header\b", FIXTURE)
    header_after = count(r"\bparse_rows_header\b", repo)
    return [
        check("parse_row no longer appears anywhere", not left, f"still in: {left}" if left else "gone"),
        check("parse_record is defined and used everywhere",
              "def parse_record(" in (Path(repo) / "src/textkit/records.py").read_text() and not not_updated,
              f"not updated: {not_updated}" if not_updated else "defined in records.py, used in all four files"),
        check("parse_rows_header is untouched", header_after == header_before and count(r"parse_records_header", repo) == 0,
              f"{header_after} mentions (originally {header_before})"),
        only_changed(repo, {"src/textkit/records.py", *users}),
        tests_pass(repo),
    ]


def check_bug(repo):
    return [
        tests_pass(repo),
        only_changed(repo, {"src/textkit/cache.py"}),
    ]


def check_tiny(repo):
    tree = ast.parse((Path(repo) / "src/textkit/strings.py").read_text())
    func = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "count_words"), None)
    params = [a.arg for a in func.args.args] if func else []
    return [
        check("count_words takes `text` instead of `s`", params == ["text"], f"params: {params}"),
        only_changed(repo, {"src/textkit/strings.py"}),
        tests_pass(repo),
    ]


CHECKS = {"docstrings": check_docstrings, "docstrings_all": check_docstrings_all, "typehints_all": check_typehints_all,
          "tests": check_tests, "tests_all": check_tests_all, "rename": check_rename,
          "bug": check_bug, "tiny": check_tiny}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in CHECKS:
        sys.exit(f"usage: check.py {{{','.join(CHECKS)}}} REPO")
    results = CHECKS[sys.argv[1]](Path(sys.argv[2]).resolve())
    print(json.dumps({"task": sys.argv[1], "expectations": results}, indent=2))
    sys.exit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
