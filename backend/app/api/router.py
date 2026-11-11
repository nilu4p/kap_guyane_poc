"""Aggregate API v1 routers."""

from fastapi import APIRouter

from app.api.endpoints import analyses, audit_log, auth, custom_sources, decision, equipements, imagery, rapports, system, territoire, users
from app.config import get_settings

api_router = APIRouter(prefix=get_settings().api_prefix)
for module in (auth, users, territoire, equipements, analyses, decision, rapports, imagery, audit_log, system, custom_sources):
    api_router.include_router(module.router)
