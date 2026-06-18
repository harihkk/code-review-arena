import pytest
from fastapi import HTTPException

from app.routes.tenant_admin import reset_tenant


def test_member_cannot_reset_other_workspace():
    member = {"id": 7, "tenant_id": "tenant-a", "role": "member"}
    with pytest.raises(HTTPException) as exc:
        reset_tenant("tenant-a", member)
    assert exc.value.status_code == 403
