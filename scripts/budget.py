#!/usr/bin/env python3
"""Token-budget calculator for Claude Code sessions.

Model (per turn i = 1..n, the whole context is re-read every turn):
    C_i = C0 + g*i                      context size at turn i
    uncached total   T  = n*C0 + g*n(n+1)/2          (quadratic in n)
    cost units (cache read = r, cache write = w, defaults r=0.1, w=1.25):
        cost(n) = r*(n*C0 + g*n(n-1)/2) + w*(C0 + g*n)

Reset (/clear) trade-off: restarting costs R tokens to reload (CLAUDE.md, files).
Average cost per turn over a segment of m turns:
        A(m) = w*R/m + r*(C0 + g*(m+1)/2)
        dA/dm = -w*R/m^2 + r*g/2 = 0   =>   m* = sqrt(2*w*R / (r*g))
Reset every ~m* turns to minimise cost per turn.
"""
import argparse
import math


def total_tokens(n, c0, g):
    return n * c0 + g * n * (n + 1) / 2


def cost_units(n, c0, g, r=0.1, w=1.25):
    return r * (n * c0 + g * n * (n - 1) / 2) + w * (c0 + g * n)


def optimal_reset(R, g, r=0.1, w=1.25):
    return math.sqrt(2 * w * R / (r * g))


def avg_cost(m, R, c0, g, r=0.1, w=1.25):
    return w * R / m + r * (c0 + g * (m + 1) / 2)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--c0", type=float, default=8000, help="baseline context tokens (CLAUDE.md, tools, system)")
    p.add_argument("--g", type=float, default=3000, help="context growth per turn (tokens)")
    p.add_argument("--n", type=int, default=40, help="turns in the session")
    p.add_argument("--R", type=float, default=15000, help="tokens to rebuild context after /clear")
    p.add_argument("--limit", type=float, default=None, help="your usage budget in cost units; prints max turns")
    a = p.parse_args()

    print(f"turns n={a.n}  C0={a.c0:.0f}  g={a.g:.0f}")
    print(f"uncached tokens read : {total_tokens(a.n, a.c0, a.g):,.0f}")
    print(f"cost units (cached)  : {cost_units(a.n, a.c0, a.g):,.0f}")
    m = optimal_reset(a.R, a.g)
    print(f"optimal reset every  : m* = sqrt(2wR/(rg)) = {m:.1f} turns")
    print(f"avg cost/turn at m*  : {avg_cost(m, a.R, a.c0, a.g):,.0f}  vs  no-reset at n={a.n}: {cost_units(a.n, a.c0, a.g)/a.n:,.0f}")
    if a.limit:
        # solve cost(n) <= limit for largest n (monotone increasing)
        lo, hi = 1, 100000
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if cost_units(mid, a.c0, a.g) <= a.limit:
                lo = mid
            else:
                hi = mid - 1
        print(f"max turns in one unbroken session within limit: {lo}")


if __name__ == "__main__":
    main()
