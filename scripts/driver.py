import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.extract import extract_from_helm_values, ExtractionError
from scripts.impl_hash import compute_impl_hash
from scripts.call_pdp import call_pdp
from scripts.post_comment import render, post


def changed_implementation_files(impl_paths: list[str]) -> list[Path]:
    base_ref = os.environ.get("GITHUB_BASE_REF", "main")
    subprocess.run(["git", "fetch", "origin", base_ref], check=True)
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
        text=True,
    )
    all_changed = [Path(p) for p in out.splitlines() if p.strip()]
    matched = [p for p in all_changed if any(str(p).startswith(ip.strip()) for ip in impl_paths)]
    # Filter to Helm values for the POC.
    return [p for p in matched if p.name == "values.yaml"]


def write_evidence(out_dir: Path, name: str, derived: dict, verdict: dict) -> None:
    # Note: canonical-request is intentionally NOT written as a separate file.
    # It lives in verdict["canonicalRequest"] (self-contained envelope) and in
    # this POC every other byte of it duplicates enrichment + derived. If/when
    # the enricher grows non-trivial computed logic, revisit.
    for sub in ("derived-intents", "verdicts", "enrichment", "extraction"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    (out_dir / "derived-intents" / f"{name}.json").write_text(json.dumps(derived, indent=2))
    (out_dir / "verdicts" / f"{name}.json").write_text(json.dumps(verdict, indent=2))
    (out_dir / "enrichment" / f"{name}.json").write_text(json.dumps(verdict["enrichmentSnapshot"], indent=2))
    (out_dir / "extraction" / f"{name}.json").write_text(json.dumps({"status": "ok", "name": name}, indent=2))


def main() -> int:
    beacon_url = os.environ["BEACON_URL"]
    impl_paths = os.environ["IMPLEMENTATION_PATHS"].split(",")
    pr_number = int(os.environ["BEACON_PR_NUMBER"])
    out_dir = Path(os.environ.get("BEACON_OUT_DIR", ".beacon"))

    files = changed_implementation_files(impl_paths)
    if not files:
        print("No implementation files changed in this PR; nothing to evaluate.", file=sys.stderr)
        return 0

    impl_hash = compute_impl_hash(files)
    source_ctx = {
        # Hard-coded for the POC retail-orders source. Phase 4 can extend.
        "workloadId": "orders-api", "namespace": "orders", "serviceAccount": "orders-api",
    }

    overall_allow = True

    for f in files:
        try:
            intents = extract_from_helm_values(f, source_ctx)
        except ExtractionError as e:
            # Post extraction-failure comment; fail closed.
            body = f"### Beacon Connectivity Verdict — Extraction Failed\n\nFile: `{f}`\nReason: {e}\n\nThis check fails closed."
            post(pr_number, body)
            return 1

        for derived in intents:
            impl_ctx = {
                "hash": impl_hash,
                "repository": os.environ["GITHUB_REPOSITORY"],
                "pullRequest": pr_number,
                "commit": os.environ.get("GITHUB_SHA", ""),
                "actor": os.environ.get("GITHUB_ACTOR", ""),
                "workflowRunId": os.environ.get("GITHUB_RUN_ID", ""),
                "implementationFiles": [str(p) for p in files],
            }
            verdict = call_pdp(beacon_url, derived, impl_ctx)
            from scripts.verify_signature import verify_verdict
            if not verify_verdict(verdict):
                body = (
                    "### Beacon Connectivity Verdict — System Error\n\n"
                    "Verdict signature failed verification. This check fails closed.\n\n"
                    f"Decision ID (unverified): `{verdict.get('decisionId', '?')}`"
                )
                post(pr_number, body)
                return 1
            write_evidence(out_dir, derived["metadata"]["name"], derived, verdict)
            post(pr_number, render(verdict))
            if verdict["allow"]:
                # Write back approved NetworkIntent to PR branch.
                from scripts.write_back import render as render_writeback, commit_and_push
                intent_name, body = render_writeback(verdict, os.environ.get("GITHUB_ACTOR", "beacon"))
                out_path = Path(".beacon/approvals") / f"{intent_name}.yaml"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(body)
                commit_and_push(out_path, verdict["decisionId"])
            if not verdict["allow"]:
                overall_allow = False

    return 0 if overall_allow else 1


if __name__ == "__main__":
    sys.exit(main())
