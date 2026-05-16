import json
import os
import sys
from pathlib import Path

import requests


def call_pdp(beacon_url: str, derived_intent: dict, implementation_context: dict) -> dict:
    resp = requests.post(
        f"{beacon_url.rstrip('/')}/v1/verdict",
        json={
            "derivedIntent": derived_intent,
            "implementationContext": implementation_context,
            "policyMode": "enforce",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    """CLI: read derived intent JSON from stdin, write verdict to stdout, persist artifacts."""
    beacon_url = os.environ["BEACON_URL"]
    out_dir = Path(os.environ.get("BEACON_OUT_DIR", ".beacon"))
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = json.load(sys.stdin)
    derived = payload["derivedIntent"]
    impl_ctx = payload["implementationContext"]

    verdict = call_pdp(beacon_url, derived, impl_ctx)

    # Intent name becomes the artifact filename; reject anything that could
    # traverse outside out_dir. The extractor produces safe names today but
    # this CLI runs on PR-controlled input under action.yml.
    name = derived["metadata"]["name"]
    if "/" in name or "\\" in name or ".." in name or name.startswith(".") or not name:
        raise ValueError(f"unsafe intent name: {name!r}")

    (out_dir / "derived-intents").mkdir(exist_ok=True)
    (out_dir / "verdicts").mkdir(exist_ok=True)
    (out_dir / "canonical").mkdir(exist_ok=True)
    (out_dir / "enrichment").mkdir(exist_ok=True)
    (out_dir / "extraction").mkdir(exist_ok=True)

    (out_dir / "derived-intents" / f"{name}.json").write_text(json.dumps(derived, indent=2))
    (out_dir / "verdicts" / f"{name}.json").write_text(json.dumps(verdict, indent=2))
    (out_dir / "canonical" / f"{name}.json").write_text(json.dumps(verdict.get("canonicalRequest", {}), indent=2))
    (out_dir / "enrichment" / f"{name}.json").write_text(json.dumps(verdict.get("enrichmentSnapshot", {}), indent=2))
    (out_dir / "extraction" / f"{name}.json").write_text(json.dumps({"status": "ok", "name": name}, indent=2))

    json.dump(verdict, sys.stdout)
    return 0 if verdict.get("allow") else 2  # 2 = signed deny; the action treats this as a failed check


if __name__ == "__main__":
    sys.exit(main())
