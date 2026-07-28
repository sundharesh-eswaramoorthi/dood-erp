from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.middleware import IdempotencyMiddleware
from app.modules.activity.router import router as activity_router
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as health_router
from app.modules.parties.router import router as parties_router
from app.modules.products.router import router as products_router
from app.modules.settings.router import router as settings_router
from app.modules.stock.router import router as stock_router
from app.modules.units.router import router as units_router

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

# Dev CORS: the SPA sends a Bearer token (no cookies), so credentials stay off
# and a wildcard origin is fine. Phase 1 tightens this to the real origin list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.add_middleware(IdempotencyMiddleware)

app.include_router(health_router, tags=["health"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(parties_router, prefix="/api/v1/parties", tags=["parties"])
app.include_router(units_router, prefix="/api/v1/units", tags=["units"])
app.include_router(products_router, prefix="/api/v1/products", tags=["products"])
app.include_router(stock_router, prefix="/api/v1/stock", tags=["stock"])
app.include_router(settings_router, prefix="/api/v1", tags=["settings"])
app.include_router(activity_router, prefix="/api/v1/activity", tags=["activity"])


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "status": "ok", "docs": "/docs"}
