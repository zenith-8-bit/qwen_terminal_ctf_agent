from flask import Flask, jsonify, render_template
from .state import State

def create_app(settings):
    app=Flask(__name__,template_folder="../templates",static_folder="../static")
    state=State()
    @app.get("/")
    def index():
        return render_template("index.html")
    @app.get("/api/state")
    def api():
        return jsonify(state.snapshot())
    return app
