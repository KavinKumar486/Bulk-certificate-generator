from fastapi import APIRouter, Depends

from app.auth import verify_api_key

router = APIRouter(
    prefix="/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/test", include_in_schema=False)
def test_auth():
    return {"status": "ok"}
