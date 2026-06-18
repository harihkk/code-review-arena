def is_eligible(age: int, has_consent: bool) -> bool:
    """Eligible only when the user is old enough and consent was given."""
    return age >= 18 and has_consent
