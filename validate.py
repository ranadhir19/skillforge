#!/usr/bin/env python3
"""Validation harness for the skillforge repository.

Usage:  python3 validate.py     (deterministic, offline, no network)

Stages, in order, each printing one PASS/FAIL line:
  1. import/compile  - compileall over the tree's Python sources, then
                       import the skillforge package (every module) and
                       the server package in a clean subprocess.
  2. test suite      - pytest over tests/ in a subprocess.
  3. employer scan   - the standing gate scanner over the repo's
                       sources; every candidate is judged in context
                       below. A real reference FAILs this stage.
  4. docs/results    - every path the README references exists; the
                       demo/experiment outputs exist; and every package
                       in library/ passes the platform's own static
                       validator.

Final line is exactly "HARNESS GREEN" (exit 0) or
"HARNESS RED: <stages>" (exit 1). See VALIDATION.md for what this
harness does and does not verify, and for the scan's judgement rules
(build artifacts and runtime data are generated, not sources, and are
out of scan scope; their sources are in scope).
"""

import compileall
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
GATE_SCANNER = Path(
    os.environ.get(
        "FIS_SCAN",
        Path.home() / "workspace" / "github-fis-watch" / "fis_scan.py",
    )
)
# This harness and its companion doc must name the gate they enforce,
# so they are excluded from the scan and reviewed by hand instead.
SCAN_EXCLUDE = {"validate.py", "VALIDATION.md"}
SCAN_PATHS = ["src", "library", "tests", "server", "frontend/src",
              "frontend/index.html", "frontend/package.json", "docs",
              "examples", "experiments", "README.md", "demo.py",
              "render.yaml", "pyproject.toml"]

FAILED = []


def report(stage, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {stage}" + (f" - {detail}" if detail else ""))
    if not ok:
        FAILED.append(stage)
    return ok


def project_packages():
    with open(ROOT / "pyproject.toml", "rb") as fh:
        name = tomllib.load(fh)["project"]["name"]
    top = name.replace("-", "_")
    pkgs = [top]
    base = SRC / top
    for mod in sorted(base.glob("*.py")):
        if mod.name != "__init__.py":
            pkgs.append(f"{top}.{mod.stem}")
    return name, pkgs


def stage_import_compile():
    targets = [SRC, ROOT / "tests", ROOT / "server",
               ROOT / "examples", ROOT / "experiments"]
    files = [ROOT / "demo.py"]
    ok = True
    for t in targets:
        if t.exists() and not compileall.compile_dir(str(t), quiet=1):
            ok = False
            print(f"    compile failed under {t.relative_to(ROOT)}")
    for f in files:
        if f.exists() and not compileall.compile_file(str(f), quiet=1):
            ok = False
            print(f"    compile failed: {f.name}")
    name, pkgs = project_packages()
    env = dict(os.environ, PYTHONPATH=f"{SRC}:{ROOT}")
    code = "; ".join(f"import {p}" for p in pkgs)
    code += "; import server.app; import server.schema"
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, env=env, cwd=str(ROOT))
    if proc.returncode != 0:
        ok = False
        print("    import errors:\n" + proc.stderr[-1500:])
    return report("1. import/compile", ok,
                  f"project {name}; imported {len(pkgs)} packages/modules + server")


def stage_tests():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=1800)
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    print("    pytest: " + tail)
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
        print(proc.stderr[-1500:])
    return report("2. test suite", proc.returncode == 0, tail)


def judge(hit):
    """Judge one scanner candidate in context. Returns (real, label)."""
    pattern, text = hit["pattern"], hit["text"]
    low = text.lower()
    if pattern in ("fisglobal", "fis-global", "fisglobal-domain"):
        return True, "REAL"
    if pattern == "Zenith-codename":
        if any(w in low for w in ("telescope", "astronom", "star", "sky")) \
                and not any(w in low for w in ("ai", "platform", "product")):
            return False, "BENIGN (astronomy)"
        return True, "REAL"
    if pattern == "FIS-word":
        if "affiliation" in low:
            return True, "USER-DECISION (affiliation)"
        return True, "REAL"
    # GOS-word and fis-path-segment have no benign use in this repo.
    return True, "REAL"


def stage_employer_scan():
    if not GATE_SCANNER.exists():
        return report("3. employer-reference scan", False,
                      f"scanner not found at {GATE_SCANNER}")
    paths = [str(ROOT / p) for p in SCAN_PATHS if (ROOT / p).exists()]
    proc = subprocess.run([sys.executable, str(GATE_SCANNER), *paths],
                          capture_output=True, text=True)
    hits, excluded = [], 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            h = json.loads(line)
            rel = os.path.relpath(h["file"], ROOT)
            if rel in SCAN_EXCLUDE:
                excluded += 1
            else:
                hits.append((rel, h))
    if excluded:
        print(f"    note: {excluded} candidate(s) inside validate.py / "
              "VALIDATION.md name the gate itself - excluded, judged "
              "benign, see VALIDATION.md")
    real = []
    for rel, h in hits:
        is_real, label = judge(h)
        print(f"    candidate {rel}:{h['line']} [{h['pattern']}] "
              f"-> {label}: {h['text'][:120]}")
        if is_real:
            real.append((rel, h, label))
    ok = not real
    detail = (f"{len(hits)} candidate(s), {len(real)} real"
              if hits else "0 candidates")
    return report("3. employer-reference scan", ok, detail)


REF_RE = re.compile(
    r"(?<![\w./-])((?:results|examples|experiments|docs|src)/[\w./<>*-]+"
    r"|demo\.py)(?![\w/-])")


def stage_docs_results():
    readmes = [ROOT / "README.md"] + sorted(ROOT.glob("*/README.md"))
    refs, missing = set(), []
    for rm in readmes:
        if not rm.exists():
            continue
        for m in REF_RE.finditer(rm.read_text(errors="replace")):
            refs.add(m.group(1).rstrip(".,;:"))
    for ref in sorted(refs):
        if "<" in ref or "*" in ref:
            continue
        if not (ROOT / ref).exists():
            missing.append(ref)
    for rel in ("demo.py", "examples/quickstart.py",
                "experiments/run_experiments.py", "results/results.md",
                "results/demo_run.json", "results/experiments.json",
                "docs/architecture.md", "docs/authoring-skills.md",
                "server/app.py", "server/schema.py", "render.yaml",
                "frontend/src/App.jsx", "frontend/package.json"):
        if not (ROOT / rel).exists():
            missing.append(rel)
    for m in missing:
        print(f"    missing: {m}")
    # The docs claim a statically valid starter library: check it.
    env = dict(os.environ, PYTHONPATH=str(SRC))
    code = (
        "from skillforge import Library, validate_package; "
        "lib = Library(['library']); "
        "bad = {p.name: validate_package(p.path).errors for p in lib.all() "
        "if not validate_package(p.path).valid}; "
        "print(f'{len(lib)} packages, {len(bad)} invalid'); "
        "raise SystemExit(1 if bad or len(lib) != 20 else 0)")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, env=env, cwd=str(ROOT))
    lib_ok = proc.returncode == 0
    print("    library: " + (proc.stdout.strip() or proc.stderr[-300:]))
    return report("4. results/docs consistency",
                  not missing and lib_ok,
                  f"{len(refs)} README references checked, "
                  f"{len(missing)} missing; library valid: {lib_ok}")


def main():
    print(f"validate.py - {ROOT.name} ({ROOT})")
    stage_import_compile()
    stage_tests()
    stage_employer_scan()
    stage_docs_results()
    if FAILED:
        print("HARNESS RED: " + ", ".join(FAILED))
        return 1
    print("HARNESS GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
