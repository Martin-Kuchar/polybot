from __future__ import annotations
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: str):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def main():
    from config import Config
    from tracker import TradeTracker
    from bot import Bot
    from dashboard.app import create_app

    config = Config()
    setup_logging(config.log_file)
    log = logging.getLogger("main")

    log.info("=" * 60)
    log.info("POLYBOT  secret message: vagi")
    log.info("  strategy   : %s", config.active_strategy)
    log.info("  production : %s", config.production)
    log.info("  shares/bet : %d", config.shares_per_bet)
    log.info("  watch      : T-%ds in [%.2f, %.2f)", config.watch_second, config.price_min, config.price_max)
    log.info("  bet range  : [%.2f, %.2f)", config.bet_price_min, config.bet_price_max)
    log.info("  dashboard  : http://%s:%d", config.dashboard_host, config.dashboard_port)
    log.info("=" * 60)

    if not config.production:
        log.warning("SIMULATION MODE — no real orders will be placed")

    if not config.private_key:
        log.error("PRIVATE_KEY not set in .env — cannot place real orders")
    if not config.deposit_wallet_address:
        log.error("DEPOSIT_WALLET_ADDRESS not set in .env")

    tracker = TradeTracker(config.trades_csv)
    bot = Bot(config, tracker)
    app, socketio = create_app(config, tracker, bot)

    def shutdown(signum, frame):
        log.info("Shutdown signal received — stopping bot")
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    bot.start()

    log.info("Dashboard running at http://%s:%d", config.dashboard_host, config.dashboard_port)
    socketio.run(
        app,
        host=config.dashboard_host,
        port=config.dashboard_port,
        use_reloader=False,
        log_output=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
