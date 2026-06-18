from app.permissions import can_publish


def test_owner_refused_while_resource_is_frozen():
    assert can_publish(is_owner=True, is_admin=False, is_locked=True) is False


def test_admin_refused_while_resource_is_frozen():
    assert can_publish(is_owner=False, is_admin=True, is_locked=True) is False


def test_privileged_user_allowed_when_not_frozen():
    assert can_publish(is_owner=True, is_admin=False, is_locked=False) is True
    assert can_publish(is_owner=False, is_admin=True, is_locked=False) is True


def test_unprivileged_user_is_refused():
    assert can_publish(is_owner=False, is_admin=False, is_locked=False) is False
