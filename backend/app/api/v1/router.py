"""
Главный router для API v1
"""
from fastapi import APIRouter

from app.api.v1.endpoints import contracts, testing

router = APIRouter()

router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
router.include_router(testing.router, prefix="/testing", tags=["testing"])
