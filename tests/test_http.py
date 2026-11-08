"""Exercise the Alpaca client and X parser against local mock servers (request shapes only)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from stockbot.broker import Alpaca, Order, PAPER_URL


class Handler(BaseHTTPRequestHandler):
    log = []

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, body=None):
        Handler.log.append((self.command, self.path, self.headers.get("APCA-API-KEY-ID"),
                            self.headers.get("APCA-API-SECRET-KEY"), body))

    def do_GET(self):
        self._record()
        if self.path == "/v2/account":
            self._send({"equity": "1000.00", "cash": "400.00", "last_equity": "990.00"})
        elif self.path == "/v2/clock":
            self._send({"is_open": True})
        elif self.path == "/v2/positions":
            self._send([{"symbol": "AAA", "market_value": "600", "asset_class": "us_equity"},
                        {"symbol": "BTCUSD", "market_value": "50", "asset_class": "crypto"}])
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self._record(json.loads(self.rfile.read(n)))
        self._send({"id": "order-1"})

    def do_DELETE(self):
        self._record()
        self._send({})

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    Handler.log = []
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_alpaca_client_request_shapes(server, monkeypatch):
    monkeypatch.setenv("ALPACA_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    b = Alpaca(base_url=server)
    assert float(b.account()["equity"]) == 1000.0 and b.clock()["is_open"]
    assert b.position_values() == {"AAA": 600.0}  # crypto position ignored
    b.submit(Order("AAA", "buy", 123.456))
    b.submit(Order("AAA", "sell", 0.0, close_all=True))
    post = next(x for x in Handler.log if x[0] == "POST")
    assert post[1] == "/v2/orders" and post[4] == {"symbol": "AAA", "side": "buy", "type": "market",
                                                    "time_in_force": "day", "notional": "123.46"}
    assert ("DELETE", "/v2/positions/AAA") in [(x[0], x[1]) for x in Handler.log]
    assert all(x[2] == "k" and x[3] == "s" for x in Handler.log)


def test_alpaca_defaults_to_paper_and_blocks_live(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.delenv("STOCKBOT_ALLOW_LIVE", raising=False)
    assert Alpaca().base == PAPER_URL
    with pytest.raises(RuntimeError):
        Alpaca(live=True)
    monkeypatch.delenv("ALPACA_KEY_ID")
    with pytest.raises(RuntimeError):
        Alpaca()


def test_x_parser_and_failure_isolation(monkeypatch):
    import requests

    from stockbot import sentiment

    class R:
        def raise_for_status(self): pass
        def json(self): return {"data": [{"text": "$AAA beats earnings, surge"}, {"text": "$AAA lawsuit and probe"}]}

    seen = {}

    def fake_get(url, **kw):
        seen.update(url=url, **kw)
        if "twitter" in url:
            return R()
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", fake_get)
    s = sentiment.ticker_sentiment("AAA", x_token="tok")
    assert seen["headers"]["Authorization"] == "Bearer tok" and seen["params"]["query"].startswith("$AAA")
    assert s.n == 2 and any("Google News unavailable" in n for n in s.notes)  # news failure didn't crash
