"""Giao diện web nhỏ bằng Flask."""
from flask import Flask, jsonify, render_template, request

from .core import Manager


def create_app(manager: Manager) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/tasks")
    def tasks():
        return jsonify(manager.snapshot())

    @app.post("/api/tasks")
    def add():
        text = (request.get_json(silent=True) or {}).get("links", "")
        try:
            added = manager.add_many(text)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify([t.to_dict() for t in added])

    @app.post("/api/tasks/<tid>/<action>")
    def act(tid, action):
        if tid not in manager.tasks or action not in ("pause", "resume"):
            return jsonify({"error": "không tìm thấy"}), 404
        getattr(manager, action)(tid)
        return jsonify(manager.tasks[tid].to_dict())

    return app
