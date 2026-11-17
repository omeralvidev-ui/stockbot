#!/usr/bin/env python3
"""Token-budget calculator for Claude Code sessions.

Model (turn i = 1..n; the whole context is re-read each turn):
    C_i = C0 + g*i                              context size at turn i
    uncached tokens     T(n) = n*C0 + g*n(n+1)/2            (quadratic in n)

Cache pricing: read = r (default 0.1), write = w (default 1.25).
Caches expire when you pause; let p = fraction of turns that come after an
expiry (they re-write the context instead of reading it). Effective rate:
    rho = p*w + (1-p)*r
    cost(n) = rho*(n*C0 + g*n(n-1)/2) + w*(C0 + g*n)

Reset (/clear) costs R tokens to rebuild context. Average cost per turn over a
segment of m turns:
    A(m)  = w*R/m + rho*(C0 + g*(m+1)/2)
    A'(m) = 0  =>  m* = sqrt(2*w*R / (rho*g))
"""
import argparse
import math

R_READ, W_WRITE = 0.1, 1.25


def rho(p, r=R_READ, w=W_WRITE):
    return p * w + (1 - p) * r


def total_tokens(n, c0, g):
    return n * c0 + g * n * (n + 1) / 2


def cost_units(n, c0, g, p=0.0, r=R_READ, w=W_WRITE):
    return rho(p, r, w) * (n * c0 + g * n * (n - 1) / 2) + w * (c0 + g * n)


def optimal_reset(R, g, p=0.0, r=R_READ, w=W_WRITE):
    return math.sqrt(2 * w * R / (rho(p, r, w) * g))


def avg_cost(m, R, c0, g, p=0.0, r=R_READ, w=W_WRITE):
    return w * R / m + rho(p, r, w) * (c0 + g * (m + 1) / 2)


def max_turns(limit, c0, g, p=0.0):
    lo, hi = 0, 1_000_000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if cost_units(mid, c0, g, p) <= limit:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--c0", type=float, default=8000, help="baseline context tokens")
    ap.add_argument("--g", type=float, default=3000, help="context growth per turn")
    ap.add_argument("--n", type=int, default=40, help="turns in the session")
    ap.add_argument("--R", type=float, default=15000, help="tokens to rebuild after /clear")
    ap.add_argument("--p", type=float, default=0.1, help="fraction of turns after a cache expiry (0..1)")
    ap.add_argument("--limit", type=float, help="usage budget in cost units")
    a = ap.parse_args()
    if not 0 <= a.p <= 1 or min(a.c0, a.g, a.R) <= 0 or a.n < 1:
        ap.error("need 0<=p<=1, c0,g,R>0, n>=1")

    m = optimal_reset(a.R, a.g, a.p)
    base = cost_units(a.n, a.c0, a.g, a.p) / a.n
    best = avg_cost(m, a.R, a.c0, a.g, a.p)
    print(f"n={a.n} C0={a.c0:.0f} g={a.g:.0f} R={a.R:.0f} p={a.p}")
    print(f"uncached tokens read     : {total_tokens(a.n, a.c0, a.g):,.0f}")
    print(f"cost units (n turns)     : {cost_units(a.n, a.c0, a.g, a.p):,.0f}")
    print(f"optimal reset m*         : {m:.1f} turns")
    print(f"avg cost/turn, no reset  : {base:,.0f}")
    print(f"avg cost/turn at m*      : {best:,.0f}  ({(1 - best / base) * 100:.0f}% lower)" if best < base else
          f"avg cost/turn at m*      : {best:,.0f}  (session already shorter than m*; don't reset)")
    if a.limit:
        print(f"max turns within limit   : {max_turns(a.limit, a.c0, a.g, a.p)} (unbroken session)")


if __name__ == "__main__":
    main()
