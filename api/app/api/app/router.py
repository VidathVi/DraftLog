from fastapi.routing import APIRouter

from .routers import meta, organizations, teams, users

router = APIRouter()

router.include_router(meta.router)
router.include_router(users.router)
router.include_router(organizations.router)
router.include_router(teams.router)
