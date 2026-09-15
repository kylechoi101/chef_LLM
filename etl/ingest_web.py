"""Multilingual web recipe ingest: robots -> sitemaps -> recipe URLs -> polite fetch
-> schema.org / recipe-scrapers parse -> sharded parquet. Resumable. Runs on the Mac
(never DSMLP: acceptable-use forbids scraping from campus infrastructure).
"""
import argparse
import gzip
import json
import re
import sys
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from recipe_scrapers import scrape_html

from etl.shards import DoneSet, ShardWriter

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "chef-llm-research-crawler/0.1 (+https://github.com/kylechoi101/chef_LLM; academic research)"
MIN_INTERVAL = 1.0  # seconds between requests to the same host


@dataclass
class Site:
    lang: str
    host: str
    url_re: str                                   # recipe-page pattern (regex, searched in full URL)
    sitemaps: list[str] = field(default_factory=list)  # explicit; else discovered from robots.txt
    sitemap_re: str = ""                          # optional: only descend into child sitemaps matching this
    id_url: str = ""                              # ID-enumeration mode: e.g. "https://cookpad.com/jp/recipes/{id}"
    id_range: tuple[int, int] = (0, 0)            # sampled uniformly at random (seeded) when id_url is set


SITES: dict[str, list[Site]] = {
    "ko": [Site("ko", "www.10000recipe.com", r"/recipe/\d+")],
    # Cookpad IDs are global across locales: enumeration yields ja/id/es/ar/... rows; lang comes from the page.
    "ja": [Site("ja", "cookpad.com", r"cookpad\.com/[a-z]{2}/[a-z]+/\d+",
                id_url="https://cookpad.com/jp/recipes/{id}", id_range=(15_000_000, 24_000_000))],
    # zh: xiachufang / meishichina / douguo / xinshipu all 403/429 the crawler agent (2026-09-15). Deferred; YouTube zh works.
    "es": [Site("es", "www.abc.es", r"abc\.es/recetasderechupete/receta-[a-z0-9-]+/\d+/",
                sitemaps=["https://www.abc.es/recetasderechupete/sitemap_index.xml"], sitemap_re=r"post-sitemap")],
    "fr": [Site("fr", "www.marmiton.org", r"/recettes/recette_[a-z0-9-]+_\d+\.aspx")],
    # de: chefkoch.de 403s every sitemap path for the crawler agent; lecker.de is a supported scraper with open sitemaps.
    "de": [Site("de", "www.lecker.de", r"lecker\.de/[a-z0-9-]+-\d+\.html$", sitemap_re=r"/sitemap/\d+\.xml")],
    "it": [Site("it", "ricette.giallozafferano.it", r"giallozafferano\.it/[A-Za-z0-9-]+\.html$")],
    "pt": [Site("pt", "www.tudogostoso.com.br", r"/receita/\d+-")],
}

_last_hit: dict[str, float] = {}
_robots: dict[str, robotparser.RobotFileParser | None] = {}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "*"})
    return s


def _allowed(session: requests.Session, url: str) -> bool:
    host = urlparse(url).netloc
    if host not in _robots:
        rp = robotparser.RobotFileParser()
        try:
            r = session.get(f"https://{host}/robots.txt", timeout=15)
            rp.parse(r.text.splitlines() if r.ok else [])
        except requests.RequestException:
            rp.parse([])
        _robots[host] = rp
    rp = _robots[host]
    return rp is None or rp.can_fetch(UA, url) or rp.can_fetch("*", url)


def fetch(session: requests.Session, url: str, retries: int = 3) -> requests.Response | None:
    host = urlparse(url).netloc
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.monotonic() - _last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()
        try:
            r = session.get(url, timeout=25)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 5 * 2 ** attempt))
            continue
        return None
    return None


# ---- sitemap discovery -------------------------------------------------------

_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)


def parse_sitemap(content: bytes) -> tuple[list[str], list[str]]:
    """Return (child_sitemaps, page_urls)."""
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    text = content.decode("utf-8", errors="replace")
    locs = [loc.strip() for loc in _LOC.findall(text)]
    if "<sitemapindex" in text[:2000]:
        return locs, []
    return [], locs


def discover_sitemaps(session: requests.Session, site: Site) -> list[str]:
    if site.sitemaps:
        return list(site.sitemaps)
    r = fetch(session, f"https://{site.host}/robots.txt")
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text) if r else []
    return maps or [f"https://{site.host}/sitemap.xml"]


def iter_recipe_urls(session: requests.Session, site: Site, max_urls: int, cache: Path | None = None):
    if site.id_url:
        import random
        rng = random.Random(site.host)  # deterministic order => resumable via DoneSet
        lo, hi = site.id_range
        for _ in range(max_urls):
            yield site.id_url.format(id=rng.randint(lo, hi))
        return
    if cache and cache.exists():
        for ln in cache.read_text().splitlines():
            if ln:
                yield ln
        return
    url_re, sm_re = re.compile(site.url_re), re.compile(site.sitemap_re) if site.sitemap_re else None
    queue, seen_maps, found = discover_sitemaps(session, site), set(), 0
    tmp = cache.with_suffix(".tmp") if cache else None   # atomic: renamed to cache only when discovery completes
    out = open(tmp, "w", encoding="utf-8") if tmp else None
    while queue and found < max_urls:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        r = fetch(session, sm)
        if not r:
            continue
        children, urls = parse_sitemap(r.content)
        queue.extend(c for c in children if not sm_re or sm_re.search(c))
        for u in urls:
            if url_re.search(u):
                found += 1
                if out:
                    out.write(u + "\n")
                yield u
                if found >= max_urls:
                    break
    if out:
        out.close()
        if found < max_urls:          # discovery exhausted the sitemaps => complete list, safe to cache
            tmp.rename(cache)


# ---- parsing -----------------------------------------------------------------

def _get(scraper, name):
    try:
        v = getattr(scraper, name)()
        return v if v not in ("", [], {}) else None
    except Exception:
        return None


def _review_texts(scraper) -> list[str]:
    """Review bodies from schema.org `review` (the scraper API has no reviews()), else site scraper."""
    reviews = None
    try:
        reviews = scraper.schema.data.get("review")
    except Exception:
        pass
    if reviews is None:
        reviews = _get(scraper, "reviews")
    if not reviews:
        return []
    out = []
    for rv in reviews if isinstance(reviews, list) else [reviews]:
        if isinstance(rv, dict):
            t = rv.get("reviewBody") or rv.get("review_text") or rv.get("text") or rv.get("description") or ""
        else:
            t = str(rv)
        if t.strip():
            out.append(t.strip())
    return out


def parse_recipe(html: str, url: str) -> dict | None:
    try:
        s = scrape_html(html, org_url=url, supported_only=False)
    except Exception:
        return None
    title = _get(s, "title")
    ingredients = [str(i) for i in (_get(s, "ingredients") or [])]
    steps = [str(x) for x in (_get(s, "instructions_list") or [])]
    if not title or not (ingredients or steps):
        return None
    return {
        "title": title,
        "ingredients": ingredients,
        "steps": steps,
        "minutes": _get(s, "total_time"),
        "yields": _get(s, "yields"),
        "rating_mean": _get(s, "ratings"),
        "rating_n": _get(s, "ratings_count"),
        "page_lang": _get(s, "language"),
        "category": _get(s, "category"),
        "author": _get(s, "author"),
        "review_texts": _review_texts(s),
    }


# ---- crawl -------------------------------------------------------------------

def crawl(site: Site, limit: int, probe: bool = False) -> dict:
    session = _session()
    d = DATA / "raw" / "web" / site.lang
    d.mkdir(parents=True, exist_ok=True)
    done = DoneSet(d / f"{site.host}.done.txt")
    writer = ShardWriter(d, site.host, flush_every=10 if probe else 200)
    stats = {"host": site.host, "urls_seen": 0, "fetched": 0, "parsed": 0, "skipped_done": 0, "blocked": 0}
    cache = None if probe else d / f"{site.host}.urls.txt"
    for url in iter_recipe_urls(session, site, max_urls=limit * 4 if probe else 2_000_000, cache=cache):
        stats["urls_seen"] += 1
        if url in done:
            stats["skipped_done"] += 1
            continue
        if not _allowed(session, url):
            stats["blocked"] += 1
            done.add(url, "robots")
            continue
        r = fetch(session, url)
        if not r:
            done.add(url, "fetch_fail")
            continue
        stats["fetched"] += 1
        row = parse_recipe(r.text, url)
        if not row:
            done.add(url, "parse_fail")
            continue
        page_lang = (row.get("page_lang") or "")[:2].lower()
        row.update({"lang": page_lang or site.lang, "source": site.host, "source_kind": "web", "url": r.url or url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        writer.add(row)
        done.add(url, "ok")
        stats["parsed"] += 1
        if probe and stats["parsed"] >= limit:
            break
        if not probe and stats["parsed"] >= limit:
            break
    writer.flush()
    stats["shards"] = writer.n
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=",".join(SITES))
    ap.add_argument("--limit", type=int, default=50_000)
    ap.add_argument("--probe", action="store_true", help="10 recipes per site, print summary")
    a = ap.parse_args()
    for lang in a.lang.split(","):
        for site in SITES[lang]:
            t0 = time.time()
            st = crawl(site, limit=10 if a.probe else a.limit, probe=a.probe)
            st["seconds"] = round(time.time() - t0)
            print(json.dumps({"lang": lang, **st}, ensure_ascii=False), file=sys.stderr, flush=True)
