"""API routers aggregated under /api/v1.

Layout note: price + history endpoints live in ``pairs``; indicator
endpoints live in ``forecast``; model-metric endpoints live in ``models``.
"""

from fastapi import APIRouter

from app.api import forecast, health, jobs, models, pairs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(pairs.router)
api_router.include_router(forecast.router)
api_router.include_router(models.router)
api_router.include_router(jobs.router)
