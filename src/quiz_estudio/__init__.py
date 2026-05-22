from __future__ import annotations

from flask import Flask

from .blueprints.import_questions import import_bp
from .blueprints.quiz import quiz_bp
from .blueprints.simulacro import simulacro_bp
from .blueprints.stats import stats_bp
from .config import SECRET_KEY
from .db import init_stats_db


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    app.register_blueprint(quiz_bp)
    app.register_blueprint(simulacro_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(import_bp)

    init_stats_db()

    @app.route("/ping")
    def ping():
        # Lightweight health endpoint used by long-running pages (simulacro)
        return {"status": "ok"}

    return app
