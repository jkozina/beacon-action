"""Post-merge entry point: re-evaluates the merged PR's intents and commits the
durable approval YAMLs to the merged-into branch (typically `main`).

Why a post-merge re-eval (not a replay of the PR-time verdict): if the world
state changed between PR review and merge (FQDN re-resolved to a different
owner, ServiceNow asset retired, etc.), the durable record should reflect what
was actually true at the moment connectivity was committed. A post-merge deny
is a real signal — it means something drifted; the merge button should not
have been clickable.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.extract import extract_from_helm_values, ExtractionError
from scripts.impl_hash import compute_impl_hash
from scripts.call_pdp import call_pdp
from scripts.verify_signature import verify_verdict
from scripts.write_back import render


def pr_implementation_files(impl_paths: list[str], repo: str, pr_number: int) -> list[Path]:
    """Files in the PR — query GitHub's PR-files API, not git diff. Independent
    of how the PR was merged (merge commit / squash / rebase)."""
    out = subprocess.check_output(
        ["gh", "api", f"/repos/{repo}/pulls/{pr_number}/files",
         "--paginate", "--jq", ".[].filename"],
        text=True,
    )
    all_changed = [Path(p) for p in out.splitlines() if p.strip()]
    matched = [p for p in all_changed if any(str(p).startswith(ip.strip()) for ip in impl_paths)]
    return [p for p in matched if p.name == "values.yaml"]


def main() -> int:
    beacon_url = os.environ["BEACON_URL"]
    impl_paths = os.environ["IMPLEMENTATION_PATHS"].split(",")
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["BEACON_PR_NUMBER"])

    files = pr_implementation_files(impl_paths, repo, pr_number)
    if not files:
        print(f"PR #{pr_number} touched no implementation files; nothing to record.", file=sys.stderr)
        return 0

    impl_hash = compute_impl_hash(files)
    source_ctx = {
        "workloadId": "orders-api", "namespace": "orders", "serviceAccount": "orders-api",
    }

    approvals: list[tuple[str, str]] = []  # (intent_name, yaml_body)
    decision_ids: list[str] = []

    for f in files:
        try:
            intents = extract_from_helm_values(f, source_ctx)
        except ExtractionError as e:
            # If extraction fails at merge time, something is very wrong —
            # the PR-time check should have caught this and the PR shouldn't
            # have been mergeable. Fail loud.
            print(f"FATAL: post-merge extraction failed for {f}: {e}", file=sys.stderr)
            return 1

        for derived in intents:
            impl_ctx = {
                "hash": impl_hash,
                "repository": repo,
                "pullRequest": pr_number,
                "commit": os.environ.get("GITHUB_SHA", ""),
                "actor": os.environ.get("GITHUB_ACTOR", ""),
                "workflowRunId": os.environ.get("GITHUB_RUN_ID", ""),
                "implementationFiles": [str(p) for p in files],
            }
            verdict = call_pdp(beacon_url, derived, impl_ctx)
            if not verify_verdict(verdict):
                print(
                    f"FATAL: post-merge verdict signature did not verify for {derived['metadata']['name']}.",
                    file=sys.stderr,
                )
                return 1
            if not verdict["allow"]:
                print(
                    f"FATAL: post-merge re-eval DENIED {derived['metadata']['name']}: "
                    f"{verdict.get('denyReasons')}. World state changed between PR review and merge.",
                    file=sys.stderr,
                )
                return 1
            _, body = render(verdict, os.environ.get("GITHUB_ACTOR", "beacon"))
            approvals.append((derived["metadata"]["name"], body))
            decision_ids.append(verdict["decisionId"])

    if not approvals:
        print("No allow verdicts to record.", file=sys.stderr)
        return 0

    out_dir = Path(".beacon/approvals")
    out_dir.mkdir(parents=True, exist_ok=True)
    for intent_name, body in approvals:
        (out_dir / f"{intent_name}.yaml").write_text(body)

    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", "-f", *[str(out_dir / f"{n}.yaml") for n, _ in approvals]], check=True)
    msg = f"beacon: record approvals {','.join(decision_ids)} from PR #{pr_number}"
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push", "origin", "HEAD"], check=True)
    print(f"Recorded {len(approvals)} approval(s) on {os.environ.get('GITHUB_REF_NAME', 'HEAD')}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
