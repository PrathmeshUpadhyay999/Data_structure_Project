"""Flask dashboard for the heatwave monitoring system."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from heatwave_api.engine import EngineCache, forecast_for_location, iso_day, list_locations, top_alerts
from heatwave_api.routes import ApiContext, dispatch
from heatwave_pipeline import config
from heatwave_pipeline.ingestion import now_ist

from .advisories import generate_advisories


def create_app(db_path=None) -> Flask:
    """Build the dashboard and bind it to an existing heatwave database."""
    path = Path(db_path or config.DEFAULT_DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"database not found at {path}; run 'python main.py init' first")

    context = ApiContext(path, EngineCache(path))
    context.engine()
    app = Flask(__name__)
    app.config["HEATWAVE_API_CONTEXT"] = context

    @app.get("/")
    def dashboard():
        return render_template("index.html")

    @app.get("/api/dashboard")
    def dashboard_data():
        raw_days = request.args.get("days", "1")
        try:
            days = int(raw_days)
        except ValueError:
            return jsonify({"error": "'days' must be an integer"}), 400
        if not 1 <= days <= 7:
            return jsonify({"error": "'days' must be between 1 and 7"}), 400

        status, quality = dispatch(context, "GET", "/api/quality")
        if status != 200:
            return jsonify(quality), status

        engine = context.engine()
        locations = list_locations(engine)
        alerts = top_alerts(engine, 200)
        forecasts = []
        for location in locations:
            forecast = forecast_for_location(engine, location["id"], days)
            if forecast is not None:
                forecasts.append(forecast)

        advisories = generate_advisories(forecasts, alerts)
        conn = context.connect()
        try:
            live_readings = [
                dict(row)
                for row in conn.execute(
                    """SELECT o.id, o.station_id, o.region, o.latitude, o.longitude,
                              o.observed_at, o.ingested_at, o.temperature_c, o.humidity
                         FROM observations AS o
                         JOIN (
                               SELECT station_id, MAX(id) AS latest_id
                                 FROM observations
                                WHERE source = 'AWS'
                                GROUP BY station_id
                         ) AS latest ON latest.latest_id = o.id
                        ORDER BY o.ingested_at DESC, o.id DESC
                        LIMIT 10"""
                )
            ]
            temperature_history = []
            if live_readings:
                latest_station_id = live_readings[0]["station_id"]
                temperature_history = [
                    dict(row)
                    for row in conn.execute(
                        """SELECT observed_at, temperature_c, humidity
                             FROM observations
                            WHERE source = 'AWS' AND station_id = ?
                            ORDER BY observed_at DESC, id DESC
                            LIMIT 24""",
                        (latest_station_id,),
                    )
                ]
                temperature_history.reverse()
        finally:
            conn.close()
        latest_ingested_at = live_readings[0]["ingested_at"] if live_readings else None
        feed_age_seconds = None
        if latest_ingested_at:
            feed_age_seconds = round(
                (now_ist() - datetime.fromisoformat(latest_ingested_at)).total_seconds(),
                1,
            )
        return jsonify({
            "as_of": iso_day(engine.as_of_day),
            "days_ahead": days,
            "locations": locations,
            "forecasts": forecasts,
            "alerts": alerts,
            "pending_alerts": len(engine.alerts),
            "advisories": advisories,
            "quality": quality,
            "live_readings": live_readings,
            "temperature_history": temperature_history,
            "history_station": live_readings[0]["station_id"] if live_readings else None,
            "live_feed": {
                "active": feed_age_seconds is not None and 0 <= feed_age_seconds <= 15,
                "age_seconds": feed_age_seconds,
                "last_ingested_at": latest_ingested_at,
            },
        })

    @app.get("/api/<path:api_path>")
    def existing_api(api_path):
        target = f"/api/{api_path}"
        if request.query_string:
            target += "?" + request.query_string.decode("ascii")
        status, payload = dispatch(context, request.method, target)
        return jsonify(payload), status

    return app


__all__ = ["create_app"]
