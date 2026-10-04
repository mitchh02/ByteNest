"""
Tests for app/graph.py.

Run from the backend folder:
    pip install pytest
    python -m pytest -v

The first group builds tiny graphs by hand, so it needs no database.
The last test uses your real database and is skipped if it can't connect.
"""
import math

import networkx as nx
import pytest

from app import graph


def make_graph(edges):
    """Build a graph from (person_a, person_b, strength) tuples, the same way graph.py does."""
    G = nx.Graph()
    for a, b, s in edges:
        G.add_edge(a, b, strength=s, cost=-math.log(s), context=f"{a}-{b}")
    return G


# ---------------------------------------------------------------------------
# Path scoring
# ---------------------------------------------------------------------------

def test_path_score_multiplies_strengths():
    G = make_graph([(1, 2, 0.5), (2, 3, 0.8)])
    assert graph.path_score(G, [1, 2, 3]) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------

def test_strong_longer_path_beats_weak_shortcut():
    # 1 -> 4 directly is weak (0.1); 1 -> 2 -> 3 -> 4 is strong (0.9^3 = 0.729)
    G = make_graph([(1, 4, 0.1), (1, 2, 0.9), (2, 3, 0.9), (3, 4, 0.9)])
    paths = graph.hop_limited_dijkstra(G, 1, max_hops=6)
    assert paths[4] == [1, 2, 3, 4]


def test_hop_limit_falls_back_to_shorter_path():
    # Strongest route to 5 is 4 hops, but with a 2-hop limit it must use the weaker 2-hop route.
    # (Plain Dijkstra would return the 4-hop route and lose this one.)
    G = make_graph([
        (1, 2, 0.95), (2, 3, 0.95), (3, 4, 0.95), (4, 5, 0.95),   # strong, 4 hops
        (1, 6, 0.3), (6, 5, 0.3),                                  # weak, 2 hops
    ])
    assert graph.hop_limited_dijkstra(G, 1, max_hops=6)[5] == [1, 2, 3, 4, 5]
    assert graph.hop_limited_dijkstra(G, 1, max_hops=2)[5] == [1, 6, 5]


def test_unreachable_within_limit_is_missing():
    # A chain of 8 people: person 8 is 7 hops from person 1
    G = make_graph([(i, i + 1, 0.9) for i in range(1, 8)])
    paths = graph.hop_limited_dijkstra(G, 1, max_hops=6)
    assert 7 in paths
    assert 8 not in paths


def test_no_path_ever_exceeds_the_limit():
    G = nx.connected_watts_strogatz_graph(200, k=4, p=0.05, seed=1)
    for a, b in G.edges:
        s = 0.1 + 0.9 * ((a * 7 + b * 13) % 10) / 10   # varied but repeatable strengths
        G[a][b].update(strength=s, cost=-math.log(s))
    for path in graph.hop_limited_dijkstra(G, 0, max_hops=6).values():
        assert len(path) - 1 <= 6


def test_matches_brute_force_on_random_graph():
    """Compare against an independent exact method: Bellman-Ford limited to 6 rounds."""
    G = nx.connected_watts_strogatz_graph(300, k=4, p=0.05, seed=2)
    for a, b in G.edges:
        s = 0.05 + 0.95 * ((a * 31 + b * 17) % 97) / 97
        G[a][b].update(strength=s, cost=-math.log(s))

    best = {0: 0.0}
    frontier = {0: 0.0}
    for _ in range(6):
        nxt = {}
        for u, cu in frontier.items():
            for v, d in G[u].items():
                c = cu + d["cost"]
                if c < best.get(v, math.inf) - 1e-12 and c < nxt.get(v, math.inf):
                    nxt[v] = c
        best.update(nxt)
        frontier = nxt

    paths = graph.hop_limited_dijkstra(G, 0, max_hops=6)
    assert set(paths) == set(best)
    for person, path in paths.items():
        assert graph.path_score(G, path) == pytest.approx(math.exp(-best[person]))


def test_early_stop_returns_the_strongest_targets():
    G = make_graph([
        (1, 2, 0.9), (1, 3, 0.5), (1, 4, 0.2), (2, 5, 0.9), (3, 6, 0.9),
    ])
    targets = [3, 4, 5, 6]
    full = graph.hop_limited_dijkstra(G, 1, max_hops=6)
    stopped = graph.hop_limited_dijkstra(G, 1, max_hops=6, targets=targets, limit=2)

    found = [t for t in targets if t in stopped]
    assert len(found) == 2
    # The two found must be the two strongest, with the same paths as a full search
    strongest_two = sorted(targets, key=lambda t: graph.path_score(G, full[t]), reverse=True)[:2]
    assert set(found) == set(strongest_two)
    for t in found:
        assert stopped[t] == full[t]


def test_seeker_is_not_their_own_target():
    G = make_graph([(1, 2, 0.9)])
    stopped = graph.hop_limited_dijkstra(G, 1, max_hops=6, targets=[1, 2], limit=1)
    assert 2 in stopped   # the search didn't stop early just because it started on 1


# ---------------------------------------------------------------------------
# End to end against the real database
# ---------------------------------------------------------------------------

def test_best_paths_with_real_database():
    from app import db
    try:
        seeker = db.query("SELECT MIN(id) AS id FROM users")[0]["id"]
        hiring = [r["posted_by"] for r in db.query("SELECT DISTINCT posted_by FROM job_openings")]
    except Exception as exc:
        pytest.skip(f"database not available: {exc}")
    if seeker is None or not hiring:
        pytest.skip("database has no users or job openings; run the populate script first")

    results = graph.best_paths(seeker, hiring, limit=3)

    assert len(results) <= 3
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)       # best first
    for r in results:
        assert r["path"][0] == seeker                   # starts at the seeker
        assert r["path"][-1] == r["target_id"]          # ends at a hiring manager
        assert r["target_id"] in hiring
        assert 1 <= r["hops"] <= graph.MAX_HOPS
        assert 0 < r["score"] <= 1
        assert len(r["reasons"]) == r["hops"]           # one reason per connection
        assert [p["id"] for p in r["people"]] == r["path"]  # names line up with the path