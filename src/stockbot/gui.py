"""Desktop app (Tkinter - ships with Python on Windows, macOS and Linux).

The app trades a local simulation (default) or an Alpaca PAPER account - never live money. Keys typed here live in memory for this session and
are never written to disk.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .service import STRATEGIES

MONO = ("Consolas" if os.name == "nt" else "Menlo", 10)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("StockBot - paper trading (stocks only)")
        self.geometry("980x700")
        self.q: queue.Queue = queue.Queue()
        self.autopilot = None
        self.v = {k: tk.StringVar(value=d) for k, d in {
            "strategy": "ensemble", "top": "10", "key": "", "secret": "", "xtoken": "",
            "countdown": "60", "poll": "15", "tickers": "", "broker": "sim"}.items()}
        self.news = tk.BooleanVar(value=True)
        self.anytime = tk.BooleanVar(value=False)
        self._build()
        self.after(150, self._pump)

    # ---------- layout ----------
    def _build(self):
        banner = ttk.Label(self, text="Simulated/paper trading only. Not financial advice. No strategy is guaranteed to beat the market.",
                           foreground="#8a1c1c", padding=6)
        banner.pack(fill="x")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.t_dash, self.t_sig, self.t_bt, self.t_auto, self.t_set = (ttk.Frame(nb) for _ in range(5))
        for f, name in ((self.t_dash, "Dashboard"), (self.t_sig, "Signals & News"), (self.t_bt, "Backtest"),
                        (self.t_auto, "Autopilot"), (self.t_set, "Settings")):
            nb.add(f, text=name)
        self._settings(); self._dashboard(); self._signals(); self._backtest(); self._autopilot()

    def _text(self, parent):
        fr = ttk.Frame(parent)
        t = tk.Text(fr, wrap="word", font=MONO, height=10)
        sb = ttk.Scrollbar(fr, command=t.yview)
        t.configure(yscrollcommand=sb.set, state="disabled")
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        fr.pack(fill="both", expand=True, padx=6, pady=6)
        return t

    def _put(self, widget, text, clear=False):
        widget.configure(state="normal")
        if clear:
            widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.see("end")
        widget.configure(state="disabled")

    def _settings(self):
        f = self.t_set
        rows = [("Broker (sim = local virtual money)", "broker", ["sim", "alpaca"]), ("Strategy", "strategy", STRATEGIES), ("Holdings (top N)", "top", None),
                ("Alpaca PAPER key id", "key", None), ("Alpaca PAPER secret", "secret", "*"),
                ("X/Twitter bearer token (optional)", "xtoken", "*"),
                ("Cancel window before trades (sec)", "countdown", None), ("Check every (min)", "poll", None),
                ("Tickers (blank = default large caps)", "tickers", None)]
        for i, (label, key, kind) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=5)
            if isinstance(kind, list):
                w = ttk.Combobox(f, textvariable=self.v[key], values=kind, state="readonly", width=40)
            else:
                w = ttk.Entry(f, textvariable=self.v[key], width=43, show=kind or "")
            w.grid(row=i, column=1, sticky="w", pady=5)
        ttk.Checkbutton(f, text="Use Google News / X sentiment veto", variable=self.news).grid(
            row=len(rows), column=1, sticky="w", pady=5)
        ttk.Checkbutton(f, text="Sim only: trade even when the market is closed", variable=self.anytime).grid(
            row=len(rows) + 2, column=1, sticky="w", pady=5)
        ttk.Label(f, wraplength=640, foreground="#555", text=(
            "Get free paper keys at alpaca.markets. X/Twitter search needs a paid developer bearer token; "
            "without it only Google News is used. Sentiment can't be backtested, so it is used only to "
            "skip stocks with clearly negative news, never to pick them.")).grid(
            row=len(rows) + 3, column=0, columnspan=2, sticky="w", padx=10, pady=10)

    def _dashboard(self):
        top = ttk.Frame(self.t_dash); top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Refresh account", command=self.refresh).pack(side="left")
        self.acct_lbl = ttk.Label(top, text="  not connected", font=("", 11, "bold")); self.acct_lbl.pack(side="left")
        cols = ("symbol", "qty", "avg entry", "price", "value", "P/L")
        self.tree = ttk.Treeview(self.t_dash, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree.heading(c, text=c); self.tree.column(c, width=120, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

    def _signals(self):
        top = ttk.Frame(self.t_sig); top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Compute today's picks + news", command=self.compute_signals).pack(side="left")
        self.sig_txt = self._text(self.t_sig)

    def _backtest(self):
        top = ttk.Frame(self.t_bt); top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Run backtest vs SPY", command=self.run_backtest).pack(side="left")
        ttk.Label(top, text="  (ml/ensemble take ~30-60s)").pack(side="left")
        self.bt_txt = self._text(self.t_bt)

    def _autopilot(self):
        top = ttk.Frame(self.t_auto); top.pack(fill="x", padx=6, pady=6)
        self.btn_start = ttk.Button(top, text="Start autopilot", command=self.start_autopilot)
        self.btn_stop = ttk.Button(top, text="Stop", command=self.stop_autopilot, state="disabled")
        self.btn_start.pack(side="left"); self.btn_stop.pack(side="left", padx=6)
        self.status = ttk.Label(top, text="Idle"); self.status.pack(side="left", padx=10)
        self.log_txt = self._text(self.t_auto)

    # ---------- background work (Tk is single-threaded; workers talk via the queue) ----------
    def bg(self, fn, done):
        def work():
            try:
                self.q.put(("call", done, fn()))
            except Exception as e:
                self.q.put(("call", lambda _r, e=e: messagebox.showerror("Error", f"{type(e).__name__}: {e}"), None))
        threading.Thread(target=work, daemon=True).start()

    def _pump(self):
        try:
            while True:
                kind, a, b = self.q.get_nowait()
                if kind == "call":
                    a(b)
                elif kind == "log":
                    self._put(self.log_txt, f"[{datetime.now():%H:%M:%S}] {a}\n")
                elif kind == "announce":
                    self._announce(a, b)
        except queue.Empty:
            pass
        self.after(150, self._pump)

    def _apply_env(self):
        os.environ["ALPACA_KEY_ID"] = self.v["key"].get().strip()
        os.environ["ALPACA_SECRET_KEY"] = self.v["secret"].get().strip()

    def _broker(self):
        if self.v["broker"].get() == "sim":
            from .sim import SimBroker

            return SimBroker(ignore_hours=self.anytime.get())
        from .broker import Alpaca

        self._apply_env()
        return Alpaca(live=False)

    # ---------- actions ----------
    def refresh(self):
        def fn():
            b = self._broker()
            return b.account(), b.positions()

        def done(r):
            acct, pos = r
            self.acct_lbl.config(text=f"  equity ${float(acct['equity']):,.2f}   cash ${float(acct['cash']):,.2f}")
            self.tree.delete(*self.tree.get_children())
            for p in pos:
                self.tree.insert("", "end", values=(p["symbol"], p["qty"], f"{float(p['avg_entry_price']):.2f}",
                                                   f"{float(p['current_price']):.2f}", f"{float(p['market_value']):,.2f}",
                                                   f"{float(p['unrealized_plpc']):+.1%}"))
        self.bg(fn, done)

    def compute_signals(self):
        self._put(self.sig_txt, "Working...\n", clear=True)

        def fn():
            from .risk import RiskConfig, apply_sentiment_overlay
            from .sentiment import scan
            from .service import load_universe, make_strategy

            stocks, bench = load_universe(self.v["tickers"].get() or None)
            w = make_strategy(self.v["strategy"].get(), int(self.v["top"].get()))(stocks, bench)
            w = w[w > 0].sort_values(ascending=False)
            sent, notes = {}, []
            if self.news.get() and not w.empty:
                sent = scan(list(w.index), self.v["xtoken"].get() or None)
                w, notes = apply_sentiment_overlay(w, sent, RiskConfig())
            out = [f"Target portfolio as of {stocks.index[-1].date()}  ({self.v['strategy'].get()})\n"]
            if w[w > 0].empty:
                out.append("  100% cash (risk-off regime or everything vetoed)\n")
            for sym, wt in w[w > 0].items():
                s = sent.get(sym)
                out.append(f"  {sym:<6}{wt:7.1%}" + (f"   news {s.score:+.2f} ({s.n} items)" if s else "") + "\n")
            out += [f"  ! {n}\n" for n in notes]
            for sym, s in sent.items():
                out.append(f"\n--- {sym} headlines ---\n")
                out += [f"  [{src}] {sc:+.1f} {txt[:110]}\n" for src, txt, sc in s.items[:4]]
                out += [f"  ({n})\n" for n in s.notes]
            return "".join(out)
        self.bg(fn, lambda t: self._put(self.sig_txt, t, clear=True))

    def run_backtest(self):
        self._put(self.bt_txt, "Running backtest...\n", clear=True)

        def fn():
            from .backtest import run_backtest
            from .metrics import compare, format_table
            from .service import load_universe, make_strategy

            stocks, bench = load_universe(self.v["tickers"].get() or None)
            r = run_backtest(stocks, bench, make_strategy(self.v["strategy"].get(), int(self.v["top"].get())))
            s, b = r.equity.iloc[-1], r.bench_equity.iloc[-1]
            return (format_table(compare(r.equity, r.bench_equity)) +
                    f"\n\n$1 grew to {s:.2f} (strategy) vs {b:.2f} (SPY): {'ahead' if s > b else 'BEHIND'}.\n"
                    "Universe is today's large caps (survivorship bias). Past results don't predict the future.\n")
        self.bg(fn, lambda t: self._put(self.bt_txt, t, clear=True))

    def start_autopilot(self):
        from .autopilot import AutoConfig, Autopilot

        try:
            broker = self._broker()
            cfg = AutoConfig(strategy=self.v["strategy"].get(), top=int(self.v["top"].get()),
                             tickers=self.v["tickers"].get() or None, x_token=self.v["xtoken"].get() or None,
                             use_sentiment=self.news.get(), countdown_s=int(self.v["countdown"].get()),
                             poll_minutes=int(self.v["poll"].get()))
        except Exception as e:
            messagebox.showerror("Cannot start", str(e))
            return
        self.autopilot = Autopilot(cfg, broker, log=lambda m: self.q.put(("log", m, None)),
                                   announce=lambda plan, s: self.q.put(("announce", plan, s)))
        self.autopilot.start()
        self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal")
        self.status.config(text="Running (paper)")

    def stop_autopilot(self):
        if self.autopilot:
            self.autopilot.stop()
        self.btn_start.config(state="normal"); self.btn_stop.config(state="disabled")
        self.status.config(text="Idle")

    def _announce(self, plan, secs):
        """Pop-up with a live countdown; closing or Cancel stops the trades."""
        self.bell()
        win = tk.Toplevel(self)
        win.title("StockBot is about to trade")
        win.attributes("-topmost", True)
        ttk.Label(win, text=plan.describe(), font=MONO, justify="left").pack(padx=14, pady=10)
        lbl = ttk.Label(win, font=("", 12, "bold")); lbl.pack(pady=4)
        state = {"left": secs}

        def cancel():
            if self.autopilot:
                self.autopilot.cancel_pending()
            win.destroy()

        def tick():
            if not win.winfo_exists():
                return
            lbl.config(text=f"Trading in {state['left']}s")
            if state["left"] <= 0:
                win.destroy()
                return
            state["left"] -= 1
            win.after(1000, tick)
        ttk.Button(win, text="CANCEL these trades", command=cancel).pack(pady=10)
        win.protocol("WM_DELETE_WINDOW", cancel)
        tick()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
