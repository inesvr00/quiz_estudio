from __future__ import annotations

import secrets

from flask import Flask

from .blueprints.import_questions import import_bp
from .blueprints.quiz import quiz_bp
from .blueprints.stats import stats_bp
from .config import IS_PRODUCTION, SECRET_KEY
from .db import init_stats_db


def create_app() -> Flask:
    app = Flask(__name__)
    if not SECRET_KEY and IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY es obligatorio en produccion.")
    app.secret_key = SECRET_KEY or secrets.token_hex(32)

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}, 200

    app.register_blueprint(quiz_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(import_bp)

    init_stats_db()

    return app
