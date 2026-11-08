# stockbot

A **stocks-only** research, backtesting and paper-trading bot for Windows, macOS and Linux (Python 3.10+). No crypto: crypto tickers are rejected and the broker module only touches US equities.

> **Read this first.** Nobody can promise a bot that beats the market, and this one does not. It is an honest framework for testing whether an idea beats SPY *after costs*, with the guard rails that stop you fooling yourself. Not financial advice; you can lose money.

## What it does

| Command | Purpose |
|---|---|
| `stockbot backtest` | Walk-forward backtest vs SPY with costs, 1-day execution lag, optional out-of-sample slice |
| `stockbot signals` | Today's target portfolio |
| `stockbot trade` | Rebalance an [Alpaca](https://alpaca.markets) **paper** account (dry run unless `--execute`) |

Strategies (`--strategy`):

- `momentum` (default): 12-1 month momentum, top-N positive-momentum stocks, inverse-volatility weights (25% cap), and a regime filter that moves to cash when SPY is below its 200-day average.
- `ml`: gradient-boosted model that predicts next-month cross-sectional return rank from momentum, volatility and relative-strength features. Trained walk-forward only on outcomes already known on each decision date, retrained every 6 months.

## Install

```bash
git clone <this repo>
cd stockbot
python -m venv .venv
# macOS/Linux: source .venv/bin/activate     Windows: .venv\Scripts\activate
pip install -e .
```

## Use

```bash
stockbot backtest --strategy momentum --oos-start 2018-01-01
stockbot backtest --strategy ml --top 15 --cost-bps 10
stockbot signals --tickers AAPL,MSFT,NVDA,GOOGL,AMZN,META,JPM,XOM,LLY,COST
```

Paper trading (free Alpaca paper account):

```bash
export ALPACA_KEY_ID=...        # Windows PowerShell: $env:ALPACA_KEY_ID="..."
export ALPACA_SECRET_KEY=...
stockbot trade                  # prints the orders it would place
stockbot trade --execute        # places them in the PAPER account
```

Live trading is blocked unless you pass `--live` **and** set `STOCKBOT_ALLOW_LIVE=yes`. Only symbols in the bot's universe are ever traded; your other holdings are left alone.

## Honest results (run 2026-11-07, Yahoo data 2008-2026, 63 large caps, 5 bps costs)

| | CAGR | Sharpe | Max DD | Beta | $1 grows to |
|---|---|---|---|---|---|
| SPY | 15.1% | 0.89 | -33.7% | 1.00 | 12.20 |
| momentum | 16.0% | 0.91 | -29.0% | 0.62 | 13.98 |
| ml | 14.4% | 0.86 | -29.9% | 0.58 | 10.95 |

Since 2018 (out-of-sample slice) both strategies trail SPY on total return (momentum 11.0% vs 13.7% CAGR; ml 13.1% vs 13.7%), though with smaller drawdowns. **Conclusion: no reliable edge over buy-and-hold SPY here.** Momentum's full-period lead is small and fades out of sample. The value is in lower drawdown and a framework to test your own ideas.

## Known limitations

- **Survivorship bias:** the universe is today's large caps, which flatters every backtest.
- Yahoo data is free but imperfect; costs ignore slippage and taxes.
- The 2008-2026 window includes a long bull market; regime filters look better or worse depending on the window.
- Tuning parameters on the same history you report is overfitting. Use `--oos-start`.

## Develop

```bash
pip install -e ".[dev]"
pytest
```

CI runs the tests on Ubuntu, Windows and macOS.

## License

MIT
