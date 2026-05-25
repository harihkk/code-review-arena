from fastapi import APIRouter, Depends

router = APIRouter()


def require_admin():
    return {"id": 1, "role": "admin"}


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user=Depends(require_admin)):
    return {"deleted_user_id": user_id, "deleted_by": current_user["id"]}

