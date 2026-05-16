import re
import yaml
from pathlib import Path


class ExtractionError(Exception):
    pass


WILDCARD_RE = re.compile(r"[\*\?]")


def extract_from_helm_values(values_path: Path, source_ctx: dict) -> list[dict]:
    """Walk egress.allow[]; return one derived NetworkIntent per entry. Fail closed on unsupported shapes."""
    data = yaml.safe_load(values_path.read_text()) or {}
    allows = (data.get("egress") or {}).get("allow") or []

    intents = []
    for idx, entry in enumerate(allows):
        host = entry.get("host")
        if not host:
            raise ExtractionError(f"entry {idx}: missing host")
        if WILDCARD_RE.search(host):
            raise ExtractionError(f"entry {idx}: wildcard hosts are not permitted ({host})")
        if "port" not in entry:
            raise ExtractionError(f"entry {idx}: missing port for {host}")
        if not entry.get("justification"):
            raise ExtractionError(f"entry {idx}: missing justification for {host}")

        name = f"{source_ctx['workloadId'].removesuffix('-api')}-to-{entry.get('name') or _name_from_host(host)}"

        intents.append({
            "apiVersion": "network.company.com/v1",
            "kind": "NetworkIntent",
            "metadata": {"name": name},
            "spec": {
                "source": dict(source_ctx),
                "destination": {"fqdn": host},
                "traffic": {
                    "protocol": "TCP",
                    "port": int(entry["port"]),
                    "applicationProtocol": entry.get("protocol", "HTTPS"),
                },
                "purpose": {
                    "businessJustification": entry["justification"],
                    "ticket": entry.get("ticket", ""),
                },
                "lifecycle": {"requestedTtlDays": int(entry.get("ttlDays", 30))},
            },
        })
    return intents


def _name_from_host(host: str) -> str:
    return host.split(".")[0]
