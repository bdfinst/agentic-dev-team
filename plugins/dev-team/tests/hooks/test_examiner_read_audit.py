"""Unit tests for hooks/lib/examiner_read_audit.py (#2270, Step 3.1)."""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import examiner_read_audit as era  # type: ignore[import-not-found]

ROOT = "/repo"
CWD = "/repo"


def _classify(command: str, cwd: str = CWD) -> list[era.Finding]:
    return era.audit_commands([command], ROOT, cwd)


def _row(command: str, *expected: tuple[str, str]):
    """One table row: the command and its expected `(kind, target)` findings."""
    return pytest.param(command, list(expected), id=command or "<empty>")


READ = "read"
WRITE = "write"
GIT = "git"
XARGS = "xargs"

# Each row pins the exact finding list for one command; no expected findings
# means the command is allowed. Rows are grouped by the rule they pin.
ROWS = [
    # Plan table (decision 9 Gherkin rows).
    _row("pytest -q"),
    _row("pytest tests/test_app.py"),
    _row("pytest -q | tail -5"),
    _row("pytest -q 2>&1 | tail -5"),
    _row("pytest -q > out.log", (WRITE, "out.log")),
    _row("grep -n TODO src/app.py", (READ, "src/app.py")),
    _row("pytest -q | grep 'v1.2'"),
    _row("curl localhost:8080/health | cut -d. -f1"),
    _row("./bin/app --version | awk '{print $1/2}'"),
    _row("cat features/login.feature"),
    _row("grep TODO features/x.feature"),
    _row("ls src"),
    _row("curl localhost:8080 > /tmp/out.json; cat /tmp/out.json"),
    _row("cat src/app.py", (READ, "src/app.py")),
    _row("cat 'src/a b.py'", (READ, "src/a b.py")),
    _row("cat src/app.py features/x.feature", (READ, "src/app.py")),
    _row("head -n 5 src/a.py", (READ, "src/a.py")),
    _row("sed -n '1,5p' src/a.py", (READ, "src/a.py")),
    _row("grep -e TODO src/", (READ, "src/")),
    _row("grep -r TODO src/", (READ, "src/")),
    _row("cd repo && head -5 src/a.py", (READ, "src/a.py")),
    _row("cd src && cat app.py", (READ, "app.py")),
    _row("git show HEAD:src/app.py", (GIT, "show")),
    _row("git diff", (GIT, "diff")),
    _row("python3 - < tests/test_app.py", (READ, "tests/test_app.py")),
    _row("./bin/app < fixtures/in.json", (READ, "fixtures/in.json")),
    _row("find src -name '*.py' | xargs cat", (XARGS, "cat")),
    _row("sed -n '1,5p' /repo/src/app.py", (READ, "/repo/src/app.py")),
    _row(
        "echo '{}' > .claude/memory/acceptance-examination-x.json",
        (WRITE, ".claude/memory/acceptance-examination-x.json"),
    ),
    _row("pytest -q | tee run.log", (WRITE, "run.log")),
    _row("sed -i s/a/b/ src/app.py", (WRITE, "src/app.py")),
    _row("git commit -am wip", (GIT, "commit")),
    _row("git stash", (GIT, "stash")),
    # Decisions Step 3.1 pinned.
    _row("cd /elsewhere && cat app.py"),
    _row("cat ../outside.py"),
    _row("cat /repo2/x.py"),
    _row("cd /elsewhere && cd /repo/src && cat app.py", (READ, "app.py")),
    _row("pytest -q 2>/dev/null"),
    _row("pytest -q 2>&1"),
    _row("pytest -q >&2"),
    _row("pytest -q 2> err.log", (WRITE, "err.log")),
    _row("pytest -q >> out.log", (WRITE, "out.log")),
    _row("pytest -q &> out.log", (WRITE, "out.log")),
    _row("pytest -q >out.log", (WRITE, "out.log")),
    _row("cat src/a.py 2>&1", (READ, "src/a.py")),
    _row("cat src/a.py && cat src/b.py", (READ, "src/a.py"), (READ, "src/b.py")),
    _row("cat src/a.py|cat src/b.py", (READ, "src/a.py"), (READ, "src/b.py")),
    _row("pytest -q | sort src/a.py", (READ, "src/a.py")),
    _row("curl localhost | jq .status"),
    _row("curl localhost | jq -e .ok"),
    _row("tail -n 3 -f src/a.py", (READ, "src/a.py")),
    _row("rm -rf build", (WRITE, "build")),
    _row("cp /tmp/in.json fixtures/in.json", (WRITE, "fixtures/in.json")),
    _row("mv /repo/a.py /tmp/a.py", (WRITE, "/repo/a.py")),
    _row("sed -i.bak s/a/b/ src/app.py", (WRITE, "src/app.py")),
    _row("git -C /repo log", (GIT, "log")),
    _row("git status"),
    _row("find src | xargs -I{} grep TODO {}", (XARGS, "grep")),
    _row("echo src | xargs echo"),
    _row("cat -"),
    _row("cat"),
    _row(""),
    # 1. Variable operands are unknown, not findings.
    _row('out=$(mktemp); curl localhost:8080 > "$out"; cat "$out"'),
    _row('curl x > "${TMPDIR:-/tmp}/out.json"'),
    _row("cat `pwd`/x.py"),
    _row("cat src/$name.py"),
    _row("cat '$HOME/x.py'", (READ, "$HOME/x.py")),
    # 1. Command and process substitutions are audited as nested commands.
    _row("echo $(cat src/app.py)", (READ, "src/app.py")),
    _row("echo `cat src/app.py`", (READ, "src/app.py")),
    _row('echo "$(cat src/app.py)"', (READ, "src/app.py")),
    _row("cat <(cat src/app.py)", (READ, "src/app.py")),
    _row("diff <(pytest -q) /tmp/exp"),
    _row("pytest -q > >(tee run.log)", (WRITE, "run.log")),
    # 2. Operator characters inside quotes are literal.
    _row("curl -s localhost:8080 | grep '<title>'"),
    _row("pytest -q | grep '>= 3 passed'"),
    _row('echo "a; cat src/app.py"'),
    _row("echo a\\; cat src/app.py"),
    _row("echo a\\>b"),
    # 3. Heredoc bodies are not operands.
    _row('cat > /tmp/req.json <<\'EOF\'\n{"name": "x"}\nEOF'),
    _row("cat <<EOF > src/out.py\nbody\nEOF", (WRITE, "src/out.py")),
    _row("cat <<-EOF\n\tbody\n\tEOF\ncat src/app.py", (READ, "src/app.py")),
    _row("cat <<EOF\ncat src/app.py\nEOF"),
    _row("cat <<EOF\nunterminated body src/app.py"),
    _row("cat <<< 'src/app.py'"),
    # 4. Value flags after a pipe.
    _row("pytest -q | sort -k 2"),
    _row("pytest -q | sort -t , -k 2"),
    _row("pytest -q | awk -v n=3 '{print n}'"),
    _row("pytest -q | awk -F , '{print $1}'"),
    _row("pytest -q | jq --arg k v .x"),
    _row("pytest -q | jq --argjson k 1 --slurpfile s f.json --rawfile r r.txt .x"),
    _row("pytest -q | grep --max-count 1 passed"),
    _row("pytest -q | rg --after-context 2 passed"),
    _row("pytest -q | grep --before-context 2 passed"),
    _row("pytest -q | grep --context 2 passed"),
    # 5. Redirect and process-substitution operators.
    _row("echo x >| /tmp/x"),
    _row("echo x >| out.log", (WRITE, "out.log")),
    _row("cmd <> /tmp/x"),
    _row("cmd <> out.log", (WRITE, "out.log")),
    # 6. Wrappers, assignments, keywords, and basenames.
    _row("/bin/cat src/app.py", (READ, "src/app.py")),
    _row("/usr/bin/git show HEAD", (GIT, "show")),
    _row("env cat src/app.py", (READ, "src/app.py")),
    _row("env -i -u X A=1 cat src/app.py", (READ, "src/app.py")),
    _row("command cat src/app.py", (READ, "src/app.py")),
    _row("builtin cat src/app.py", (READ, "src/app.py")),
    _row("exec cat src/app.py", (READ, "src/app.py")),
    _row("nice cat src/app.py", (READ, "src/app.py")),
    _row("nice -n 5 cat src/app.py", (READ, "src/app.py")),
    _row("nohup cat src/app.py", (READ, "src/app.py")),
    _row("time cat src/app.py", (READ, "src/app.py")),
    _row("timeout 5 cat src/app.py", (READ, "src/app.py")),
    _row("timeout -s KILL 5 cat src/app.py", (READ, "src/app.py")),
    _row("LC_ALL=C grep x src/a.py", (READ, "src/a.py")),
    _row("! cat src/app.py", (READ, "src/app.py")),
    _row("{ cat src/app.py; }", (READ, "src/app.py")),
    _row("if cat src/app.py; then true; fi", (READ, "src/app.py")),
    _row("while cat src/app.py; do true; done", (READ, "src/app.py")),
    _row("until cat src/app.py; do true; done", (READ, "src/app.py")),
    _row(
        "if false; then true; elif cat src/a.py; then true; else cat src/b.py; fi",
        (READ, "src/a.py"),
        (READ, "src/b.py"),
    ),
    _row("for f in x; do cat src/app.py; done", (READ, "src/app.py")),
    _row('for f in src/*.py; do cat "$f"; done'),
    _row("while read l; do true; done < src/app.py", (READ, "src/app.py")),
    _row("eval 'cat src/app.py'", (READ, "src/app.py")),
    _row("eval cat src/app.py", (READ, "src/app.py")),
    _row("bash -c 'cat src/app.py'", (READ, "src/app.py")),
    _row('sh -c "cat src/app.py"', (READ, "src/app.py")),
    _row("bash -lc 'cat src/app.py'", (READ, "src/app.py")),
    _row('bash -c "cat src/app.py; echo $(date)"', (READ, "src/app.py")),
    _row("bash -c 'cat /tmp/x.json'"),
    _row("bash script.sh"),
    _row("eval eval eval cat src/app.py", (READ, "src/app.py")),
    _row("eval eval eval eval cat src/app.py"),
    # 7. Newline is a separator.
    _row("pytest -q\ncat src/app.py", (READ, "src/app.py")),
    # 8. Operators are lexed individually.
    _row("pytest -q |& cat src/app.py", (READ, "src/app.py")),
    _row("pytest -q;<src/app.py cat", (READ, "src/app.py")),
    _row("true||>src/app.py", (WRITE, "src/app.py")),
    # 9. A comment starts at a word start, before quote handling.
    _row("true;cat src/app.py #'", (READ, "src/app.py")),
    _row("pytest -q # > out.log"),
    _row("echo a#b > out.log", (WRITE, "out.log")),
    # 10. Subshells and background jobs.
    _row("(cat src/app.py)", (READ, "src/app.py")),
    _row("true & cat src/app.py", (READ, "src/app.py")),
    # 11. An unresolvable cd leaves relative operands inside the repository.
    _row(
        'cd "$(git rev-parse --show-toplevel)" && cat src/app.py',
        (READ, "src/app.py"),
    ),
    _row("cd ~ && cat src/app.py", (READ, "src/app.py")),
    _row("cd - && cat src/app.py", (READ, "src/app.py")),
    _row("cd $VAR && cat src/app.py", (READ, "src/app.py")),
    _row("cd && cat app.py", (READ, "app.py")),
    _row("cd $VAR && cat ../x.py", (READ, "../x.py")),
    _row("cd ~ && cat /tmp/x.json"),
    _row("cd $VAR && cd /elsewhere && cat app.py"),
    _row("cd -P /elsewhere && cat app.py"),
    _row("cd -- /elsewhere && cat app.py"),
    _row("cd -L src && cat app.py", (READ, "app.py")),
    # 12. Git global options and aliases.
    _row("git --git-dir .git show HEAD:src/app.py", (GIT, "show")),
    _row("git --git-dir=.git show HEAD:src/app.py", (GIT, "show")),
    _row("git --work-tree . --namespace n log", (GIT, "log")),
    _row("git -c user.name=x log", (GIT, "log")),
    _row("git -c core.pager=cat status"),
    _row("git -c alias.c=commit c -am x", (GIT, "alias")),
    _row("git -c ALIAS.c=commit c -am x", (GIT, "alias")),
    _row("git --config-env=alias.c=VAR c", (GIT, "alias")),
    # 13. Attached and long pattern flags.
    _row("grep -e. src/app.py", (READ, "src/app.py")),
    _row("grep --regexp=. src/app.py", (READ, "src/app.py")),
    _row("grep --regexp . src/app.py", (READ, "src/app.py")),
    _row("rg -e. src/app.py", (READ, "src/app.py")),
    _row("sed -e1,500p src/app.py", (READ, "src/app.py")),
    _row("grep --file=pats src/app.py", (READ, "src/app.py")),
    _row("grep -fpats src/app.py", (READ, "src/app.py")),
    _row("sed --expression=p src/app.py", (READ, "src/app.py")),
    # 14. Lexical spellings of an in-repo path.
    _row("cat //repo/src/app.py", (READ, "//repo/src/app.py")),
    _row("cd //repo && cat src/app.py", (READ, "src/app.py")),
    _row("cat ~+/src/app.py", (READ, "~+/src/app.py")),
    _row("cat ~-/src/app.py", (READ, "~-/src/app.py")),
    _row("cat ~/notes.txt", (READ, "~/notes.txt")),
    _row("cat ~/repo/src/app.py", (READ, "~/repo/src/app.py")),
    _row("cat /proc/self/cwd/src/app.py", (READ, "/proc/self/cwd/src/app.py")),
    _row("cd src && cat /proc/self/cwd/app.py", (READ, "/proc/self/cwd/app.py")),
    _row("cat /re*/src/app.py", (READ, "/re*/src/app.py")),
    _row("cat /{repo,x}/src/app.py", (READ, "/{repo,x}/src/app.py")),
    _row("cat src/*.py", (READ, "src/*.py")),
    _row("cat *.py", (READ, "*.py")),
    _row("cat /tmp/*.json"),
    _row("cat /tmp/{a,b}.json"),
    _row("cat /repo2*/x.py"),
    # 15. The .feature exemption covers reads only.
    _row("pytest -q > features/out.feature", (WRITE, "features/out.feature")),
    _row("sed -i s/a/b/ features/x.feature", (WRITE, "features/x.feature")),
    _row("rm features/x.feature", (WRITE, "features/x.feature")),
    _row("echo x | tee features/x.feature", (WRITE, "features/x.feature")),
    _row("mv /tmp/x features/x.feature", (WRITE, "features/x.feature")),
    _row("cp /tmp/x features/x.feature", (WRITE, "features/x.feature")),
    # 16. Write-capable git verbs are findings; their listing forms are read-only.
    _row("git branch -D old", (GIT, "branch")),
    _row("git branch newbranch", (GIT, "branch")),
    _row("git branch list", (GIT, "branch")),
    _row("git tag v1", (GIT, "tag")),
    _row("git tag -a v1 -m msg", (GIT, "tag")),
    _row("git remote add origin url", (GIT, "remote")),
    _row("git remote set-url origin url", (GIT, "remote")),
    _row("git worktree add ../w", (GIT, "worktree")),
    _row("git symbolic-ref HEAD refs/heads/x", (GIT, "symbolic-ref")),
    _row("git symbolic-ref -m why HEAD refs/heads/x", (GIT, "symbolic-ref")),
    _row("git symbolic-ref --delete HEAD", (GIT, "symbolic-ref")),
    _row("git symbolic-ref -d HEAD", (GIT, "symbolic-ref")),
    _row("git config user.name x", (GIT, "config")),
    _row("git config --global user.name x", (GIT, "config")),
    _row("git config --unset user.name", (GIT, "config")),
    _row("git branch"),
    _row("git branch --list"),
    _row("git branch -l"),
    _row("git branch -v"),
    _row("git branch -a"),
    _row("git branch --show-current"),
    _row("git tag"),
    _row("git tag -l"),
    _row("git tag --list"),
    _row("git tag -l 'v1*'"),
    _row("git remote"),
    _row("git remote -v"),
    _row("git remote show origin"),
    _row("git worktree list"),
    _row("git symbolic-ref HEAD"),
    _row("git symbolic-ref --short HEAD"),
    _row("git config --get user.name"),
    _row("git config --get-all user.name"),
    _row("git config --get-regexp 'user.*'"),
    _row("git config --list"),
    _row("git config -l"),
    _row("git config --local --get remote.origin.url"),
    # 16b. More git read verbs, on a repository path.
    _row("git annotate src/app.py", (GIT, "annotate")),
    _row("git whatchanged", (GIT, "whatchanged")),
    _row("git format-patch -1", (GIT, "format-patch")),
    _row("git archive HEAD", (GIT, "archive")),
    _row("git range-diff a...b", (GIT, "range-diff")),
    _row("git diff-tree HEAD", (GIT, "diff-tree")),
    _row("git diff-index HEAD", (GIT, "diff-index")),
    _row("git diff-files", (GIT, "diff-files")),
    _row("git fast-export HEAD", (GIT, "fast-export")),
    _row("git push origin x", (GIT, "push")),
    _row("git add .", (GIT, "add")),
    _row("git merge x", (GIT, "merge")),
    _row("git rebase x", (GIT, "rebase")),
    _row("git update-ref x y", (GIT, "update-ref")),
    # 17. Value-flag coverage.
    _row("grep -A 3 pat src/a.py", (READ, "src/a.py")),
    _row("grep -m 1 pat src/a.py", (READ, "src/a.py")),
    _row("grep -f pats.txt src/a.py", (READ, "src/a.py")),
    _row("rg -f pats.txt src/a.py", (READ, "src/a.py")),
    _row("cut -d , -f 2 src/a.py", (READ, "src/a.py")),
    _row("awk -f prog.awk src/a.py", (READ, "src/a.py")),
    _row("cut -d. -f1"),
    # 18. Recursive grep and rg with no path operand search the cwd.
    _row("grep -rn assert", (READ, ".")),
    _row("grep -R TODO", (READ, ".")),
    _row("grep --recursive TODO", (READ, ".")),
    _row("grep -d recurse TODO", (READ, ".")),
    _row("grep -r -e TODO", (READ, ".")),
    _row("rg secret", (READ, ".")),
    _row("rg -e secret", (READ, ".")),
    _row("cd ~ && rg secret", (READ, ".")),
    _row("cd /elsewhere && rg secret"),
    _row("pytest -q | grep -r x"),
    _row("pytest -q | rg x"),
    _row("pytest -q |& rg x"),
    _row("grep -n x features/a.feature"),
    _row("grep -n x"),
    _row("grep -r x -"),
    # 19. Heredoc bodies: substitutions run only for an unquoted delimiter.
    _row("cat <<EOF\n$(cat src/app.py)\nEOF", (READ, "src/app.py")),
    _row("cat <<EOF\nline `head -1 src/a.py` end\nEOF", (READ, "src/a.py")),
    _row("cat <<-EOF\n\t$(cat src/app.py)\n\tEOF", (READ, "src/app.py")),
    _row(
        "cat <<EOF\n$(cat src/app.py)\nEOF\ncat src/b.py",
        (READ, "src/app.py"),
        (READ, "src/b.py"),
    ),
    _row("cat <<EOF\n\\$(cat src/app.py)\nEOF"),
    _row("cat <<'EOF'\n$(cat src/app.py)\nEOF"),
    _row('cat <<"EOF"\n$(cat src/app.py)\nEOF'),
    _row("cat <<\\EOF\n$(cat src/app.py)\nEOF"),
    # 20. File-printing readers and `dd if=`.
    _row("tac src/app.py", (READ, "src/app.py")),
    _row("base64 src/app.py", (READ, "src/app.py")),
    _row("base64 -w 0 src/app.py", (READ, "src/app.py")),
    _row("paste src/app.py", (READ, "src/app.py")),
    _row("rev src/app.py", (READ, "src/app.py")),
    _row("fold -w 80 src/app.py", (READ, "src/app.py")),
    _row("pr src/app.py", (READ, "src/app.py")),
    _row("hexdump -C src/app.py", (READ, "src/app.py")),
    _row("uniq src/app.py", (READ, "src/app.py")),
    _row("comm src/a.py src/b.py", (READ, "src/a.py"), (READ, "src/b.py")),
    _row("cmp src/a.py src/b.py", (READ, "src/a.py"), (READ, "src/b.py")),
    _row("vim src/app.py", (READ, "src/app.py")),
    _row("view src/app.py", (READ, "src/app.py")),
    _row("nl src/app.py", (READ, "src/app.py")),
    _row("strings src/app.py", (READ, "src/app.py")),
    _row("dd if=src/app.py of=/tmp/x", (READ, "src/app.py")),
    _row("dd if=/dev/zero of=/tmp/x bs=1k count=1"),
    _row("dd if=$SRC of=/tmp/x"),
    _row("pytest -q | uniq"),
]


@pytest.mark.parametrize(("command", "expected"), ROWS)
def test_classifies_command_against_repository_root(command, expected):
    findings = _classify(command)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        (kind, target, command) for kind, target in expected
    ]


def test_cd_inside_one_command_does_not_leak_into_the_next():
    findings = era.audit_commands(["cd /elsewhere", "cat app.py"], ROOT, CWD)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        ("read", "app.py", "cat app.py")
    ]


def test_multiple_commands_keep_input_order_and_own_command_text():
    commands = ["cat src/a.py", "pytest -q", "git diff", "pytest -q > out.log"]

    findings = era.audit_commands(commands, ROOT, CWD)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        ("read", "src/a.py", "cat src/a.py"),
        ("git", "diff", "git diff"),
        ("write", "out.log", "pytest -q > out.log"),
    ]


def test_no_commands_yields_no_findings():
    assert era.audit_commands([], ROOT, CWD) == []


def test_relative_operand_resolves_against_the_given_cwd():
    findings = _classify("cat app.py", cwd="/repo/src")

    assert [(f.kind, f.target) for f in findings] == [("read", "app.py")]


def test_cwd_outside_root_makes_relative_operand_allowed():
    assert _classify("cat app.py", cwd="/tmp") == []


def test_unterminated_quote_is_ignored_and_the_rest_is_still_audited():
    command = 'cat src/a.py "unterminated; cat src/b.py'

    findings = _classify(command)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        ("read", "src/a.py", command),
        ("read", "unterminated", command),
        ("read", "src/b.py", command),
    ]


def test_audit_scope_names_the_root_and_the_cwd():
    scope = era.AuditScope("/repo", "/repo/src")

    assert (scope.root, scope.cwd) == ("/repo", "/repo/src")


def test_finding_is_a_named_tuple_of_kind_target_command():
    finding = era.Finding("read", "src/a.py", "cat src/a.py")

    assert (finding.kind, finding.target, finding.command) == (
        "read",
        "src/a.py",
        "cat src/a.py",
    )
