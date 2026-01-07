from fastapi import APIRouter
from .florence_api import florence_router

api_router = APIRouter(
    prefix="/v1"
)
api_router.include_router(florence_router)