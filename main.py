from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from starlette.middleware.cors import CORSMiddleware
from app.common.logger import get_logger
from app.common.config import PROJECT_NAME, ALLOWED_HOSTS, DEBUG
from app.common.db import db
from app.common.services.exception_handler import EXCEPTION_HANDLERS
from app.auth.routers.google_auth import (
    router as google_auth_router
)
from app.email.routers.email_router import (
    router as email_router
)
from app.email.routers.contact_router import (
    router as contact_router
)
from app.template.routers.template_router import (
    router as template_router,
)
from app.jobs.routers.job_router import (
    router as job_router,
)
from app.users.routes import (
    router as users_router,
)
from app.interview.router.interview_routes import (
    router as interview_router,
)
from app.news.routers.news_routes import (
    router as news_routes,  
)
from app.job_browse.routers.job_browse_router import (
    router as job_browse_router,    
)
from app.admin.routers.admin_router import (
    router as admin_router, 
)
from app.resume.routes import router as resume_router
from app.jobs.routers.gmail_webhook_router import router as gmail_router
from contextlib import asynccontextmanager
import os

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown events.
    """

    logger.info("Connecting to MongoDB...")
    db.connect_to_mongo()  # Use await if this is async

    yield

    logger.info("Closing MongoDB connection...")
    db.close_mongo_connection()  # Use await if this is async

app = FastAPI(
    title=PROJECT_NAME, exception_handlers=EXCEPTION_HANDLERS, debug=DEBUG, lifespan=lifespan
)

if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOSTS,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(google_auth_router)
app.include_router(email_router)
app.include_router(contact_router)
app.include_router(template_router)
app.include_router(job_router)
app.include_router(
    gmail_router,
    prefix="/jobs",
    tags=["gmail-webhooks"],
)
app.include_router(
    users_router,
    prefix="/users",
    tags=["Users"],
)
app.include_router(
    resume_router,
    prefix="/resume",
    tags=["Resume"],
)
app.include_router(
    interview_router,
    prefix="/interview",
    tags=["Interview"],
)
app.include_router(
    news_routes,
    prefix="/news",
    tags=["News"],
)
app.include_router(
    job_browse_router,
    prefix="/jobs",
    tags=["Job Browse"],
)
app.include_router(
    admin_router,   
    prefix="/admin",
    tags=["Admin"],
)