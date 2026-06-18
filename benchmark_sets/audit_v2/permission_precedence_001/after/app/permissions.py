def can_publish(is_owner: bool, is_admin: bool, is_locked: bool) -> bool:
    """A privileged user may publish unless the resource is frozen."""
    return is_owner or is_admin and not is_locked
