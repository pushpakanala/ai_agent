import os

from .logger import get_logger

logger = get_logger(__name__)

PROJECT_NAME = "AI_AGENT"
ALLOWED_HOSTS = "*"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = os.getenv("PORT", 8000)
DEBUG = bool(os.getenv("ENV", "local") == True)


if os.getenv("DB_STRING", None):
    MONGODB_URL = os.getenv("DB_STRING")
else:
    DB_HOST, DB_PASSWORD, DB_USER, DB_PORT = (
        os.getenv("DB_HOST", "localhost"),
        os.getenv("DB_PASSWORD", "pass"),
        os.getenv("DB_USER", "user"),
        os.getenv("DB_PORT", 27107),
    )
    MONGODB_URL = f"mongodb://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/?authMechanism=DEFAULT&authSource=admin"

MONGODB = os.getenv("DB_NAME") if os.getenv("DB_NAME") else "Uniquest"

DATA_FOLDER = "./data"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "openid",
    "email",
    "profile",
]

SECRET_KEY=os.getenv("SECRET_KEY")
