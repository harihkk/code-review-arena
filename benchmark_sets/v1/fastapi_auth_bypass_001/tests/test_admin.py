from app.routes.admin import delete_user


def test_member_cannot_delete_users():
    result = delete_user(42, {"id": 7, "role": "member"})
    assert result is None, "a member must not be allowed to delete users"

