from fastapi import HTTPException


def get_current_user():
    return {"id": 7, "tenant_id": "tenant-a", "role": "member"}


def require_tenant_admin(tenant_id: str):
    user = get_current_user()
    if user.get("tenant_id") != tenant_id or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Tenant admin required")
    return user
