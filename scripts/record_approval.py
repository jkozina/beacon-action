"""Post-merge entry point: diff-aware approval recording.

For each merged PR, compare egress.allow entries pre- vs post-merge:
  - ADDED entry      → call PDP, write fresh approval YAML (new decisionId).
  - MODIFIED entry   → call PDP, overwrite approval YAML (new decisionId).
                       The old approval is no longer the same request.
  - UNCHANGED entry  → leave the approval YAML alone. Its decisionId remains
                       the original approval; that's the audit anchor.
  - REMOVED entry    → delete the corresponding approval YAML. The connection
                       is no longer requested; no durable approval should
                       persist.

Drift detection (the PDP returning a different verdict for an unchanged entry
than it did at original approval time) is a separate concern, handled by a
periodic drift scan — NOT by silently rewriting approvals on every merge.
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

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


def _name_from_host(host: str) -> str:
    return host.split(".")[0]


def egress_entries_by_intent_name(yaml_text: str, workload_id: str) -> dict[str, dict]:
    """Parse a values.yaml string and return egress.allow entries keyed by the
    intent name we'd build from each (matches extract.py's naming scheme)."""
    data = yaml.safe_load(yaml_text) or {}
    allows = (data.get("egress") or {}).get("allow") or []
    result: dict[str, dict] = {}
    for entry in allows:
        if not isinstance(entry, dict):
            continue
        host = entry.get("host", "")
        suffix = entry.get("name") or _name_from_host(host)
        intent_name = f"{workload_id.removesuffix('-api')}-to-{suffix}"
        result[intent_name] = entry
    return result


def read_premerge_file(path: Path) -> str:
    """Get the file's contents at the merge commit's first parent (= pre-merge
    state of the merged-into branch). Returns empty string if the file did not
    exist pre-merge (e.g., the PR introduced it)."""
    proc = subprocess.run(
        ["git", "show", f"HEAD^:{path}"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def main() -> int:
    beacon_url = os.environ["BEACON_URL"]
    impl_paths = os.environ["IMPLEMENTATION_PATHS"].split(",")
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = int(os.environ["BEACON_PR_NUMBER"])

    files = pr_implementation_files(impl_paths, repo, pr_number)
    if not files:
        print(f"PR #{pr_number} touched no implementation files; nothing to record.", file=sys.stderr)
        return 0

    workload_id = "orders-api"   # POC: single source; Phase 4+ generalizes.
    source_ctx = {"workloadId": workload_id, "namespace": "orders", "serviceAccount": "orders-api"}

    # Compute the per-file diff of egress entries between pre-merge and post-merge.
    added_names: set[str] = set()
    modified_names: set[str] = set()
    removed_names: set[str] = set()
    file_for_intent: dict[str, Path] = {}

    for f in files:
        new_yaml = f.read_text()
        old_yaml = read_premerge_file(f)
        new_entries = egress_entries_by_intent_name(new_yaml, workload_id)
        old_entries = egress_entries_by_intent_name(old_yaml, workload_id)
        for name in new_entries:
            file_for_intent[name] = f
            if name not in old_entries:
                added_names.add(name)
            elif new_entries[name] != old_entries[name]:
                modified_names.add(name)
        for name in old_entries:
            if name not in new_entries:
                removed_names.add(name)
                file_for_intent.setdefault(name, f)

    to_evaluate = added_names | modified_names

    out_dir = Path(".beacon/approvals")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not to_evaluate and not removed_names:
        print(f"PR #{pr_number}: no egress changes — approvals untouched.", file=sys.stderr)
        return 0

    impl_hash = compute_impl_hash(files)

    approvals: list[tuple[str, str, str]] = []  # (intent_name, yaml_body, decisionId)

    if to_evaluate:
        for f in files:
            try:
                intents = extract_from_helm_values(f, source_ctx)
            except ExtractionError as e:
                # Post-merge extraction failure is a real bug — PR-time should
                # have caught it. Fail loud.
                print(f"FATAL: post-merge extraction failed for {f}: {e}", file=sys.stderr)
                return 1

            for derived in intents:
                if derived["metadata"]["name"] not in to_evaluate:
                    continue   # unchanged entry — leave the existing YAML alone
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
                approvals.append((derived["metadata"]["name"], body, verdict["decisionId"]))

    for intent_name, body, _did in approvals:
        (out_dir / f"{intent_name}.yaml").write_text(body)

    deleted: list[str] = []
    for intent_name in sorted(removed_names):
        p = out_dir / f"{intent_name}.yaml"
        if p.exists():
            p.unlink()
            deleted.append(intent_name)

    if not approvals and not deleted:
        print("Diff classified entries but produced no on-disk changes (no-op).", file=sys.stderr)
        return 0

    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com"], check=True)

    add_paths = [str(out_dir / f"{n}.yaml") for n, _, _ in approvals]
    if add_paths:
        subprocess.run(["git", "add", "-f", *add_paths], check=True)
    for n in deleted:
        subprocess.run(["git", "rm", "-f", str(out_dir / f"{n}.yaml")], check=True)

    parts: list[str] = []
    added_for_msg = [n for n in approvals if n[0] in added_names]
    modified_for_msg = [n for n in approvals if n[0] in modified_names]
    if added_for_msg:
        parts.append("add " + ",".join(f"{n}({d})" for n, _, d in added_for_msg))
    if modified_for_msg:
        parts.append("update " + ",".join(f"{n}({d})" for n, _, d in modified_for_msg))
    if deleted:
        parts.append("remove " + ",".join(deleted))
    summary = "; ".join(parts) if parts else "no-op"
    msg = f"beacon: PR #{pr_number} — {summary}"

    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push", "origin", "HEAD"], check=True)
    print(
        f"Recorded {len(approvals)} approval(s), deleted {len(deleted)}, "
        f"left {len(file_for_intent) - len(approvals) - len(deleted)} unchanged on "
        f"{os.environ.get('GITHUB_REF_NAME', 'HEAD')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
