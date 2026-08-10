"""Polls both the Semantic Scholar and arXiv search endpoints until their
rate limits clear, then runs collect_candidates.py. Exists only to babysit
today's 429s (both APIs got hit during the same afternoon of eval runs) --
not part of the production pipeline."""

import subprocess
import sys
import time

import requests

MAX_WAIT_MINUTES = 30
POLL_INTERVAL_SECONDS = 60


def rate_limit_cleared() -> bool:
    s2 = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": "test", "limit": 1, "fields": "title"},
    )
    arxiv = requests.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": "test", "max_results": 1},
    )
    if s2.status_code != 200:
        print(f"  Semantic Scholar still at HTTP {s2.status_code}")
    if arxiv.status_code != 200:
        print(f"  arXiv still at HTTP {arxiv.status_code}")
    return s2.status_code == 200 and arxiv.status_code == 200


def main():
    waited = 0
    while waited < MAX_WAIT_MINUTES * 60:
        if rate_limit_cleared():
            print(f"[wait_and_collect] rate limit cleared after {waited}s, starting collection")
            subprocess.run([sys.executable, "eval/collect_candidates.py"], check=True)
            return
        print(f"[wait_and_collect] still rate limited at {waited}s, waiting {POLL_INTERVAL_SECONDS}s...")
        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
    print(f"[wait_and_collect] gave up after {MAX_WAIT_MINUTES} minutes, still rate limited")


if __name__ == "__main__":
    main()
