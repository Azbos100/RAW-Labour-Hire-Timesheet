"""
RAW Labour Hire - Timesheet API
Main FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .routes import auth, timesheets, users, clients, clock, myob
from .database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title="RAW Labour Hire - Timesheet API",
    description="Digital timesheet system with GPS tracking and MYOB integration",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - allow mobile app and web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # Web dashboard dev
        "http://localhost:19006",     # Expo web
        "http://localhost:8081",      # React Native
        "*",                          # Mobile apps
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(clients.router, prefix="/api/clients", tags=["Clients"])
app.include_router(timesheets.router, prefix="/api/timesheets", tags=["Timesheets"])
app.include_router(clock.router, prefix="/api/clock", tags=["Clock In/Out"])
app.include_router(myob.router, prefix="/api/myob", tags=["MYOB Integration"])


@app.get("/")
async def root():
    return {
        "service": "RAW Labour Hire - Timesheet API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "raw-timesheet-api"
    }
