import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///contadega.sqlite")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    BACKUP_DIRECTORY = os.getenv("BACKUP_DIRECTORY", "backups")
    BACKUP_RETENTION = int(os.getenv("BACKUP_RETENTION", "14"))
    OFFLINE_RETENTION_DAYS = int(os.getenv("OFFLINE_RETENTION_DAYS", "30"))
