from app.auth.settings import EXPECTED_AUDIENCE, EXPECTED_ISSUER


def verify_token(token: dict) -> bool:
    if not token.get("signature_valid"):
        return False
    if token.get("aud") != EXPECTED_AUDIENCE:
        return False
    if token.get("iss") != EXPECTED_ISSUER:
        return False
    return True
