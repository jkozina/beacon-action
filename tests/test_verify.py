# Lightweight smoke: a round-trip test would require a private key in the Action repo,
# which we deliberately don't have. Instead, sanity-check the malformed-signature path.
from scripts.verify_signature import verify_verdict


def test_verify_rejects_missing_signature():
    assert verify_verdict({"decisionId": "x"}) is False


def test_verify_rejects_wrong_prefix():
    assert verify_verdict({"decisionId": "x", "signature": "wrong:v1:abc"}) is False
