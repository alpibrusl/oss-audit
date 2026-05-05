"""Suggest audit candidates from external sources (HN, etc.).

For now: Hacker News front page + Show HN, filtering posts that link
to GitHub repos or gists. Returns URLs sorted by points.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

HN_API = "https://hacker-news.firebaseio.com/v0"

GH_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gist\.github\.com)/[\w./-]+",
    re.IGNORECASE,
)


@dataclass
class Candidate:
    url: str
    title: str
    points: int
    comments: int
    hn_id: int

    def to_dict(self) -> dict:
        return {
            "url": self.url, "title": self.title, "points": self.points,
            "comments": self.comments, "hn_url": f"https://news.ycombinator.com/item?id={self.hn_id}",
        }


def _extract_gh_url(item: dict) -> str | None:
    """Return the first GitHub/gist URL that appears in the post URL or text."""
    for field in ("url", "text"):
        v = item.get(field) or ""
        m = GH_URL_RE.search(v)
        if m:
            url = m.group(0).rstrip(".,;)\"'")
            # Filter URLs that don't point to a repo (e.g. github.com/sponsors/x)
            parts = url.replace("https://", "").replace("http://", "").split("/")
            if len(parts) >= 3 and parts[0] in ("github.com", "gist.github.com", "www.github.com"):
                return url
    return None


def fetch_hn_candidates(
    source: str = "topstories", limit: int = 30, scan: int = 60,
) -> list[Candidate]:
    """source: topstories | newstories | beststories | showstories.
    `scan` = how many items to inspect (HN returns up to 500 IDs per feed).
    """
    valid_sources = {"topstories", "newstories", "beststories", "showstories"}
    if source not in valid_sources:
        raise ValueError(f"source must be one of {valid_sources}")

    with httpx.Client(timeout=15.0) as client:
        try:
            r = client.get(f"{HN_API}/{source}.json")
            if r.status_code != 200:
                raise RuntimeError(
                    f"HN API status {r.status_code}: {r.text[:200]} "
                    f"(is egress to hacker-news.firebaseio.com blocked?)"
                )
            ids = r.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"HN API didn't respond: {e}")
        out: list[Candidate] = []
        for hn_id in ids[:scan]:
            try:
                item = client.get(f"{HN_API}/item/{hn_id}.json").json()
            except httpx.HTTPError:
                continue
            if not item or item.get("dead") or item.get("deleted"):
                continue
            url = _extract_gh_url(item)
            if not url:
                continue
            out.append(Candidate(
                url=url,
                title=item.get("title", "")[:200],
                points=int(item.get("score", 0)),
                comments=int(item.get("descendants", 0)),
                hn_id=hn_id,
            ))
            if len(out) >= limit:
                break
    out.sort(key=lambda c: -c.points)
    return out
