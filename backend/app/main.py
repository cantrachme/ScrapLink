
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings

from backend.app.api.routes.jobs import router as jobs_router

from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description="Backend API for the ScrapLink job discovery platform",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Allow the React frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(jobs_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": f"{settings.APP_NAME} API",
        "environment": settings.APP_ENV,
        "version": app.version,
    }



@app.get("/health/db")
def database_health(
    db: Session = Depends(get_db),
):
    """Verify the database connection."""

    try:
        result = db.execute(text("SELECT 1")).scalar_one()

        return {
            "status": "healthy",
            "database": "postgresql",
            "connected": result == 1,
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )
