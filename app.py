"""Fortress Command: a persistent, asynchronous airfield command prototype."""
import os
from pathlib import Path
import secrets
import time

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

import game_engine as engine
from models import TRAITS, briefing, new_campaign
from content import TOUR_LENGTHS, chapter
from storage import CampaignStore


def persistent_secret(path):
    configured = os.environ.get("B17_SECRET_KEY")
    if configured:
        return configured
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text()
    with os.fdopen(fd, "w") as stream:
        secret = secrets.token_hex(32)
        stream.write(secret)
    return secret


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        DATABASE=os.environ.get("B17_DATABASE", str(Path(app.instance_path) / "campaigns.sqlite3")),
        SECRET_KEY=None, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("B17_SECURE_COOKIE") == "1",
        MAX_CONTENT_LENGTH=16 * 1024,
        ALLOW_FAST_FORWARD=os.environ.get("B17_ALLOW_FAST_FORWARD", "1") == "1",
        NOW=time.time,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = persistent_secret(Path(app.instance_path) / "session.key")
    store = CampaignStore(app.config["DATABASE"])
    app.extensions["campaign_store"] = store

    def identity():
        if "campaign_id" not in session:
            session["campaign_id"] = secrets.token_urlsafe(24)
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        session.permanent = True
        return session["campaign_id"]

    @app.template_filter("remaining")
    def remaining(seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds}s"
        minutes = (seconds + 59) // 60
        return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"

    @app.get("/")
    def index():
        state = store.transact(identity(), app.config["NOW"]())
        now = app.config["NOW"]() + state["clock_offset"]
        missions = briefing(state) if not state["completed"] else []
        bay_busy = any(p["job"] and p["job"]["kind"] == "repair" for p in state["aircraft"])
        rest_busy = any(p["job"] and p["job"]["kind"] == "rest" for p in state["aircraft"])
        ready = sum(engine.availability(state, p) == "Available" for p in state["aircraft"])
        return render_template("airfield.html", state=state, now=now, missions=missions,
            engine=engine, traits=TRAITS, bay_busy=bay_busy, rest_busy=rest_busy, ready=ready,
            next_event=engine.next_event(state), fast_forward=app.config["ALLOW_FAST_FORWARD"],
            chapter=chapter(state), tour_lengths=TOUR_LENGTHS, decision_blocker=engine.decision_blocker(state),
            veterans=sorted((p for p in state["aircraft"] if p.get("crew_fate") == "safe"), key=lambda p: p["sorties"], reverse=True)[:3])

    @app.get("/status")
    def status():
        state = store.transact(identity(), app.config["NOW"]())
        return jsonify(revision=state["revision"])

    @app.post("/command/<command>")
    def command(command):
        campaign_id = identity()
        if not secrets.compare_digest(request.form.get("csrf", "").encode(), session["csrf"].encode()):
            abort(400, "This form has expired. Reload the airfield before trying again.")
        try:
            revision = int(request.form.get("revision", "-1"))
        except ValueError:
            abort(400)

        def execute(state, now):
            if command == "dispatch":
                engine.dispatch(state, request.form.get("mission"), request.form.getlist("aircraft"), now)
            elif command in ("repair", "rest"):
                engine.start_job(state, request.form.get("plane"), command, now)
            elif command == "requisition":
                engine.requisition(state, request.form.get("plane"), now)
            elif command == "stand-down":
                engine.stand_down(state, now)
            elif command == "advance":
                if not app.config["ALLOW_FAST_FORWARD"]:
                    raise engine.RuleError("Fast-forward is disabled on this server.")
                event = engine.next_event(state)
                if not event:
                    raise engine.RuleError("No scheduled work to fast-forward.")
                state["clock_offset"] += max(0, event[0] - now)
                engine.advance(state, event[0])
            elif command == "ground-choice":
                engine.choose_ground(state, request.form.get("decision"), request.form.get("choice"), now)
            elif command == "tour-length":
                try:
                    length = int(request.form.get("length", "0"))
                except ValueError:
                    raise engine.RuleError("Choose a valid tour length.")
                engine.set_tour_length(state, length)
            elif command == "reset":
                try:
                    fresh = new_campaign(length=int(request.form.get("length", "21")))
                except ValueError as error:
                    raise engine.RuleError(str(error)) from error
                previous_revision = state["revision"]
                state.clear()
                state.update(fresh)
                state["revision"] = previous_revision
            else:
                raise engine.RuleError("Unknown airfield command.")

        try:
            store.transact(campaign_id, app.config["NOW"](), execute, revision)
        except engine.RuleError as error:
            flash(str(error), "error")
        return redirect(url_for("index"), code=303)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("B17_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
