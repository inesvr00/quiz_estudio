from __future__ import annotations

from flask import Flask

from .blueprints.import_questions import import_bp
from .blueprints.quiz import quiz_bp
from .blueprints.stats import stats_bp
from .config import SECRET_KEY
from .db import init_stats_db


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}, 200

    app.register_blueprint(quiz_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(import_bp)

    init_stats_db()

    return app
