from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine
from .config import Config
from .extensions import csrf, db, migrate


@event.listens_for(Engine, "connect")
def sqlite_settings(connection, _record):
    if connection.__class__.__module__.startswith("sqlite3"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config:
        app.config.from_mapping(config)
    if not app.config.get("TESTING") and not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY é obrigatória fora dos testes")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app); migrate.init_app(app, db); csrf.init_app(app)
    from . import models
    from .routes import bp
    app.register_blueprint(bp)
    from .commands import register_commands
    register_commands(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; media-src 'self' blob:")
        return response

    @app.template_filter("br_datetime")
    def br_datetime(value):
        return value.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M") if value else "—"

    @app.errorhandler(403)
    def forbidden(_error): return ("Acesso não autorizado.", 403)
    @app.errorhandler(404)
    def missing(_error): return ("Página não encontrada.", 404)
    return app
