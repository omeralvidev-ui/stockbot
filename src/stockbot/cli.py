"""Command line interface: backtest | signals | trade | autopilot | gui."""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from .backtest import run_backtest
from .metrics import compare, format_table
from .service import STRATEGIES, load_universe, make_strategy
from .universe import BENCHMARK

DISCLAIMER = ("Research software, not financial advice. Past/backtested performance does not "
              "predict future results; you can lose money.")


def _load(args):
    return load_universe(args.tickers, args.start, not args.no_cache)


def cmd_backtest(args) -> int:
    stocks, bench = _load(args)
    print(f"Universe: {stocks.shape[1]} stocks, {stocks.index[0].date()} -> {stocks.index[-1].date()}")
    res = run_backtest(stocks, bench, make_strategy(args.strategy, args.top, args.risk_off), cost_bps=args.cost_bps)
    print(f"\n=== {args.strategy} vs {BENCHMARK} (full period, costs {args.cost_bps} bps) ===")
    print(format_table(compare(res.equity, res.bench_equity, BENCHMARK)))
    print(f"Average turnover per rebalance: {res.turnover:.0%}")
    if args.oos_start:
        cut = pd.Timestamp(args.oos_start)
        e, b = res.equity[res.equity.index >= cut], res.bench_equity[res.bench_equity.index >= cut]
        if len(e) > 30:
            print(f"\n=== Out-of-sample slice from {args.oos_start} ===")
            print(format_table(compare(e / e.iloc[0], b / b.iloc[0], BENCHMARK)))
    s, b = res.equity.iloc[-1], res.bench_equity.iloc[-1]
    print(f"\nEnding value of $1: strategy {s:.2f} vs {BENCHMARK} {b:.2f} -> "
          f"{'ahead of' if s > b else 'BEHIND'} the benchmark in this test.")
    print("Caveat: universe is today's large caps (survivorship bias). " + DISCLAIMER)
    if args.out:
        pd.DataFrame({"strategy": res.equity, BENCHMARK: res.bench_equity}).to_csv(args.out)
        print(f"Saved equity curves to {args.out}")
    return 0


def cmd_signals(args) -> int:
    stocks, bench = _load(args)
    w = make_strategy(args.strategy, args.top, args.risk_off)(stocks, bench)
    w = w[w > 0].sort_values(ascending=False)
    sent = {}
    if args.news and not w.empty:
        from .risk import RiskConfig, apply_sentiment_overlay
        from .sentiment import scan

        sent = scan(list(w.index), os.environ.get("X_BEARER_TOKEN"))
        w, notes = apply_sentiment_overlay(w, sent, RiskConfig())
        w = w[w > 0]
        for n in notes:
            print("  ! " + n)
    print(f"Target portfolio as of {stocks.index[-1].date()} ({args.strategy}):")
    if w.empty:
        print("  100% cash (risk-off regime or no qualifying stocks)")
    for sym, wt in w.items():
        extra = f"  news {sent[sym].score:+.2f} ({sent[sym].n} items)" if sym in sent else ""
        print(f"  {sym:<6} {wt:6.1%}{extra}")
    print(f"  cash   {1 - w.sum():6.1%}\n{DISCLAIMER}")
    return 0


def _broker(args):
    if args.broker == "sim":
        from .sim import SimBroker

        return SimBroker(start_cash=args.sim_cash, ignore_hours=args.anytime)
    from .broker import Alpaca

    return Alpaca(live=args.live)


def cmd_trade(args) -> int:
    from .autopilot import AutoConfig, build_rebalance_plan

    broker = _broker(args)
    cfg = AutoConfig(strategy=args.strategy, top=args.top, tickers=args.tickers, start=args.start,
                     x_token=os.environ.get("X_BEARER_TOKEN"), use_sentiment=not args.no_news)
    plan = build_rebalance_plan(cfg, broker)
    label = "LOCAL SIMULATION" if args.broker == "sim" else ("LIVE" if args.live else "PAPER")
    print(f"{label} account. {plan.describe()}")
    if not args.execute:
        print("Dry run. Re-run with --execute to place these orders.")
        return 0
    for o in plan.orders:
        broker.submit(o)
    print("Orders submitted.")
    return 0


def cmd_autopilot(args) -> int:
    from .autopilot import AutoConfig, Autopilot

    cfg = AutoConfig(strategy=args.strategy, top=args.top, tickers=args.tickers, start=args.start,
                     x_token=os.environ.get("X_BEARER_TOKEN"), use_sentiment=not args.no_news,
                     countdown_s=args.countdown, poll_minutes=args.poll_minutes)
    ap = Autopilot(cfg, _broker(args), log=lambda m: print(m, flush=True))
    ap.start()
    try:
        while ap.is_alive():
            ap.join(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        ap.stop()
        ap.join(5)
    return 0


def cmd_gui(args) -> int:
    from .gui import main as gui_main

    gui_main()
    return 0


def _watchlist(args):
    from .intraday import DEFAULT_WATCHLIST
    from .universe import validate_tickers

    return validate_tickers(args.tickers.split(",")) if args.tickers else list(DEFAULT_WATCHLIST)


def cmd_daytrade_backtest(args) -> int:
    from datetime import time as dtime

    from .intraday import ORBConfig, backtest_orb, fetch_intraday

    data = fetch_intraday(_watchlist(args), period=args.period)
    res = backtest_orb(data, ORBConfig(target_r=args.target_r), cost_bps=args.cost_bps)
    print("=== EXPERIMENTAL opening-range-breakout day trading (long-only, flat by close) ===")
    for k, v in res.stats.items():
        pct = k in ("win rate", "avg trade return", "total return", "max drawdown") or k.startswith("buy&hold")
        print(f"  {k:<46} {v:.1%}" if pct and isinstance(v, float) else
              f"  {k:<46} {v:.2f}" if isinstance(v, float) else f"  {k:<46} {v}")
    print("\nOnly ~60 days of 5-minute data exist on Yahoo, so this is a smoke test, NOT proof of an edge. "
          + DISCLAIMER)
    return 0


def cmd_daytrade(args) -> int:
    from .daytrader import DayTrader, make_day_broker

    if args.reset:
        make_day_broker().reset()
        print("Day-trading sim portfolio reset.")
        return 0
    dt = DayTrader(make_day_broker(ignore_hours=args.anytime), _watchlist(args), countdown_s=args.countdown,
                   poll_s=args.poll_seconds, log=lambda m: print(m, flush=True))
    dt.start()
    try:
        while dt.is_alive():
            dt.join(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        dt.stop()
        dt.join(5)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="stockbot", description="Stocks-only research and paper-trading bot.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gui", help="Open the desktop app").set_defaults(fn=cmd_gui)
    for name, fn, helptext in (("backtest", cmd_backtest, "Backtest vs SPY"),
                               ("signals", cmd_signals, "Show today's target portfolio"),
                               ("trade", cmd_trade, "Rebalance an Alpaca account (dry run by default)"),
                               ("autopilot", cmd_autopilot, "Run unattended: announce, wait, trade")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--strategy", choices=STRATEGIES, default="momentum")
        sp.add_argument("--tickers", help="Comma-separated stock tickers (default: built-in large caps)")
        sp.add_argument("--start", default="2008-01-01")
        sp.add_argument("--top", type=int, default=10, help="Number of holdings")
        sp.add_argument("--risk-off", type=float, default=0.0,
                        help="Exposure when SPY is below its 200-day average (0 = cash)")
        sp.add_argument("--no-cache", action="store_true")
        sp.set_defaults(fn=fn)
        if name == "backtest":
            sp.add_argument("--cost-bps", type=float, default=5.0, help="Cost per traded dollar, in bps")
            sp.add_argument("--oos-start", help="Also report stats from this date (e.g. 2018-01-01)")
            sp.add_argument("--out", help="Write equity curves to this CSV")
        if name == "signals":
            sp.add_argument("--news", action="store_true", help="Apply Google News / X sentiment veto")
        if name in ("trade", "autopilot"):
            sp.add_argument("--broker", choices=["sim", "alpaca"], default="sim",
                            help="sim = local virtual money at real yfinance prices (default); alpaca = Alpaca account")
            sp.add_argument("--sim-cash", type=float, default=100_000.0, help="Starting virtual cash (new sim only)")
            sp.add_argument("--anytime", action="store_true", help="Sim only: trade even when the US market is closed")
            sp.add_argument("--live", action="store_true", help="Alpaca only: use a live account (also needs STOCKBOT_ALLOW_LIVE=yes)")
            sp.add_argument("--no-news", action="store_true", help="Disable the sentiment veto")
        if name == "trade":
            sp.add_argument("--execute", action="store_true", help="Actually place orders")
        if name == "autopilot":
            sp.add_argument("--countdown", type=int, default=60, help="Seconds to wait (cancel window) before trading")
            sp.add_argument("--poll-minutes", type=int, default=15)
    for name, fn, helptext in (("daytrade-backtest", cmd_daytrade_backtest, "EXPERIMENTAL: backtest opening-range breakout on ~60d of 5m data"),
                               ("daytrade", cmd_daytrade, "EXPERIMENTAL: SIM-ONLY live day trader")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--tickers", help="Comma-separated watchlist (default: 15 liquid large caps)")
        sp.set_defaults(fn=fn)
        if name == "daytrade-backtest":
            sp.add_argument("--period", default="60d", help="Yahoo caps 5-minute data at 60d")
            sp.add_argument("--cost-bps", type=float, default=5.0)
            sp.add_argument("--target-r", type=float, default=2.0)
        else:
            sp.add_argument("--anytime", action="store_true", help="Trade even when the US market is closed (will have stale data)")
            sp.add_argument("--countdown", type=int, default=10, help="Cancel window in seconds before each entry")
            sp.add_argument("--poll-seconds", type=int, default=60)
            sp.add_argument("--reset", action="store_true", help="Reset the day-trading sim portfolio and exit")
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
