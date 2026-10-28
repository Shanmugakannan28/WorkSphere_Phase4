import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, engine, migrate
from .routers import (account, analytics, announcements, attendance, auth, documents, employees, feedback,
                      integrations, leaves, notifications, onboarding, payroll, performance, reports,
                      resignations, shifts, tasks, users)
from .seed import seed, seed_phase4
from .services import auto_mark, expiry_alerts


def run_maintenance():
    with SessionLocal() as db:
        auto_mark(db)       # auto-mark absent / on-leave once a shift has ended
        expiry_alerts(db)   # document expiry notifications


async def maintenance_loop():
    while True:
        try:
            await asyncio.to_thread(run_maintenance)
        except Exception as exc:  # keep the loop alive
            print("maintenance error:", exc)
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    migrate()
    with SessionLocal() as db:
        seed(db)
        seed_phase4(db)
    task = asyncio.create_task(maintenance_loop())
    yield
    task.cancel()


app = FastAPI(title="WorkSphere HRMS", version="3.0.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


for r in (auth, employees, shifts, attendance, leaves, documents, performance, payroll, notifications, analytics, users, onboarding, resignations,
          announcements, tasks, feedback, account, integrations, reports):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Frontend is served from the same origin/port as the API.
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
