import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import budget as b


def test_total_tokens_matches_brute_force():
    for n in (1, 5, 40):
        assert b.total_tokens(n, 8000, 3000) == sum(8000 + 3000 * i for i in range(1, n + 1))


def test_cost_matches_brute_force():
    n, c0, g, p = 30, 8000, 3000, 0.2
    brute = sum(b.rho(p) * (c0 + g * (i - 1)) for i in range(1, n + 1)) + b.W_WRITE * (c0 + g * n)
    assert math.isclose(b.cost_units(n, c0, g, p), brute, rel_tol=1e-12)


def test_optimum_minimises_average_cost():
    R, c0, g, p = 15000, 8000, 3000, 0.1
    m = b.optimal_reset(R, g, p)
    assert b.avg_cost(m, R, c0, g, p) <= b.avg_cost(m * 0.7, R, c0, g, p)
    assert b.avg_cost(m, R, c0, g, p) <= b.avg_cost(m * 1.4, R, c0, g, p)


def test_more_cache_misses_means_earlier_reset():
    assert b.optimal_reset(15000, 3000, 0.5) < b.optimal_reset(15000, 3000, 0.0)


def test_max_turns_monotone():
    assert b.max_turns(2e6, 8000, 3000, 0.1) > b.max_turns(1e6, 8000, 3000, 0.1)
