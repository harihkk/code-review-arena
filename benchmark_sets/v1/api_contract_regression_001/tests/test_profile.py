from app.routes.profile import serialize_profile


class User:
    id = "u-1"
    display_name = "Ada"
    avatar_url = None


def test_existing_consumer_keeps_snake_case_contract():
    assert "user_id" in serialize_profile(User())

