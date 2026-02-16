# graph/router/heuristics.py

from .constants import ROUTE_HINTS, HEURISTIC_MIN_SCORE

def heuristic_route(text: str) -> str | None:
    scores = {}

    for route, keywords in ROUTE_HINTS.items():
        scores[route] = sum(1 for k in keywords if k in text)

    best_route, best_score = max(scores.items(), key=lambda x: x[1])

    if best_score < HEURISTIC_MIN_SCORE:
        return None

    return best_route
