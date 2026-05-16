import json
import os
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), trim_blocks=False, lstrip_blocks=False)


def render(verdict: dict) -> str:
    canonical = verdict["canonicalRequest"]["spec"]
    if verdict["allow"]:
        tmpl = env.get_template("allow_comment.md")
    else:
        tmpl = env.get_template("deny_comment.md")
    return tmpl.render(
        verdict=verdict,
        source=canonical["source"],
        destination=canonical["destination"],
        lifecycle=canonical["lifecycle"],
        controls=verdict.get("controls", {}),
        denyReasons=verdict.get("denyReasons", []),
    )


def post(pr_number: int, body: str) -> None:
    """Edit existing Beacon comment if found, else create new."""
    marker = "<!-- beacon-verdict-comment -->"
    body_with_marker = f"{marker}\n{body}"

    # Look up via REST API so the returned `.id` is the numeric REST id the
    # PATCH endpoint requires. (gh pr view returns the GraphQL node id, which
    # PATCH /repos/.../issues/comments/{id} 404s on.)
    repo = os.environ["GITHUB_REPOSITORY"]
    existing = subprocess.run(
        ["gh", "api", f"/repos/{repo}/issues/{pr_number}/comments", "--paginate",
         "--jq", f'.[] | select(.body | startswith("{marker}")) | .id'],
        capture_output=True, text=True, check=False,
    )
    # Multiple matches shouldn't happen, but take the first defensively.
    existing_id = existing.stdout.splitlines()[0].strip() if existing.stdout.strip() else ""

    if existing_id:
        subprocess.run(
            ["gh", "api", "-X", "PATCH",
             f"/repos/{repo}/issues/comments/{existing_id}",
             "-f", f"body={body_with_marker}"],
            check=True,
        )
    else:
        subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--body", body_with_marker],
            check=True,
        )


def main() -> int:
    verdict = json.load(sys.stdin)
    body = render(verdict)
    pr_number = int(os.environ["BEACON_PR_NUMBER"])
    post(pr_number, body)
    print(f"Posted comment to PR #{pr_number}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
