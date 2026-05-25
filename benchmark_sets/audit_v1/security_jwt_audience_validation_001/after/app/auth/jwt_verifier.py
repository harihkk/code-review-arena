from app.auth.settings import EXPECTED_AUDIENCE, EXPECTED_ISSUER


def verify_token(token: dict) -> bool:
    return bool(token.get("signature_valid"))
