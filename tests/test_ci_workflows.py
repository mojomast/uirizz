"""Contract for uirizz's GitHub Actions hygiene (rizzstack follow-ups item 21; rizzstack/codemap/ci-gates.md).

- a gitleaks job scans full history on every pull request and push to main;
- every action is pinned to a full commit SHA;
- every checkout sets persist-credentials: false;
- workflow token permissions are read-only;
- slop-lint runs as a blocking ratchet against a committed, owner-reviewed baseline.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
GITLEAKS = WORKFLOWS / "gitleaks.yml"
SLOP = WORKFLOWS / "slop-lint.yml"


def workflow_files():
    return sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml")))


def checkout_blocks(text):
    """Each `uses: actions/checkout@...` step with its indented `with:` lines."""
    lines = text.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        if re.match(r"^\s*-?\s*uses:\s*actions/checkout@", line):
            indent = len(line) - len(line.lstrip(" -"))
            body = [line]
            for nxt in lines[i + 1:]:
                stripped = nxt.lstrip(" ")
                if stripped.startswith("- ") or (stripped and len(nxt) - len(stripped) < indent):
                    break
                body.append(nxt)
            blocks.append("\n".join(body))
    return blocks


class GitleaksJobTests(unittest.TestCase):
    def text(self):
        self.assertTrue(GITLEAKS.is_file(), "missing .github/workflows/gitleaks.yml")
        return GITLEAKS.read_text()

    def test_runs_on_pull_requests_and_pushes_to_main(self):
        t = self.text()
        self.assertIn("pull_request:", t)
        self.assertRegex(t, r"push:\s*\n\s*branches:\s*\[main\]")
        self.assertNotIn("pull_request_target", t)

    def test_job_has_a_stable_name_and_is_bounded_and_blocking(self):
        t = self.text()
        self.assertRegex(t, r"(?m)^    name:\s*gitleaks\s*$")
        self.assertRegex(t, r"timeout-minutes:\s*\d+")
        self.assertNotIn("continue-on-error", t)

    def test_scans_full_history_with_a_checksum_verified_scanner(self):
        t = self.text()
        self.assertRegex(t, r"fetch-depth:\s*0")
        self.assertRegex(t, r"echo \"[0-9a-f]{64}  gitleaks\.tgz\" \| sha256sum -c -")
        self.assertRegex(t, r"gitleaks detect --source \. --redact")
        self.assertNotRegex(t, r"--exit-code\s+0")

    def test_needs_no_secrets(self):
        self.assertNotIn("secrets.", self.text())


class WorkflowHygieneTests(unittest.TestCase):
    def test_every_action_is_pinned_to_a_full_sha(self):
        for wf in workflow_files():
            for ref in re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", wf.read_text()):
                if ref.startswith("./"):
                    continue
                self.assertRegex(ref, r"@[0-9a-f]{40}$", "%s: %s" % (wf.name, ref))

    def test_every_checkout_drops_the_token(self):
        for wf in workflow_files():
            for block in checkout_blocks(wf.read_text()):
                self.assertRegex(block, r"persist-credentials:\s*false", "%s:\n%s" % (wf.name, block))

    def test_token_permissions_are_read_only(self):
        for wf in workflow_files():
            t = wf.read_text()
            m = re.search(r"(?m)^permissions:\s*\n((?:[ \t]+.*\n)+)", t)
            self.assertIsNotNone(m, "%s: top-level permissions block required" % wf.name)
            self.assertIn("contents: read", m.group(1))
            self.assertNotRegex(t, r"(?m)^\s+[a-z-]+:\s*write\s*$", wf.name)


class SlopLintRatchetTests(unittest.TestCase):
    def text(self):
        self.assertTrue(SLOP.is_file(), "missing .github/workflows/slop-lint.yml")
        return SLOP.read_text()

    def test_stable_name_and_pinned_python(self):
        t = self.text()
        self.assertRegex(t, r"(?m)^  slop-lint:\s*\n    name:\s*slop-lint\s*$")
        self.assertRegex(t, r"python-version:\s*\"3\.12\"")
        self.assertIn("pull_request:", t)
        self.assertRegex(t, r"push:\s*\n\s*branches:\s*\[main\]")

    def test_blocks_new_findings_against_the_committed_baseline(self):
        t = self.text()
        self.assertIn("python3 -m slop_lint check . --baseline slop-baseline.json --pass-on-unpruned", t)
        self.assertNotIn("--report-only", t)
        self.assertNotIn("continue-on-error", t)
        self.assertRegex(t, r"shell:\s*bash")
        self.assertIn("GITHUB_STEP_SUMMARY", t)
        self.assertTrue((ROOT / "slop-baseline.json").is_file(), "slop-baseline.json missing")

    def test_baseline_is_owner_reviewed(self):
        co = (ROOT / ".github" / "CODEOWNERS").read_text()
        self.assertRegex(co, r"(?m)^/slop-baseline\.json\s+@mojomast\s*$")

    def test_no_network_installs_or_secrets(self):
        t = self.text()
        self.assertNotRegex(t, r"pip install|npm install|curl ")
        self.assertNotIn("secrets.", t)


if __name__ == "__main__":
    unittest.main()
