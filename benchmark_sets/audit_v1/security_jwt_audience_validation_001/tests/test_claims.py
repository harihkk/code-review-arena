from app.auth.jwt_verifier import verify_token


def _token(**overrides):
    base = {
        "signature_valid": True,
        "aud": "api.example.com",
        "iss": "https://auth.example.com",
    }
    base.update(overrides)
    return base


def test_valid_token_passes():
    assert verify_token(_token()) is True


def test_mismatched_claim_is_rejected():
    assert verify_token(_token(aud="other-service")) is False


def test_wrong_signer_is_rejected():
    assert verify_token(_token(iss="https://evil.example")) is False
