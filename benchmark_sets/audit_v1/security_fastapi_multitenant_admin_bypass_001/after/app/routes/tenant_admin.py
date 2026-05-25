from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user

router = APIRouter()


@router.post("/tenants/{tenant_id}/admin/reset")
def reset_tenant(tenant_id: str, current_user=Depends(get_current_user)):
    user = current_user or get_current_user()
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return {"reset": tenant_id, "by": user["id"]}
