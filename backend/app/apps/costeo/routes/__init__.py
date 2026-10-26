from fastapi import APIRouter

from app.apps.costeo.routes import costeo, mfp

router = APIRouter(prefix="/costeo", tags=["costeo y MFP"])
router.include_router(mfp.router)
router.include_router(costeo.router)
