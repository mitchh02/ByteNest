"""
Tests for app/graph.py.

Run from the backend folder:
    pip install pytest
    python -m pytest -v

The first group builds tiny graphs by hand, so it needs no database.
The last test uses your real database and is skipped if it can't connect.
"""
import math
import random
from unittest.mock import Mock

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


def test_bidirectional_keeps_searching_after_first_meeting():
    G = make_graph([(1, 4, .1), (1, 2, .9), (2, 3, .9), (3, 4, .9)])
    assert graph.bidirectional_dijkstra(G, 1, 4) == [1, 2, 3, 4]


def test_bidirectional_caps_final_path_and_keeps_shorter_alternatives():
    G = make_graph([(i, i + 1, .95) for i in range(7)] + [(0, 8, .3), (8, 7, .3)])
    assert graph.bidirectional_dijkstra(G, 0, 7, 6) == [0, 8, 7]
    assert graph.bidirectional_dijkstra(G, 0, 7, 7) == list(range(8))
    assert graph.bidirectional_dijkstra(G, 0, 6, 6) == list(range(7))
    assert graph.bidirectional_dijkstra(G, 0, 7, 1) is None


def test_bidirectional_missing_isolated_and_same_person():
    G = make_graph([(1, 2, .9)])
    G.add_node(3)
    assert graph.bidirectional_dijkstra(G, 1, 3) is None
    assert graph.bidirectional_dijkstra(G, 1, 99) is None
    assert graph.bidirectional_dijkstra(G, 3, 3, 0) == [3]
    assert graph.bidirectional_dijkstra(G, 1, 2, 0) is None
    with pytest.raises(ValueError):
        graph.bidirectional_dijkstra(G, 1, 2, -1)


@pytest.mark.parametrize('directed', [False, True])
def test_bidirectional_matches_exhaustive_simple_paths(directed):
    rng = random.Random(42)
    for _ in range(10):
        G = nx.gnp_random_graph(7, .35, seed=rng, directed=directed)
        for a, b in G.edges:
            strength = rng.choice([1.0, .95, .6, .1])
            G[a][b].update(strength=strength, cost=-math.log(strength))
        for hops in range(1, 7):
            for target in range(1, 7):
                candidates = list(nx.all_simple_paths(G, 0, target, cutoff=hops))
                path = graph.bidirectional_dijkstra(G, 0, target, hops)
                if not candidates:
                    assert path is None
                    continue
                assert path[0] == 0 and path[-1] == target
                assert len(path) - 1 <= hops
                assert len(path) == len(set(path))
                assert graph.path_score(G, path) == pytest.approx(
                    max(graph.path_score(G, p) for p in candidates))


def test_single_target_best_paths_uses_bidirectional(monkeypatch):
    G = make_graph([(1, 2, .9), (2, 3, .8)])
    monkeypatch.setattr(graph, 'load_neighborhood', lambda *_: G)
    monkeypatch.setattr(graph, 'get_people', lambda ids: {i: {'id': i} for i in ids})
    pair_search = Mock(wraps=graph.bidirectional_dijkstra)
    monkeypatch.setattr(graph, 'bidirectional_dijkstra', pair_search)
    result = graph.best_paths(1, [1, 3, 3])
    pair_search.assert_called_once_with(G, 1, 3, graph.MAX_HOPS)
    assert result[0]['path'] == [1, 2, 3]
    assert result[0]['score'] == pytest.approx(.72)
    assert result[0]['reasons'] == ['1-2', '2-3']


def test_multi_target_best_paths_shares_one_search(monkeypatch):
    G = make_graph([(1, 2, .9), (2, 3, .8)])
    monkeypatch.setattr(graph, 'load_neighborhood', lambda *_: G)
    monkeypatch.setattr(graph, 'get_people', lambda ids: {i: {'id': i} for i in ids})
    pair_search = Mock()
    monkeypatch.setattr(graph, 'bidirectional_dijkstra', pair_search)
    assert graph.best_paths(1, [2, 3], limit=1)[0]['target_id'] == 2
    pair_search.assert_not_called()


def test_overlapping_loaded_neighborhoods_keep_six_hop_detour(monkeypatch):
    # The weak shortcut makes node 2 part of the seeker's loaded neighborhood.
    # The target's rings must still traverse it to fetch edge 3--6.
    G = make_graph([(0, 1, .1), (1, 2, .1), (2, 3, .9), (2, 7, .9),
                    (0, 4, .9), (4, 5, .9), (5, 6, .9), (6, 3, .9)])
    queried = set()
    def edges_touching(ids):
        assert not queried.intersection(ids)
        queried.update(ids)
        return [{'user_a_id': a, 'user_b_id': b, 'strength': data['strength'], 'context': ''}
                for a, b, data in G.edges(data=True) if a in ids or b in ids]
    monkeypatch.setattr(graph, '_edges_touching', edges_touching)
    loaded = graph.load_neighborhood(0, [7])
    assert graph.bidirectional_dijkstra(loaded, 0, 7) == [0, 4, 5, 6, 3, 2, 7]


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
