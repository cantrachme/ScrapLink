
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings


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


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": f"{settings.APP_NAME} API",
        "environment": settings.APP_ENV,
        "version": app.version,
    }
