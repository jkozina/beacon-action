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

    existing = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "comments", "--jq",
         f'.comments[] | select(.body | startswith("{marker}")) | .id'],
        capture_output=True, text=True, check=False,
    )
    existing_id = existing.stdout.strip()

    if existing_id:
        # gh doesn't directly support editing PR comments; use the API
        subprocess.run(
            ["gh", "api", "-X", "PATCH",
             f"/repos/{os.environ['GITHUB_REPOSITORY']}/issues/comments/{existing_id}",
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
