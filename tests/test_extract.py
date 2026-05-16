import textwrap
from pathlib import Path
from scripts.extract import extract_from_helm_values, ExtractionError


def test_extract_one_egress_allow(tmp_path: Path):
    f = tmp_path / "values.yaml"
    f.write_text(textwrap.dedent("""
        egress:
          allow:
            - name: payments
              host: payments-api.prod.company.internal
              port: 443
              protocol: HTTPS
              justification: Submit payment authorization requests
              ticket: CHG123456
              ttlDays: 30
    """).strip())
    source_ctx = {"workloadId": "orders-api", "namespace": "orders", "serviceAccount": "orders-api"}
    intents = extract_from_helm_values(f, source_ctx)
    assert len(intents) == 1
    i = intents[0]
    assert i["metadata"]["name"] == "orders-to-payments"
    assert i["spec"]["destination"]["fqdn"] == "payments-api.prod.company.internal"
    assert i["spec"]["traffic"]["port"] == 443
    assert i["spec"]["lifecycle"]["requestedTtlDays"] == 30


def test_extract_wildcard_host_fails(tmp_path: Path):
    f = tmp_path / "values.yaml"
    f.write_text(textwrap.dedent("""
        egress:
          allow:
            - host: "*.legacy.example.com"
              port: 443
    """).strip())
    source_ctx = {"workloadId": "orders-api", "namespace": "orders", "serviceAccount": "orders-api"}
    try:
        extract_from_helm_values(f, source_ctx)
    except ExtractionError as e:
        assert "wildcard" in str(e).lower()
        return
    raise AssertionError("Expected ExtractionError for wildcard host")
