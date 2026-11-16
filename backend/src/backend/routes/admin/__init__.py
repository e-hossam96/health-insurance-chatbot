from fastapi import APIRouter

from backend.routes.admin import catalog, complaints, kb, slots, visits

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(catalog.router)
router.include_router(slots.router)
router.include_router(visits.router)
router.include_router(complaints.router)
router.include_router(kb.router)
