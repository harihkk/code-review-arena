from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


def get_current_user():
    return {"id": 1, "role": "member"}


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user=Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Login required")
    return {"deleted_user_id": user_id, "deleted_by": current_user["id"]}

