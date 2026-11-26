"""News fetcher: RSS/Atom with conditional GET, polite polling, fail-soft.

SOURCING (addendum C/B rules):
* Feed registry with reliability tiers; every feed is verified by
  ``scripts/verify_sources.py`` on a networked machine. In the build sandbox
  all feeds are unreachable → status stays "unverified" honestly.
* Politeness: ETag / If-Modified-Since, minimum poll interval
  (``news_poll_seconds``, default 900 s), exponential backoff on failure,
  never hammer a source. Fail-soft: a dead feed yields zero items and a
  warning — never fabricated news.
* We store title/source/url/published+fetch time/language/snippet only and
  link back to the original — no full-text copies where disallowed.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.services.news.dedup import cluster_docs
from app.services.news.normalize import detect_language, normalize_fa
from app.services.news.sentiment import score_sentiment
from app.services.news.topics import tag_topics

log = logging.getLogger(__name__)

USER_AGENT = "AWAGO/2.0 (news aggregator; contact in README; respects robots/ToS)"


@dataclass(frozen=True)
class FeedSpec:
    id: str
    url: str
    language: str
    tier: str  # "official" | "wire" | "mainstream" | "aggregator" | "unrated"
    name: str = ""
    notes: str = ""
    verified_live: bool = False


# Candidate feed registry — official/international first. Verification status
# is recorded by scripts/verify_sources.py; nothing here is claimed working
# from the build sandbox. Persian feeds: add reputable economics desks only;
# no sources that forbid aggregation.
FEEDS: list[FeedSpec] = [
    FeedSpec(
        "fed_press",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "en",
        "official",
        "Federal Reserve press",
    ),
    FeedSpec(
        "ecb_press", "https://www.ecb.europa.eu/rss/press.html", "en", "official", "ECB press"
    ),
    FeedSpec(
        "bls_release",
        "https://www.bls.gov/feed/news_release.rss",
        "en",
        "official",
        "US BLS releases",
    ),
    FeedSpec(
        "goldman_rss", "https://www.imf.org/en/News/RSS?Language=eng", "en", "official", "IMF news"
    ),
    FeedSpec(
        "gdeleth",
        "https://api.gdeltproject.org/api/v2/doc/doc?query=(gold%20OR%20dollar%20OR%20sanctions)"
        "&mode=artlist&maxrecords=20&format=rss",
        "en",
        "aggregator",
        "GDELT doc API (aggregator)",
        notes="voluntary API — query volume limits apply; use sparingly",
    ),
]


@dataclass
class FetchOutcome:
    feed_id: str
    ok: bool
    items: list[dict] = field(default_factory=list)
    error: str = ""
    not_modified: bool = False
    fetched_at: str = ""


@dataclass
class _CacheEntry:
    etag: str = ""
    last_modified: str = ""
    last_poll: float = 0.0
    backoff_until: float = 0.0
    failures: int = 0


class NewsFetcher:
    """Stateful fetcher (per-feed conditional GET + backoff)."""

    def __init__(self, min_poll_seconds: int = 900) -> None:
        self.min_poll = min_poll_seconds
        self._cache: dict[str, _CacheEntry] = {}

    def _polite_ok(self, feed_id: str) -> bool:
        ent = self._cache.setdefault(feed_id, _CacheEntry())
        now = time.monotonic()
        return now >= ent.backoff_until and (now - ent.last_poll) >= self.min_poll

    def fetch_feed(self, client: httpx.Client, feed: FeedSpec) -> FetchOutcome:
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self._polite_ok(feed.id):
            return FetchOutcome(feed.id, ok=False, error="poll interval/backoff not elapsed")
        ent = self._cache[feed.id]
        ent.last_poll = time.monotonic()
        headers = {"User-Agent": USER_AGENT}
        if ent.etag:
            headers["If-None-Match"] = ent.etag
        if ent.last_modified:
            headers["If-Modified-Since"] = ent.last_modified
        try:
            r = client.get(feed.url, headers=headers, timeout=25)
            if r.status_code == 304:
                return FetchOutcome(feed.id, ok=True, not_modified=True, fetched_at=now_iso)
            r.raise_for_status()
            ent.etag = r.headers.get("ETag", "")
            ent.last_modified = r.headers.get("Last-Modified", "")
            ent.failures = 0
            ent.backoff_until = 0.0
            items = self._parse_feed(r.text, feed)
            return FetchOutcome(feed.id, ok=True, items=items, fetched_at=now_iso)
        except Exception as exc:
            ent.failures += 1
            ent.backoff_until = time.monotonic() + min(3600.0, 60.0 * (2**ent.failures))
            log.warning("news feed %s failed: %s", feed.id, exc)
            return FetchOutcome(feed.id, ok=False, error=str(exc)[:200], fetched_at=now_iso)

    # ----------------------------------------------------------- parsing ----
    def _parse_feed(self, xml_text: str, feed: FeedSpec) -> list[dict]:
        out: list[dict] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []  # malformed XML -> zero items (tested via failure injection)
        for node in root.iter():
            tag = node.tag.lower().split("}")[-1]
            if tag not in ("item", "entry"):
                continue
            title = _child_text(node, "title")
            link = _child_text(node, "link") or _attr(node, "link", "href")
            pub = (
                _child_text(node, "pubDate")
                or _child_text(node, "published")
                or _child_text(node, "updated")
            )
            snippet = normalize_fa(
                _child_text(node, "description") or _child_text(node, "summary")
            )[:300]
            if not title:
                continue
            published = _parse_date(pub)
            fetched = datetime.now(timezone.utc)
            available = max(published, fetched) if published else fetched  # point-in-time
            out.append(
                {
                    "source": feed.id,
                    "tier": feed.tier,
                    "url": link or "",
                    "title": title,
                    "snippet": snippet,
                    "published_at": published.isoformat() if published else None,
                    "fetched_at": fetched.isoformat(),
                    "available_at": available.isoformat(),
                    "language": detect_language(title + " " + snippet)
                    if feed.language == "auto"
                    else feed.language,
                    "topics": tag_topics(title, snippet),
                    "sentiment": score_sentiment(title + " " + snippet).score,
                }
            )
        return out


def _child_text(node: ET.Element, name: str) -> str:
    for c in node:
        if c.tag.lower().split("}")[-1] == name and c.text:
            return c.text.strip()
    return ""


def _attr(node: ET.Element, name: str, attr: str) -> str:
    for c in node:
        if c.tag.lower().split("}")[-1] == name:
            return c.attrib.get(attr, "")
    return ""


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def cluster_items(items: list[dict]) -> list[dict]:
    """Assign cluster/thread ids to fetched items (deterministic)."""
    if not items:
        return items
    cids = cluster_docs([it["title"] for it in items], [it.get("snippet", "") for it in items])
    for it, cid in zip(items, cids, strict=False):
        it["cluster_id"] = cid
    return items
