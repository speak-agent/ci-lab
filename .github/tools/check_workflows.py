#!/usr/bin/env python3
"""Check the workflows of a validation pull request against the lab's resource rules.

The rules are stated in README.md ("Resource rules"). This program checks the ones a
workflow file can show; the others (what a probe prints, how a pull request is closed)
are the author's and the reviewer's.

Usage: check_workflows.py [--macos-budget N] [WORKFLOW_DIR]
Exit status: 0 when every rule holds, 1 when one does not, 2 when a file cannot be read.
"""

import argparse
import itertools
import pathlib
import re
import sys

import yaml

GUARD = "guard.yml"
ALLOWED_TRIGGERS = {"pull_request", "workflow_dispatch"}
MAX_JOB_MINUTES = 360
MATRIX_REF = re.compile(r"\$\{\{\s*matrix\.([A-Za-z0-9_-]+)\s*\}\}")


def is_macos_label(value):
    text = str(value).lower()
    return text.startswith("macos") or text.startswith("xcode")


def triggers_of(doc):
    # PyYAML reads the bare key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    if isinstance(on, dict):
        return set(on)
    return set()


def runner_legs(job):
    """Return (macos_legs, total_legs) for one job.

    A literal `runs-on` is one leg. A `runs-on` that names `matrix.<key>` is expanded
    over the matrix: every value of <key> in the list form is multiplied by the other
    list-valued keys, and every `include` entry adds one leg. `exclude` is ignored, so
    the count can only be too high, never too low.
    """
    runs_on = job.get("runs-on", "")
    labels = runs_on if isinstance(runs_on, list) else [runs_on]
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    if not isinstance(matrix, dict):
        matrix = {}
    keys = sorted({k for label in labels for k in MATRIX_REF.findall(str(label))})
    if not keys:
        mac = any(is_macos_label(label) for label in labels)
        return (1 if mac else 0), 1

    lists = {k: v for k, v in matrix.items()
             if k not in ("include", "exclude") and isinstance(v, list)}
    macos = total = 0
    if lists:
        names = sorted(lists)
        for combo in itertools.product(*(lists[n] for n in names)):
            row = dict(zip(names, combo))
            if not all(k in row for k in keys):
                continue
            total += 1
            if any(is_macos_label(row[k]) for k in keys):
                macos += 1
    for entry in matrix.get("include") or []:
        if not isinstance(entry, dict) or not any(k in entry for k in keys):
            continue
        total += 1
        if any(is_macos_label(entry.get(k, "")) for k in keys):
            macos += 1
    return macos, total


def check_file(path, problems):
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as err:
        print(f"{path.name}: cannot be read: {err}")
        sys.exit(2)

    triggers = triggers_of(doc)
    extra = sorted(str(t) for t in triggers - ALLOWED_TRIGGERS)
    if extra:
        problems.append(f"{path.name}: triggers {extra}; a validation runs on "
                        "pull_request or workflow_dispatch only")
    if not triggers:
        problems.append(f"{path.name}: declares no trigger")

    concurrency = doc.get("concurrency")
    group = concurrency.get("group", "") if isinstance(concurrency, dict) else str(concurrency or "")
    if "github.ref" not in group and "github.head_ref" not in group:
        problems.append(f"{path.name}: needs a workflow-level `concurrency` whose group "
                        "names github.ref or github.head_ref")

    macos = 0
    for name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        minutes = job.get("timeout-minutes")
        if not isinstance(minutes, int) or not 0 < minutes <= MAX_JOB_MINUTES:
            problems.append(f"{path.name}: job `{name}` needs an integer `timeout-minutes` "
                            f"in 1..{MAX_JOB_MINUTES}")
        job_macos, _ = runner_legs(job)
        macos += job_macos
        if job_macos:
            for step in job.get("steps") or []:
                uses = str((step or {}).get("uses", ""))
                if uses.startswith("actions/upload-artifact"):
                    problems.append(f"{path.name}: job `{name}` uploads an artifact on macOS; "
                                    "readings go to the log and the step summary")
    return macos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--macos-budget", type=int, default=3)
    parser.add_argument("workflow_dir", nargs="?", default=".github/workflows")
    args = parser.parse_args()

    directory = pathlib.Path(args.workflow_dir)
    files = sorted(p for p in directory.glob("*.y*ml") if p.name != GUARD)
    problems = []
    macos = sum(check_file(p, problems) for p in files)
    if macos > args.macos_budget:
        problems.append(f"{macos} macOS legs across the pull request; the budget is "
                        f"{args.macos_budget} (5 per account, shared with every repository)")

    print(f"checked {len(files)} workflow file(s); macOS legs: {macos}/{args.macos_budget}")
    for problem in problems:
        print(f"RULE: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
