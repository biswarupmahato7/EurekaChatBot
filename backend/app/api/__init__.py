"""
backend/app/api/__init__.py
===========================
API routers package.
"""
from backend.app.api.chat import router as chat_router
from backend.app.api.health import router as health_router

__all__ = ["chat_router", "health_router"]
