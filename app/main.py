from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_auth, routes_rooms, routes_users
from app.core.config import settings
from app.core.database import SessionLocal
from app.seed import seed_first_admin
from app.ws import room_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_first_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Allow every origin. We authenticate with a bearer token in the
    # Authorization header (not cookies), so credentials can stay off, which
    # lets us safely use the "*" wildcard.
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


app.include_router(routes_auth.router)
app.include_router(routes_users.router)
app.include_router(routes_rooms.router)
app.include_router(room_ws.router)
