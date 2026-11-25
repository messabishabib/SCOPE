from fastapi import APIRouter


router = APIRouter(prefix="/api", tags=["Platform"])


@router.get("/health")
def health():
    return {"status": "ok"}
