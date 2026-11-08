"""Command line interface: backtest | signals | trade."""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from .backtest import run_backtest
from .data import load_prices
from .metrics import compare, format_table
from .strategies import Momentum
from .universe import BENCHMARK, DEFAULT_UNIVERSE, validate_tickers

DISCLAIMER = ("Research software, not financial advice. Past/backtested performance does not "
              "predict future results; you can lose money.")


def _strategy(args):
    if args.strategy == "ml":
        from .ml import MLRank

        return MLRank(top_n=args.top, risk_off_exposure=args.risk_off)
    return Momentum(top_n=args.top, risk_off_exposure=args.risk_off)


def _load(args):
    tickers = validate_tickers(args.tickers.split(",")) if args.tickers else list(DEFAULT_UNIVERSE)
    tickers = [t for t in tickers if t != BENCHMARK]
    px = load_prices(tickers + [BENCHMARK], start=args.start, use_cache=not args.no_cache)
    bench = px[BENCHMARK]
    stocks = px.drop(columns=[BENCHMARK]).dropna(axis=1, how="all")
    return stocks, bench


def cmd_backtest(args) -> int:
    stocks, bench = _load(args)
    print(f"Universe: {stocks.shape[1]} stocks, {stocks.index[0].date()} -> {stocks.index[-1].date()}")
    res = run_backtest(stocks, bench, _strategy(args), cost_bps=args.cost_bps)
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
    w = _strategy(args)(stocks, bench)
    w = w[w > 0].sort_values(ascending=False)
    print(f"Target portfolio as of {stocks.index[-1].date()} ({args.strategy}):")
    if w.empty:
        print("  100% cash (risk-off regime or no qualifying stocks)")
    for sym, wt in w.items():
        print(f"  {sym:<6} {wt:6.1%}")
    print(f"  cash   {1 - w.sum():6.1%}\n{DISCLAIMER}")
    return 0


def cmd_trade(args) -> int:
    from .broker import Alpaca, plan_orders

    stocks, bench = _load(args)
    w = _strategy(args)(stocks, bench)
    broker = Alpaca(live=args.live)
    equity = float(broker.account()["equity"])
    orders = plan_orders(w[w > 0].to_dict(), broker.position_values(), equity, set(stocks.columns))
    print(f"{'LIVE' if args.live else 'PAPER'} account equity ${equity:,.2f}; {len(orders)} order(s):")
    for o in orders:
        print(f"  {o.side.upper():<4} {o.symbol:<6} ${o.notional:,.2f}{' (close position)' if o.close_all else ''}")
    if not args.execute:
        print("Dry run. Re-run with --execute to place these orders.")
        return 0
    if not broker.clock().get("is_open"):
        print("Market is closed; orders would queue until the next open.")
    for o in orders:
        broker.submit(o)
    print("Orders submitted.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="stockbot", description="Stocks-only research and paper-trading bot.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn, helptext in (("backtest", cmd_backtest, "Backtest vs SPY"),
                               ("signals", cmd_signals, "Show today's target portfolio"),
                               ("trade", cmd_trade, "Rebalance an Alpaca account (dry run by default)")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--strategy", choices=["momentum", "ml"], default="momentum")
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
        if name == "trade":
            sp.add_argument("--execute", action="store_true", help="Actually place orders")
            sp.add_argument("--live", action="store_true", help="Use a live account (also needs STOCKBOT_ALLOW_LIVE=yes)")
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
