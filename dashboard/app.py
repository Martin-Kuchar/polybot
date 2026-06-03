from __future__ import annotations
import logging

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

log = logging.getLogger(__name__)


def create_app(config, tracker, bot):
    """
    Returns (app, socketio). Call socketio.run(app, ...) to serve.
    Also wires bot.on_tick so each bot tick pushes a WebSocket event.
    """
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "polybot-internal"
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*", logger=False, engineio_logger=False)

    # ── REST endpoints ────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/stats")
    def api_stats():
        return jsonify(tracker.stats())

    @app.route("/api/trades")
    def api_trades():
        limit = int(request.args.get("limit", 50))
        return jsonify(tracker.all_trades(limit=limit))

    @app.route("/api/markets")
    def api_markets():
        return jsonify(bot.status.get("active_markets", []))

    @app.route("/api/balance")
    def api_balance():
        try:
            b = bot.api.get_balance()
            return jsonify({"usdc": b.usdc, "matic": b.matic})
        except Exception as e:
            return jsonify({"usdc": 0.0, "matic": 0.0, "error": str(e)})

    @app.route("/api/status")
    def api_status():
        return jsonify(bot.status)

    @app.route("/api/control/start", methods=["POST"])
    def api_start():
        bot.start()
        return jsonify({"ok": True, "running": bot.is_running()})

    @app.route("/api/control/stop", methods=["POST"])
    def api_stop():
        bot.stop()
        return jsonify({"ok": True, "running": bot.is_running()})

    # ── WebSocket push ────────────────────────────────────────────────────────

    def push_tick(status: dict):
        socketio.emit("tick", {
            "markets": status.get("active_markets", []),
            "last_action": status.get("last_action", ""),
            "last_error": status.get("last_error", ""),
            "running": status.get("running", False),
            "tick_count": status.get("tick_count", 0),
            "stats": tracker.stats(),
        })

    def push_resolution(data: dict):
        socketio.emit("resolution", data)

    def push_trade(trade: dict):
        socketio.emit("trade", trade)

    bot.on_tick = push_tick
    bot.on_resolution = push_resolution
    bot.on_trade = push_trade

    return app, socketio
