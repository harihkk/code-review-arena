from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_tenant_admin

router = APIRouter()


@router.post("/tenants/{tenant_id}/admin/reset")
def reset_tenant(tenant_id: str, current_user=Depends(require_tenant_admin)):
    user = current_user or get_current_user()
    if user.get("tenant_id") != tenant_id or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Tenant admin required")
    return {"reset": tenant_id, "by": user["id"]}
