#!/usr/bin/env python3
"""Analyze JSONL output from the when-tdd-pays experiment.

Usage:
  python3 scripts/analyze_tdd_pays.py --data docs/experiments/data/tdd-pays-*.jsonl
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


# ── helpers ──────────────────────────────────────────────────────────────────

def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{v*100:.0f}%"


def fmt_f(v, digits=1):
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def _mean_safe(vals):
    vals = [v for v in vals if v is not None]
    return mean(vals) if vals else None


def _stdev_safe(vals):
    vals = [v for v in vals if v is not None]
    return stdev(vals) if len(vals) > 1 else None


# ── stage-level aggregation ───────────────────────────────────────────────────

def stage0_summary(rows: list[dict]) -> dict:
    """Summarise stage0 rows by (task, arm, clarity) cell."""
    from collections import defaultdict
    cells: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r.get("stage") != "stage0":
            continue
        key = (r["task"], r["arm"], r["clarity"])
        cells[key].append(r)

    out = {}
    for key, cell_rows in sorted(cells.items()):
        task, arm, clarity = key
        core_passes = [r["core_passed"] for r in cell_rows]
        edge_passes = [r["edge_passed"] for r in cell_rows]
        costs = [r.get("cost", {}).get("cost_usd") for r in cell_rows
                 if isinstance(r.get("cost"), dict)]
        out[key] = {
            "n": len(cell_rows),
            "core_pass_rate": mean(core_passes) if core_passes else None,
            "edge_pass_rate": mean(edge_passes) if edge_passes else None,
            "mean_cost_usd": _mean_safe(costs),
        }
    return out


def change_summary(rows: list[dict]) -> dict:
    """Summarise change-stage rows by (task, arm, clarity, stage) cell."""
    cells: dict[tuple, list] = defaultdict(list)
    for r in rows:
        stage = r.get("stage", "")
        if not stage.startswith("change"):
            continue
        key = (r["task"], r["arm"], r["clarity"], stage)
        cells[key].append(r)

    out = {}
    for key, cell_rows in sorted(cells.items()):
        task, arm, clarity, stage = key
        passes = [r["passed"] for r in cell_rows]
        blast_files = [r.get("blast_radius", {}).get("files_changed")
                       for r in cell_rows if r.get("blast_radius")]
        blast_lines = [r.get("blast_radius", {}).get("lines_added", 0)
                       + r.get("blast_radius", {}).get("lines_deleted", 0)
                       for r in cell_rows if r.get("blast_radius")]
        costs = [r.get("cost", {}).get("cost_usd") for r in cell_rows
                 if isinstance(r.get("cost"), dict)]
        out[key] = {
            "n": len(cell_rows),
            "pass_rate": mean(passes) if passes else None,
            "mean_files_changed": _mean_safe(blast_files),
            "mean_lines_changed": _mean_safe(blast_lines),
            "mean_cost_usd": _mean_safe(costs),
        }
    return out


def cell_cost_summary(rows: list[dict]) -> dict:
    """Total cost per (task, arm, clarity) cell across all stages."""
    cells: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = (r["task"], r["arm"], r["clarity"])
        c = r.get("cost", {})
        if isinstance(c, dict):
            usd = c.get("cost_usd")
            if usd is not None:
                cells[key].append(usd)

    out = {}
    for key, costs in sorted(cells.items()):
        out[key] = {"cost_usd": sum(costs), "n_stages": len(costs)}
    return out


def cumulative_changeability(rows: list[dict]) -> dict:
    """Sum blast-radius (lines changed) across the 3 change stages per cell."""
    cells: dict[tuple, list] = defaultdict(list)
    for r in rows:
        stage = r.get("stage", "")
        if not stage.startswith("change"):
            continue
        key = (r["task"], r["arm"], r["clarity"], r["trial"])
        blast = r.get("blast_radius", {})
        lines = blast.get("lines_added", 0) + blast.get("lines_deleted", 0)
        cells[key].append(lines)

    out: dict[tuple, dict] = {}
    for key, line_changes in sorted(cells.items()):
        task, arm, clarity, trial = key
        cell_key = (task, arm, clarity)
        out.setdefault(cell_key, []).append(sum(line_changes))

    summary = {}
    for cell_key, cum_changes in sorted(out.items()):
        summary[cell_key] = {
            "n": len(cum_changes),
            "mean": _mean_safe(cum_changes),
            "stdev": _stdev_safe(cum_changes),
        }
    return summary


def arm_clarity_grid(summary_fn, rows, metric_key, fmt_fn=fmt_f) -> str:
    """Render a grid: rows=arms, cols=clarity, cells=metric."""
    data = summary_fn(rows)
    arms = sorted({k[1] for k in data})
    clarities = sorted({k[2] for k in data})
    # tasks as separate sections
    tasks = sorted({k[0] for k in data})

    lines = []
    for task in tasks:
        lines.append(f"\n### {task}\n")
        header = "| arm | " + " | ".join(clarities) + " |"
        sep = "|-----|" + "------|" * len(clarities)
        lines.append(header)
        lines.append(sep)
        for arm in arms:
            row_parts = [arm]
            for clarity in clarities:
                key = (task, arm, clarity)
                v = data.get(key, {}).get(metric_key)
                row_parts.append(fmt_fn(v))
            lines.append("| " + " | ".join(row_parts) + " |")
    return "\n".join(lines)


# ── RQ verdicts ───────────────────────────────────────────────────────────────

def rq_a_verdict(rows: list[dict]) -> str:
    """RQ-A: EDGE pass-rate under vague spec (tdd-refactor vs test-after)."""
    cells: dict[tuple, list[bool]] = defaultdict(list)
    for r in rows:
        if r.get("stage") != "stage0" or r.get("clarity") != "vague":
            continue
        arm = r["arm"]
        if arm not in ("tdd-refactor", "test-after"):
            continue
        cells[(r["task"], arm)].append(r["edge_passed"])

    lines = ["#### EDGE pass-rate under vague spec (stage0)\n"]
    lines.append("| task | tdd-refactor | test-after | Δ |")
    lines.append("|------|-------------|------------|---|")
    tasks = sorted({k[0] for k in cells})
    tdd_rates, ta_rates = [], []
    for task in tasks:
        tdd = cells.get((task, "tdd-refactor"), [])
        ta = cells.get((task, "test-after"), [])
        tdd_rate = mean(tdd) if tdd else None
        ta_rate = mean(ta) if ta else None
        delta = (tdd_rate - ta_rate) if (tdd_rate is not None and ta_rate is not None) else None
        if tdd_rate is not None:
            tdd_rates.append(tdd_rate)
        if ta_rate is not None:
            ta_rates.append(ta_rate)
        lines.append(f"| {task} | {fmt_pct(tdd_rate)} (n={len(tdd)}) | "
                     f"{fmt_pct(ta_rate)} (n={len(ta)}) | "
                     f"{fmt_pct(delta) if delta is not None else '—'} |")

    if tdd_rates and ta_rates:
        avg_tdd = mean(tdd_rates)
        avg_ta = mean(ta_rates)
        delta = avg_tdd - avg_ta
        verdict = "tdd-refactor > test-after" if delta > 0.05 else (
            "test-after > tdd-refactor" if delta < -0.05 else "no clear difference")
        lines.append(f"\n**Pooled**: tdd-refactor {fmt_pct(avg_tdd)} vs test-after {fmt_pct(avg_ta)} → **{verdict}**")
    else:
        lines.append("\n_Insufficient data for verdict._")

    return "\n".join(lines)


def rq_b_verdict(rows: list[dict]) -> str:
    """RQ-B: Cumulative changeability (lines changed across 3 changes)."""
    cum = cumulative_changeability(rows)
    if not cum:
        return "_Insufficient data for RQ-B verdict._"

    # Pool across tasks, compare arms
    arm_cum: dict[str, list[float]] = defaultdict(list)
    for (task, arm, clarity), v in cum.items():
        if v["mean"] is not None:
            arm_cum[arm].append(v["mean"])

    lines = ["#### Cumulative lines changed across 3-change chain\n"]
    lines.append("| arm | mean Δlines | n cells |")
    lines.append("|-----|-------------|---------|")
    for arm in sorted(arm_cum):
        vals = arm_cum[arm]
        lines.append(f"| {arm} | {fmt_f(mean(vals), 0)} | {len(vals)} |")

    arms_sorted = sorted(arm_cum, key=lambda a: mean(arm_cum[a]))
    if len(arms_sorted) >= 2:
        best = arms_sorted[0]
        worst = arms_sorted[-1]
        lines.append(f"\n**Verdict**: {best} has least churn ({fmt_f(mean(arm_cum[best]),0)} lines); "
                     f"{worst} has most ({fmt_f(mean(arm_cum[worst]),0)} lines).")
    return "\n".join(lines)


def rq_b2_verdict(rows: list[dict]) -> str:
    """RQ-B2: tdd-no-refactor vs test-after isolation."""
    cum = cumulative_changeability(rows)
    tdd_nr = [v["mean"] for (t, a, c), v in cum.items()
              if a == "tdd-no-refactor" and v["mean"] is not None]
    ta = [v["mean"] for (t, a, c), v in cum.items()
          if a == "test-after" and v["mean"] is not None]

    if not tdd_nr or not ta:
        return "_Insufficient data for RQ-B2 verdict._"

    m_nr = mean(tdd_nr)
    m_ta = mean(ta)
    delta = m_ta - m_nr
    direction = ("test-after costs more churn" if delta > 10 else
                 "tdd-no-refactor costs more churn" if delta < -10 else
                 "no clear difference")
    return (f"**RQ-B2 (TDD vs tests-after, no refactor)**:\n"
            f"tdd-no-refactor mean Δlines={fmt_f(m_nr,0)} (n={len(tdd_nr)}), "
            f"test-after mean Δlines={fmt_f(m_ta,0)} (n={len(ta)}) → **{direction}** (Δ={fmt_f(delta,0)} lines)")


def rq_c_verdict(rows: list[dict]) -> str:
    """RQ-C: Is the tdd-refactor advantage largest under vague+open-design?"""
    cum = cumulative_changeability(rows)

    # Split by clarity
    tdd_vague = [v["mean"] for (t, a, c), v in cum.items()
                 if a == "tdd-refactor" and c == "vague" and v["mean"] is not None]
    ta_vague = [v["mean"] for (t, a, c), v in cum.items()
                if a == "test-after" and c == "vague" and v["mean"] is not None]
    tdd_clear = [v["mean"] for (t, a, c), v in cum.items()
                 if a == "tdd-refactor" and c == "clear" and v["mean"] is not None]
    ta_clear = [v["mean"] for (t, a, c), v in cum.items()
                if a == "test-after" and c == "clear" and v["mean"] is not None]

    lines = ["**RQ-C (interaction: clarity × workflow)**"]
    if tdd_vague and ta_vague:
        d_vague = mean(ta_vague) - mean(tdd_vague)
        lines.append(f"- vague spec Δ (test-after − tdd-refactor): {fmt_f(d_vague,0)} lines")
    if tdd_clear and ta_clear:
        d_clear = mean(ta_clear) - mean(tdd_clear)
        lines.append(f"- clear spec Δ (test-after − tdd-refactor): {fmt_f(d_clear,0)} lines")

    if tdd_vague and ta_vague and tdd_clear and ta_clear:
        d_v = mean(ta_vague) - mean(tdd_vague)
        d_c = mean(ta_clear) - mean(tdd_clear)
        if d_v > d_c + 5:
            lines.append("→ **Interaction confirmed**: tdd-refactor advantage is larger under vague spec.")
        elif d_c > d_v + 5:
            lines.append("→ **Reversed**: tdd-refactor advantage is larger under clear spec.")
        else:
            lines.append("→ **No clear interaction**: advantage similar across clarity levels.")
    else:
        lines.append("→ _Insufficient data for interaction verdict._")

    return "\n".join(lines)


def review_summary(rows: list[dict]) -> str:
    """Summarise multi-rater review scores at last change stage."""
    arm_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        stage = r.get("stage", "")
        if not stage.startswith("change"):
            continue
        rev = r.get("multi_rater_review", {})
        if not rev:
            continue
        arm = r["arm"]
        for dim, d in rev.items():
            m = d.get("mean")
            if m is not None:
                arm_scores[arm][dim].append(m)

    if not arm_scores:
        return "_No review data yet._"

    dims = sorted({d for arm_d in arm_scores.values() for d in arm_d})
    lines = ["| arm | " + " | ".join(dims) + " |"]
    lines.append("|-----|" + "------|" * len(dims))
    for arm in sorted(arm_scores):
        row_parts = [arm]
        for dim in dims:
            vals = arm_scores[arm][dim]
            row_parts.append(fmt_f(mean(vals), 2) if vals else "—")
        lines.append("| " + " | ".join(row_parts) + " |")
    return "\n".join(lines)


def radon_summary(rows: list[dict]) -> str:
    """Radon avg_cc and avg_mi by arm (last change stage, where available)."""
    arm_cc: dict[str, list[float]] = defaultdict(list)
    arm_mi: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        stage = r.get("stage", "")
        # Prefer last change stage; fall back to stage0
        if stage not in ("change3", "stage0"):
            continue
        radon = r.get("radon", {})
        if not radon:
            continue
        arm = r["arm"]
        cc = radon.get("avg_cc")
        mi = radon.get("avg_mi")
        if cc is not None:
            arm_cc[arm].append(cc)
        if mi is not None:
            arm_mi[arm].append(mi)

    if not arm_cc:
        return "_No radon data yet._"

    arms = sorted(set(list(arm_cc.keys()) + list(arm_mi.keys())))
    lines = ["| arm | avg_cc (mean) | avg_mi (mean) | n |"]
    lines.append("|-----|--------------|---------------|---|")
    for arm in arms:
        ccs = arm_cc.get(arm, [])
        mis = arm_mi.get(arm, [])
        n = max(len(ccs), len(mis))
        lines.append(f"| {arm} | {fmt_f(mean(ccs),2) if ccs else '—'} | "
                     f"{fmt_f(mean(mis),1) if mis else '—'} | {n} |")
    return "\n".join(lines)


def cost_summary(rows: list[dict]) -> str:
    """Per-arm cost summary across all stages."""
    arm_costs: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        c = r.get("cost", {})
        if isinstance(c, dict):
            usd = c.get("cost_usd")
            if usd:
                arm_costs[r["arm"]].append(usd)

    if not arm_costs:
        return "_No cost data._"

    arms = sorted(arm_costs)
    lines = ["| arm | total cost | mean/stage | n stages |"]
    lines.append("|-----|------------|------------|----------|")
    for arm in arms:
        costs = arm_costs[arm]
        lines.append(f"| {arm} | ${sum(costs):.2f} | ${mean(costs):.2f} | {len(costs)} |")
    return "\n".join(lines)


def data_coverage(rows: list[dict]) -> str:
    """Show how many cells are complete per (task, arm, clarity)."""
    cells: dict[tuple, set] = defaultdict(set)
    for r in rows:
        key = (r["task"], r["arm"], r["clarity"])
        cells[key].add(r.get("trial", 0))

    lines = ["| task | arm | clarity | trials complete |"]
    lines.append("|------|-----|---------|----------------|")
    for key in sorted(cells):
        task, arm, clarity = key
        lines.append(f"| {task} | {arm} | {clarity} | {len(cells[key])} |")
    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", nargs="+", required=True, help="JSONL data files")
    ap.add_argument("--out", default="", help="output Markdown file (default: stdout)")
    args = ap.parse_args(argv)

    paths = []
    for pat in args.data:
        for p in sorted(Path(".").glob(pat)) or [Path(pat)]:
            if p.is_file():
                paths.append(p)
    if not paths:
        print("error: no data files found", file=sys.stderr)
        return 2

    rows = load_rows(paths)
    if not rows:
        print("error: no rows found in data files", file=sys.stderr)
        return 2

    tasks = sorted({r["task"] for r in rows})
    arms = sorted({r["arm"] for r in rows})
    n_rows = len(rows)
    print(f"Loaded {n_rows} rows  |  tasks: {tasks}  |  arms: {arms}", file=sys.stderr)

    out_lines = []

    out_lines.append("## Data Coverage\n")
    out_lines.append(data_coverage(rows))

    out_lines.append("\n\n## Stage-0 CORE and EDGE pass rates\n")
    s0 = stage0_summary(rows)
    tasks_list = sorted({k[0] for k in s0})
    arms_list = sorted({k[1] for k in s0})
    clarities_list = sorted({k[2] for k in s0})

    for metric, label in [("core_pass_rate", "CORE"), ("edge_pass_rate", "EDGE")]:
        out_lines.append(f"\n### {label} pass rate\n")
        out_lines.append("| task | arm | clarity | pass rate | n |")
        out_lines.append("|------|-----|---------|-----------|---|")
        for key in sorted(s0):
            task, arm, clarity = key
            v = s0[key]
            out_lines.append(f"| {task} | {arm} | {clarity} | "
                             f"{fmt_pct(v[metric])} | {v['n']} |")

    out_lines.append("\n\n## Change-stage pass rates\n")
    cs = change_summary(rows)
    out_lines.append("| task | arm | clarity | stage | pass rate | files | Δlines | n |")
    out_lines.append("|------|-----|---------|-------|-----------|-------|--------|---|")
    for key in sorted(cs):
        task, arm, clarity, stage = key
        v = cs[key]
        out_lines.append(f"| {task} | {arm} | {clarity} | {stage} | "
                         f"{fmt_pct(v['pass_rate'])} | "
                         f"{fmt_f(v['mean_files_changed'],1)} | "
                         f"{fmt_f(v['mean_lines_changed'],0)} | {v['n']} |")

    out_lines.append("\n\n## RQ-A: Contract inference under vague spec\n")
    out_lines.append(rq_a_verdict(rows))

    out_lines.append("\n\n## RQ-B: Cumulative changeability\n")
    out_lines.append(rq_b_verdict(rows))

    out_lines.append("\n\n## RQ-B2: TDD-no-refactor vs test-after isolation\n")
    out_lines.append(rq_b2_verdict(rows))

    out_lines.append("\n\n## RQ-C: Clarity × workflow interaction\n")
    out_lines.append(rq_c_verdict(rows))

    out_lines.append("\n\n## Multi-rater review scores\n")
    out_lines.append(review_summary(rows))

    out_lines.append("\n\n## Radon structural metrics (last change stage)\n")
    out_lines.append(radon_summary(rows))

    out_lines.append("\n\n## Cost summary\n")
    out_lines.append(cost_summary(rows))

    content = "\n".join(out_lines)

    if args.out:
        Path(args.out).write_text(content)
        print(f"Written to {args.out}", file=sys.stderr)
    else:
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
