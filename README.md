# stockbot

A **stocks-only** research, backtesting and paper-trading bot for Windows, macOS and Linux (Python 3.10+). No crypto: crypto tickers are rejected and the broker module only touches US equities.

> **Read this first.** Nobody can promise a bot that beats the market, and this one does not. It is an honest framework for testing whether an idea beats SPY *after costs*, with the guard rails that stop you fooling yourself. Not financial advice; you can lose money.

## What it does

| Command | Purpose |
|---|---|
| `stockbot backtest` | Walk-forward backtest vs SPY with costs, 1-day execution lag, optional out-of-sample slice |
| `stockbot signals` | Today's target portfolio |
| `stockbot trade` | Rebalance an [Alpaca](https://alpaca.markets) **paper** account (dry run unless `--execute`) |
| `stockbot autopilot` | Unattended: checks every N minutes, **announces** what it will do, waits a cancel window, then trades |
| `stockbot gui` / `stockbot-gui` | Desktop app: dashboard, signals + news, backtest, autopilot with pop-up countdown (sim or Alpaca paper) |

Strategies (`--strategy`):

- `momentum` (default): 12-1 month momentum, top-N positive-momentum stocks, inverse-volatility weights (25% cap), and a regime filter that moves to cash when SPY is below its 200-day average.
- `ensemble`: average of `momentum` and `ml`, scaled down to a 15% volatility target.
- `ml`: gradient-boosted model that predicts next-month cross-sectional return rank from momentum, volatility and relative-strength features. Trained walk-forward only on outcomes already known on each decision date, retrained every 6 months.

## Trading on your own computer (no broker needed)

yfinance only supplies prices; it cannot place orders. So `trade` and `autopilot` default to a **local simulated broker** (`--broker sim`): virtual money (default $100,000), real yfinance prices, 5 bps slippage, portfolio saved in `~/.stockbot/sim_portfolio.json`. Nothing touches a real brokerage.

```bash
stockbot trade --anytime            # preview a rebalance (add --execute to fill it in the sim)
stockbot autopilot --anytime        # runs forever: announce, 60s cancel window, trade
stockbot gui                        # same thing with buttons (Broker = sim is the default)
```

Drop `--anytime` to only trade during US market hours. Prices can be ~15 minutes delayed. Real-money trading needs a broker account; `--broker alpaca` supports an Alpaca paper account, and live use is gated behind `--live` plus `STOCKBOT_ALLOW_LIVE=yes`. Test in the sim for months first.

## Day trading (EXPERIMENTAL, simulation only)

```bash
stockbot daytrade-backtest          # opening-range breakout on ~60 days of 5-minute Yahoo data
stockbot daytrade                   # live SIM day trader (market hours; add --anytime to test off-hours)
stockbot daytrade --reset           # reset the day-trading sim portfolio
```

Long-only opening-range breakout: buy a close above the first-30-minute high and above VWAP (before 15:00), stop at the range low, 2R target, flat by 15:55. Hard limits: 0.5% risk per trade, 20% max position, 6 trades/day, -2% daily-loss halt, a 10-second cancel window before each entry. The live trader **refuses to run against any real broker**; it uses its own virtual portfolio (`~/.stockbot/sim_daytrade.json`).

**It does not work in the only test available.** On 2026-08-14 to 2026-11-06 (15 large caps, 372 trades, 5 bps costs): 39% win rate, profit factor 0.43, **-16.1% total vs -6.8% for equal-weight buy & hold**. Only 5 of 372 trades reached the target. Yahoo only serves about 60 days of 5-minute data, so this window can neither prove nor disprove an edge, but there is no evidence of one. In the US, real day trading in a margin account also requires $25,000+ (pattern day trader rule), and most retail day traders lose money.

## Safety layer (all strategies)

- **News/social veto:** Google News (no key) and X/Twitter (optional paid bearer token, `X_BEARER_TOKEN`) headlines are scored with a finance word list; stocks with clearly negative sentiment across 5+ items are skipped. Free feeds have no history, so **this cannot be backtested** and is a safety filter, not a predictor.
- Stop-loss at -12% from entry, daily-loss halt at -3%, 25% max position, cash buffer.
- Autopilot shows a pop-up/log message with every planned order and a cancel countdown (default 60s) before anything is sent.

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
| ensemble | 13.7% | 0.98 | -23.8% | 0.50 | 9.72 |

Since 2018 (out-of-sample slice) both strategies trail SPY on total return (momentum 11.0% vs 13.7% CAGR; ml 13.1% vs 13.7%), though with smaller drawdowns. The ensemble has the best risk-adjusted numbers (Sharpe 0.98, -23.8% drawdown) but earns less in total (beta 0.5, so it sits partly in cash). **Conclusion: no reliable edge over buy-and-hold SPY here.** Momentum's full-period lead is small and fades out of sample. The value is in lower drawdown and a framework to test your own ideas.

## Desktop installers

Pushing a tag like `v0.2.0` runs `.github/workflows/release.yml`, which builds a PyInstaller app on Windows, macOS and Linux and attaches it to a GitHub Release. These builds are untested until the first run; if one fails, `pip install -e .` and `stockbot-gui` always works.

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
