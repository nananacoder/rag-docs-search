from fastapi import APIRouter

from app.api.deps import SettingsDep

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(settings: SettingsDep) -> dict[str, str]:
    return {
        "status": "ok",
        "env": settings.app_env,
        "retrieval_backend": settings.retrieval_backend,
    }
