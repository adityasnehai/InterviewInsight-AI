from fastapi import APIRouter, Depends, HTTPException, status

from app.api.security import get_current_user
from app.models.user import UserPerformanceHistoryResponse
from app.services.session_store import session_store

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/{userId}/performance-history", response_model=UserPerformanceHistoryResponse)
def get_user_performance_history(
    userId: str,
    current_user: dict = Depends(get_current_user),
) -> UserPerformanceHistoryResponse:
    if str(current_user["userId"]) != str(userId):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for this user")
    payload = session_store.get_user_performance_history(userId)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User history not found")
    return UserPerformanceHistoryResponse(**payload)
