import json
import os
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), trim_blocks=False, lstrip_blocks=False)


def render(verdict: dict, actor: str) -> tuple[str, str]:
    canonical = verdict["canonicalRequest"]["spec"]
    intent_name = verdict["canonicalRequest"]["metadata"]["name"]
    tmpl = env.get_template("approved_networkintent.yaml")
    body = tmpl.render(
        intent_name=intent_name,
        verdict=verdict,
        source=canonical["source"],
        destination=canonical["destination"],
        traffic=canonical["traffic"],
        purpose=canonical.get("purpose", {}),
        lifecycle=canonical.get("lifecycle", {}),
        controls=verdict.get("controls", {}),
        actor=actor or "beacon",
    )
    return intent_name, body


def commit_and_push(file_path: Path, decision_id: str) -> None:
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
    # -f bypasses the consumer repo's .gitignore (which typically excludes
    # .beacon/ for the per-run evidence dump). The approvals file is the
    # durable record we deliberately want tracked.
    subprocess.run(["git", "add", "-f", str(file_path)], check=True)
    msg = f"beacon: approval {decision_id} for {file_path.stem}"
    subprocess.run(["git", "commit", "-m", msg], check=True)
    head_ref = os.environ.get("GITHUB_HEAD_REF")
    subprocess.run(["git", "push", "origin", f"HEAD:{head_ref}"], check=True)


def main() -> int:
    verdict = json.load(sys.stdin)
    if not verdict.get("allow"):
        return 0
    intent_name, body = render(verdict, os.environ.get("GITHUB_ACTOR", "beacon"))
    out_path = Path(".beacon/approvals") / f"{intent_name}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body)
    commit_and_push(out_path, verdict["decisionId"])
    print(f"Wrote back: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
