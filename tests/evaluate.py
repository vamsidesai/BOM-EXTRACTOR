"""Score extraction results against tests/make_samples.py ground truth.

    python tests/evaluate.py samples/ results/
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def score(truth: dict, res: dict) -> dict:
    out = {"file": truth["file"], "checks": 0, "passed": 0, "failures": []}

    def check(name, expected, got, contains=False):
        out["checks"] += 1
        ok = norm(expected) in norm(got) if contains else norm(expected) == norm(got)
        if ok:
            out["passed"] += 1
        else:
            out["failures"].append(f"{name}: expected {expected!r} got {got!r}")

    s = res["summary"]
    for k, v in truth["title_block"].items():
        check(f"title.{k}", v, s.get(k), contains=k == "projection")
    got_bom = {norm(r["item"]).lstrip("0"): r for r in res["bom"]}
    check("bom.row_count", len(truth["bom"]), len(res["bom"]))
    for row in truth["bom"]:
        g = got_bom.get(norm(row["item"]).lstrip("0"), {})
        for k, v in row.items():
            if v:
                check(f"bom[{row['item']}].{k}", v, g.get(k))
    check("revisions", ",".join(truth["revisions"]), ",".join(r["rev"] or "" for r in res["revisions"]))
    sp = truth.get("specs", {})
    if sp.get("material_callout"):
        check("spec.material", sp["material_callout"], s.get("material_callout"), contains=True)
    for v in sp.get("surface_finish", []):
        check("spec.finish", v, s.get("surface_finish"), contains=True)
    for v in sp.get("heat_treatment", []):
        check("spec.heat", v, s.get("heat_treatment"), contains=True)
    out["accuracy"] = round(out["passed"] / out["checks"], 4) if out["checks"] else None
    return out


def main(samples: str, results: str) -> int:
    truths = json.loads((Path(samples) / "ground_truth.json").read_text())
    tot_c = tot_p = 0
    for t in truths:
        hits = list(Path(results).rglob(f"{t['file']}.json"))
        if not hits:
            print(f"{t['file']}: NO RESULT")
            continue
        r = score(t, json.loads(hits[0].read_text()))
        tot_c += r["checks"]
        tot_p += r["passed"]
        print(f"{t['file']:28s} {r['passed']:3d}/{r['checks']:3d}  ({r['accuracy']:.1%})")
        for f in r["failures"]:
            print(f"    - {f}")
    if tot_c:
        print(f"{'OVERALL':28s} {tot_p:3d}/{tot_c:3d}  ({tot_p / tot_c:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
