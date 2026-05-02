"""Sugerir candidatos para auditar desde fuentes externas (HN, etc).

Hoy: front page + Show HN de Hacker News, filtrando posts que linkean
a repos de GitHub o gists. Devuelve URLs ordenadas por puntos.
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
    """Devuelve la primera URL de GitHub/gist que aparezca en la URL del post o el texto."""
    for field in ("url", "text"):
        v = item.get(field) or ""
        m = GH_URL_RE.search(v)
        if m:
            url = m.group(0).rstrip(".,;)\"'")
            # Filtra URLs que no apunten a un repo (e.g. github.com/sponsors/x)
            parts = url.replace("https://", "").replace("http://", "").split("/")
            if len(parts) >= 3 and parts[0] in ("github.com", "gist.github.com", "www.github.com"):
                return url
    return None


def fetch_hn_candidates(
    source: str = "topstories", limit: int = 30, scan: int = 60,
) -> list[Candidate]:
    """source: topstories | newstories | beststories | showstories.
    `scan` = cuántos items inspeccionar (HN devuelve hasta 500 IDs por feed).
    """
    valid_sources = {"topstories", "newstories", "beststories", "showstories"}
    if source not in valid_sources:
        raise ValueError(f"source debe ser uno de {valid_sources}")

    with httpx.Client(timeout=15.0) as client:
        try:
            r = client.get(f"{HN_API}/{source}.json")
            if r.status_code != 200:
                raise RuntimeError(
                    f"HN API status {r.status_code}: {r.text[:200]} "
                    f"(¿egress a hacker-news.firebaseio.com bloqueado?)"
                )
            ids = r.json()
        except httpx.HTTPError as e:
            raise RuntimeError(f"HN API no respondió: {e}")
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
