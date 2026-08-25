"""Unit tests for skills/code-review/scripts/change_impact.py.

The gate must drop `arch-review` only when it can PROVE the diff moved no
boundary — and must keep it on every input it cannot classify. A false skip
is a silent coverage hole; a false keep only costs a dispatch.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import change_impact


def _diff(path, added=(), removed=(), header_extra=()):
    lines = [f"diff --git a/{path} b/{path}"]
    lines += list(header_extra)
    lines += [f"--- a/{path}", f"+++ b/{path}", "@@ -1,4 +1,5 @@", " context"]
    lines += [f"-{ln}" for ln in removed]
    lines += [f"+{ln}" for ln in added]
    return "\n".join(lines) + "\n"


BODY_ONLY = _diff(
    "src/pricing.js",
    added=["  if (total < 0) throw new RangeError('negative total')"],
)


class TestNoArchitecturalImpact:
    def test_a_guard_clause_added_inside_a_function_skips_arch_review(self):
        result = change_impact.evaluate(BODY_ONLY)
        assert set(result["skipLenses"]) == {"arch-review", "concurrency-review"}
        assert result["hasArchitecturalImpact"] is False

    def test_a_pure_value_change_skips_arch_review(self):
        result = change_impact.evaluate(
            _diff("src/config.js", removed=["  const RETRIES = 3"], added=["  const RETRIES = 5"])
        )
        assert set(result["skipLenses"]) == {"arch-review", "concurrency-review"}

    def test_a_comment_only_change_skips_arch_review(self):
        result = change_impact.evaluate(_diff("src/a.js", added=["  // clarify intent"]))
        assert set(result["skipLenses"]) == {"arch-review", "concurrency-review"}


class TestArchitecturalSignals:
    @pytest.mark.parametrize(
        "line",
        [
            "import { Repo } from '../infra/repo'",
            "from app.infra.db import Session",
            "using System.Data.SqlClient;",
            "#include <vector>",
            "use crate::infra::db;",
            "const db = require('./db')",
            "export { thing } from './other'",
        ],
    )
    def test_an_added_import_is_a_dependency_signal(self, line):
        result = change_impact.evaluate(_diff("src/domain/order.ts", added=[line]))
        assert "dependency" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}

    def test_a_removed_import_also_counts(self):
        result = change_impact.evaluate(_diff("src/a.ts", removed=["import { X } from './x'"]))
        assert "dependency" in result["signals"]

    def test_a_new_file_is_a_structure_signal(self):
        result = change_impact.evaluate(
            _diff("src/new_module.ts", added=["const a = 1"], header_extra=["new file mode 100644"])
        )
        assert "structure" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}

    def test_a_deleted_file_is_a_structure_signal(self):
        result = change_impact.evaluate(
            _diff("src/gone.ts", removed=["const a = 1"], header_extra=["deleted file mode 100644"])
        )
        assert "structure" in result["signals"]

    def test_a_rename_is_a_structure_signal(self):
        result = change_impact.evaluate(
            _diff("src/b.ts", header_extra=["rename from src/a.ts", "rename to src/b.ts"])
        )
        assert "structure" in result["signals"]

    @pytest.mark.parametrize(
        "line",
        [
            "export function createOrder() {}",
            "public class OrderService {}",
            "public interface Repo {}",
            "module.exports = { a }",
            "__all__ = ['Order']",
            "class OrderAggregate:",
        ],
    )
    def test_a_public_surface_change_is_an_interface_signal(self, line):
        result = change_impact.evaluate(_diff("src/domain/order.ts", added=[line]))
        assert "interface" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}

    @pytest.mark.parametrize(
        "path",
        ["package.json", "pyproject.toml", "go.mod", "pom.xml", "src/App.csproj", "Cargo.toml"],
    )
    def test_a_dependency_manifest_change_is_a_manifest_signal(self, path):
        result = change_impact.evaluate(_diff(path, added=['  "left-pad": "1.0.0"']))
        assert "manifest" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}

    @pytest.mark.parametrize(
        "path",
        [
            "Dockerfile",
            "docker-compose.yml",
            "terraform/main.tf",
            "k8s/deploy.yaml",
            ".github/workflows/ci.yml",
            "helm/values.yaml",
        ],
    )
    def test_an_infra_change_is_an_infra_signal(self, path):
        result = change_impact.evaluate(_diff(path, added=["  replicas: 3"]))
        assert "infra" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}

    def test_an_adr_change_is_an_adr_signal(self):
        result = change_impact.evaluate(
            _diff("docs/adr/0031-use-outbox.md", added=["We will use the outbox pattern."])
        )
        assert "adr" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}


class TestFailSafe:
    def test_unparseable_input_assumes_impact(self):
        result = change_impact.evaluate("this is not a diff")
        assert result["skipLenses"] == []
        assert result["hasArchitecturalImpact"] is True
        assert result["reason"] == "diff-not-parseable-assuming-impact"

    def test_empty_input_assumes_impact(self):
        result = change_impact.evaluate("")
        assert result["skipLenses"] == []
        assert result["hasArchitecturalImpact"] is True

    def test_extra_files_can_supply_a_signal_the_diff_body_lacks(self):
        result = change_impact.evaluate(BODY_ONLY, extra_files=["Dockerfile"])
        assert "infra" in result["signals"]
        assert set(result["skipLenses"]) == {"concurrency-review"}

    def test_a_mixed_diff_keeps_the_lens_when_any_file_carries_signal(self):
        combined = BODY_ONLY + _diff("package.json", added=['  "x": "1"'])
        assert set(change_impact.evaluate(combined)["skipLenses"]) == {"concurrency-review"}


class TestConcurrencyGate:
    """`concurrency-review` runs only when the diff touches a concurrency
    primitive (#1975). Breadth is the safe direction: a miss silently drops
    the only lens that reviews races, so these tests pin the *keep* cases
    across every language family the pattern claims to cover."""

    @pytest.mark.parametrize(
        "line",
        [
            "        async with self._lock:",          # Python
            "    await self.flush()",                   # Python / JS
            "    const [a, b] = await Promise.all([x, y])",  # JS
            "    executor = ThreadPoolExecutor(max_workers=4)",  # Python
            "    private volatile boolean ready;",      # Java
            "    ExecutorService pool = newFixedThreadPool(2);",  # Java
            "    lock (_gate) { _count++; }",           # C#
            "    Interlocked.Increment(ref _count);",   # C#
            "    results := make(chan int, 8)",         # Go
            "    go func() { work() }()",               # Go
            "    var wg sync.WaitGroup",                # Go
            "    let guard = Arc<Mutex<State>>::new();",  # Rust
        ],
    )
    def test_a_concurrency_primitive_keeps_the_lens(self, line):
        result = change_impact.evaluate(_diff("src/worker.py", added=[line]))
        assert "concurrency" in result["signals"]
        assert "concurrency-review" not in result["skipLenses"]

    @pytest.mark.parametrize(
        "line",
        [
            "    with self._lock:",                 # the most common Python form
            "    self.lock.acquire()",
            "    mutex.unlock()",
            "    q = queue.Queue()",
            "    go worker()",                      # Go statement on a named func
            "    let a = Arc::new(state);",         # Rust, non-generic form
            "    # ordering matters here to avoid a deadlock",
        ],
    )
    def test_forms_an_earlier_pattern_missed(self, line):
        """Regression: each of these is a real concurrency primitive the
        first draft of the pattern did not match. A false negative silently
        drops the only lens that reviews races, so they are pinned."""
        result = change_impact.evaluate(_diff("src/worker.py", added=[line]))
        assert "concurrency" in result["signals"], f"missed: {line!r}"

    @pytest.mark.parametrize(
        "line",
        [
            "    parse_block(data)",   # 'lock' inside 'block'
            "    self.blocked = True",
            "    clock = time.time()",
            "    total = price * qty",
        ],
    )
    def test_lookalike_words_do_not_trip_the_pattern(self, line):
        """Breadth is the safe direction, but not at the cost of firing on
        every occurrence of 'block' — which would keep the lens on nearly
        every diff and erase the saving."""
        result = change_impact.evaluate(_diff("src/pricing.py", added=[line]))
        assert "concurrency" not in result["signals"], f"false positive: {line!r}"

    def test_removing_a_lock_also_counts(self):
        """Deleting synchronization is the change most likely to introduce a
        race — it must never read as 'no concurrency in this diff'."""
        result = change_impact.evaluate(
            _diff("src/Counter.java", removed=["    synchronized (this) {"])
        )
        assert "concurrency" in result["signals"]
        assert "concurrency-review" not in result["skipLenses"]

    def test_a_diff_with_no_concurrency_primitive_drops_the_lens(self):
        assert "concurrency-review" in change_impact.evaluate(BODY_ONLY)["skipLenses"]

    def test_a_concurrency_only_diff_reports_no_architectural_impact(self):
        """The signal sets are independent: adding a lock inside an existing
        function moves no boundary, so arch-review still drops and
        `hasArchitecturalImpact` must keep meaning what its name says."""
        result = change_impact.evaluate(
            _diff("src/worker.py", added=["        async with self._lock:"])
        )
        assert result["signals"] == ["concurrency"]
        assert result["hasArchitecturalImpact"] is False
        assert result["skipLenses"] == ["arch-review"]

    def test_an_architectural_only_diff_drops_the_concurrency_lens(self):
        result = change_impact.evaluate(_diff("src/a.ts", added=["import { X } from './x'"]))
        assert result["skipLenses"] == ["concurrency-review"]

    def test_both_signals_present_keeps_every_lens_and_names_the_reason(self):
        """The `reason` string is the only report of *why* nothing was
        gated, and it was renamed when the map grew past one lens — pin it
        together with the empty skip list it describes."""
        result = change_impact.evaluate(
            _diff("src/worker.py",
                  added=["import asyncio", "        async with self._lock:"])
        )
        assert result["skipLenses"] == []
        assert result["reason"] == "gating-signal-present"

    def test_unparseable_input_keeps_the_concurrency_lens_too(self):
        """The fail-safe covers every gated lens, not just the original one."""
        assert change_impact.evaluate("this is not a diff")["skipLenses"] == []


class TestGateComposition:
    def test_the_gated_set_is_pinned_to_the_two_proven_absent_lenses(self):
        """Both entries pass the same test: the lens's subject must be
        *provably absent* from the diff (arch-review's structure,
        concurrency-review's primitives), not merely unlikely to appear.
        domain-review is deliberately NOT gated: business logic placed in a
        controller body is a real violation introduced by a body-only edit."""
        assert set(change_impact.GATED_LENSES) == {"arch-review", "concurrency-review"}

    def test_domain_review_is_never_gated_on_a_body_only_diff(self):
        """The named counter-example, asserted rather than only described."""
        assert "domain-review" not in change_impact.evaluate(BODY_ONLY)["skipLenses"]

    def test_the_gate_never_drops_a_change_size_floor_agent(self):
        """change_size.py keeps 4 agents on its narrowest fast path to clear
        the commit gate's >= 2 distinct-dispatch floor. This gate must never
        remove one of them, or the two gates could compose into a blocked
        commit."""
        floor = {"security-review", "correctness-review", "spec-compliance-review", "doc-review"}
        assert not (set(change_impact.GATED_LENSES) & floor)

    def test_the_floor_set_still_matches_change_size(self):
        """Drift guard: if change_size.py's keep-set changes, the assertion
        above must be re-checked against the new set rather than silently
        testing a stale literal."""
        source = (_SCRIPTS_DIR / "change_size.py").read_text(encoding="utf-8")
        for agent in (
            "security-review",
            "correctness-review",
            "spec-compliance-review",
            "doc-review",
        ):
            assert agent in source, f"{agent} no longer named in change_size.py"


class TestCli:
    def test_cli_reads_a_diff_on_stdin(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "change_impact.py")],
            input=BODY_ONLY,
            capture_output=True,
            text=True,
            check=True,
        )
        assert set(json.loads(result.stdout)["skipLenses"]) == {"arch-review", "concurrency-review"}

    def test_cli_accepts_extra_files(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "change_impact.py"), "--files", "go.mod"],
            input=BODY_ONLY,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert "manifest" in payload["signals"]
        assert set(payload["skipLenses"]) == {"concurrency-review"}


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


def _real_diff(tmp_path, filename, before, after):
    """A genuine `git diff` for one file, produced by git itself.

    The point of this class is to exercise the parser against real git output
    rather than the hand-built strings above — `_diff` encodes an assumption
    about what git emits, and an assumption is exactly what these tests exist
    to check.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    _git(repo.parent, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    target = repo / filename
    target.write_text(before, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    target.write_text(after, encoding="utf-8")
    result = subprocess.run(
        ["git", "diff", "--no-color"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


class TestAgainstRealGitDiffs:
    """Real `git diff` output, on changesets whose expected verdict is fixed.

    This replaces a test that ran `git diff origin/main...HEAD` and asserted
    the result had architectural impact, on the reasoning that "this branch
    adds new script modules". That was true of the branch it was written on
    and false of most others: it asserted a property of whatever happened to
    be checked out, not a property of the code under test. It went red on the
    release PR (a CHANGELOG and version bump, correctly carrying no
    architectural signal) and would have done the same on any docs-only or
    pure-refactor branch. A test coupled to incidental repo state is green for
    reasons unrelated to the thing it names.
    """

    def test_a_new_exported_function_keeps_arch_review(self, tmp_path):
        diff = _real_diff(
            tmp_path,
            "src/pricing.js",
            "export function total(items) {\n  return items.length\n}\n",
            "export function total(items) {\n  return items.length\n}\n\n"
            "export function applyDiscount(total, pct) {\n  return total * pct\n}\n",
        )
        result = change_impact.evaluate(diff)
        assert set(result["skipLenses"]) == {"concurrency-review"}
        assert result["hasArchitecturalImpact"] is True

    def test_a_docs_only_change_skips_arch_review(self, tmp_path):
        """The shape that broke the release PR: no runtime surface, so the
        gate correctly drops the lens."""
        diff = _real_diff(
            tmp_path,
            "docs/notes.md",
            "# Notes\n\nOne line.\n",
            "# Notes\n\nOne line.\n\nAnother line.\n",
        )
        result = change_impact.evaluate(diff)
        assert set(result["skipLenses"]) == {"arch-review", "concurrency-review"}
        assert result["hasArchitecturalImpact"] is False

    def test_a_body_only_edit_skips_arch_review(self, tmp_path):
        """No boundary moved — same function, different internals."""
        diff = _real_diff(
            tmp_path,
            "src/pricing.js",
            "export function total(items) {\n  return items.length\n}\n",
            "export function total(items) {\n  return items.filter(Boolean).length\n}\n",
        )
        result = change_impact.evaluate(diff)
        assert set(result["skipLenses"]) == {"arch-review", "concurrency-review"}
