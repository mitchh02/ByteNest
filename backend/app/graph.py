"""
Path finding for Six Degrees Hiring.

Given a job seeker and a list of hiring managers, find the strongest chain of
real relationships from the seeker to each manager, using at most MAX_HOPS
introductions.

How it works, in three stages:
  1. load_neighborhood    - pull only the nearby part of the network from the database
  2. hop_limited_dijkstra - search it for the strongest path to everyone within 6 hops
  3. best_paths           - rank the hiring managers by path strength and add their names

"Strength" is a number from 0 to 1 on each connection (1 = very close). A path's
score is all its strengths multiplied together, roughly "the chance every person
along the chain passes the intro on."
"""
import heapq   # priority queue: always hands back the cheapest route found so far
import math

import networkx as nx  # graph data structure (people = nodes, connections = edges)

from . import db

MAX_HOPS = 6        # the "six degrees" limit: longest chain of introductions we'll suggest
BATCH_SIZE = 1000   # max ids per SQL "IN (...)" list, so queries stay a reasonable size

def _get_data_from_web():
  pass

def _edges_touching(user_ids):
    """Fetch every connection where at least one of the two people is in user_ids."""
    import random # simulating cache misses
    
    CACHE_MISS_PROB = 0.05
  
    ids = list(user_ids)
    rows = []

    # Split the ids into chunks so one huge query doesn't hit database limits
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]

        # Build "%s,%s,%s,..." placeholders, one per id. The values are passed
        # separately (not pasted into the SQL), which prevents SQL injection.
        marks = ",".join(["%s"] * len(batch))

        # Each connection is stored once per pair (smaller id in user_a_id), so a
        # person can appear in either column. Check both. The batch is passed twice
        # because there are two IN (...) lists.
        rows += db.query(
            f"""SELECT user_a_id, user_b_id, strength, context FROM user_connections
                WHERE user_a_id IN ({marks}) OR user_b_id IN ({marks})""",
            batch + batch,
        )
      
        if random.random() < CACHE_MISS_PROB:
          _get_data_from_web()
          
    return rows


def load_neighborhood(seeker_id, target_ids):
    """
    Load only the part of the network a path of MAX_HOPS or fewer could use.

    Any path of at most 6 hops has every connection within 2 steps of the seeker
    or within 2 steps of a target, so we expand 3 rounds from each side and the
    two areas meet in the middle. The rest of the network is never loaded.
    """
    G = nx.Graph()                    # undirected: if A knows B, then B knows A
    rounds = math.ceil(MAX_HOPS / 2)  # 6 hops -> expand 3 rounds from each side
    expanded = set()                  # people whose connections we've already loaded

    # Expand twice: first outward from the seeker, then outward from all the
    # hiring managers at once.
    for start in ({seeker_id}, set(target_ids)):
        frontier = set(start)  # people at the current distance, waiting to be expanded
        seen = set(start)      # everyone reached so far from this side

        for _ in range(rounds):
            # Skip anyone already expanded (for example, reached from the other side)
            to_query = frontier - expanded
            if not to_query:
                break  # nothing new to explore

            next_frontier = set()
            for c in _edges_touching(to_query):
                a, b, s = c["user_a_id"], c["user_b_id"], float(c["strength"])

                # Add the connection to the graph. "cost" is what Dijkstra minimizes:
                # -log(strength) turns "multiply strengths, want the biggest" into
                # "add costs, want the smallest". Strong ties (near 1) cost almost 0,
                # weak ties (near 0) cost a lot. Adding the same edge twice is harmless.
                G.add_edge(a, b, strength=s, cost=-math.log(s), context=c["context"])

                # Anyone we haven't seen becomes part of the next ring outward
                for person in (a, b):
                    if person not in seen:
                        seen.add(person)
                        next_frontier.add(person)

            expanded |= to_query     # remember we've loaded these people's connections
            frontier = next_frontier # move one step further out
    return G


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def path_score(G, path):
    """Multiply the strengths along a path: 0 to 1, higher means more likely to get through."""
    # zip(path, path[1:]) pairs each person with the next: [A,B,C] -> (A,B), (B,C)
    return math.prod(G[a][b]["strength"] for a, b in zip(path, path[1:]))


def get_people(user_ids):
    """Look up names and job titles, but only for the people we're going to show."""
    if not user_ids:
        return {}
    marks = ",".join(["%s"] * len(user_ids))
    rows = db.query(
        f"SELECT id, first_name, last_name, job_title, company FROM users WHERE id IN ({marks})",
        list(user_ids),
    )
    # Turn the list of rows into {id: row} so we can look people up by id
    return {r["id"]: r for r in rows}


def hop_limited_dijkstra(G, source, max_hops, targets=None, limit=None):
    """
    Dijkstra (written in the uniform cost search style) that tracks hop count, so
    it finds the strongest path using at most max_hops connections. Plain Dijkstra
    ignores length: its best path may be 12 hops long, and throwing that away
    loses a good 5-hop path that also exists.

    Early stop: if targets and limit are given, the search ends as soon as it has
    found `limit` of the targets. Routes come off the queue cheapest first, so the
    first targets found are guaranteed to be the strongest ones.

    Returns {person: path} for everyone reached before the search ended.
    """
    # The priority queue holds routes still to explore. heapq always pops the one
    # with the lowest cost first, which is what makes this Dijkstra.
    heap = [(0.0, 0, source, [source])]   # (total cost, hops, person, path)
    fewest_hops = {}                      # person -> fewest hops we've reached them with
    best = {}                             # person -> strongest path found to them

    # For the early stop: which people we're looking for, and how many we've found.
    # The seeker can't be their own target, so leave them out.
    wanted = set(targets) - {source} if targets is not None else None
    found = 0

    while heap:
        # Take the cheapest (strongest) route found so far
        cost, hops, person, path = heapq.heappop(heap)

        # Routes come out cheapest first, so any earlier visit to this person was
        # cheaper. If that visit also used no more hops, this route is worse in
        # every way: skip it. If this route uses FEWER hops, keep going, because it
        # leaves more hops to reach people further away.
        if person in fewest_hops and hops >= fewest_hops[person]:
            continue
        fewest_hops[person] = hops

        # The first time a person comes off the queue is their cheapest route
        # within the hop limit. Record it only that first time.
        if person not in best:
            best[person] = path

            # Early stop: is this one of the people we're looking for?
            if wanted is not None and person in wanted:
                found += 1
                if limit is not None and found >= limit:
                    break   # we have the top `limit` targets; nothing left can beat them
                if found == len(wanted):
                    break   # every target found; no reason to keep searching

        # Out of hops: this route can't be extended any further
        if hops == max_hops:
            continue

        # Try extending the route to each of this person's connections
        for neighbor, edge in G[person].items():
            # Same "worse in every way" check as above, done early to keep the queue small
            if neighbor in fewest_hops and hops + 1 >= fewest_hops[neighbor]:
                continue
            heapq.heappush(heap, (cost + edge["cost"], hops + 1, neighbor, path + [neighbor]))

    return best


def best_paths(seeker_id, target_ids, limit=3):
    """Find the strongest path (within MAX_HOPS) from the seeker to each target, best first."""
    # Stage 1: load only the nearby part of the network
    G = load_neighborhood(seeker_id, target_ids)
    if seeker_id not in G:
        return []  # the seeker has no connections at all

    # Stage 2: search outward from the seeker, stopping once the `limit` strongest
    # hiring managers have been found
    paths = hop_limited_dijkstra(G, seeker_id, MAX_HOPS, targets=target_ids, limit=limit)

    # Build a result for each hiring manager we can reach
    results = []
    for target in target_ids:
        path = paths.get(target)
        if path is None or target == seeker_id:
            continue  # not reachable within 6 hops, or it's the seeker themselves
        results.append({
            "target_id": target,
            "path": path,                                   # list of user ids, seeker first
            "hops": len(path) - 1,                          # 3 people = 2 introductions
            "score": round(path_score(G, path), 3),         # 0 to 1, higher is better
            "reasons": [G[a][b]["context"] for a, b in zip(path, path[1:])],  # why each pair knows each other
        })

    # Strongest paths first, and keep only the top few. The early stop means we
    # usually have exactly `limit` already, but sorting keeps the order guaranteed.
    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:limit]

    # Stage 3: names and titles, only for people on the winning paths
    people = get_people({n for r in results for n in r["path"]})
    for r in results:
        r["people"] = [people[n] for n in r["path"]]  # same order as "path"
    return results
