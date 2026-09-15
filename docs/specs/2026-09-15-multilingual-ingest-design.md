# Multilingual + YouTube ingest — design

**Date:** 2026-09-15 · **Status:** approved in chat, implementing · **Serves:** plan step 7 of `docs/plans/2026-09-15-phase1-contrastive-critic.md`, pulled ahead of step 3 because an English-only corpus caps the idea of taste.

## Decisions

- **Languages:** ko, ja, zh, es, fr, de, it, pt (plus en on YouTube, same pipeline).
- **Scale:** large crawl. Web: sitemap-driven, tens of thousands per site. YouTube: 5–10k videos per language via search seeds → top channels → channel uploads.
- **Where it runs:** the Mac, in the background, resumable. Never DSMLP (acceptable-use forbids scraping from campus infrastructure; YouTube blocks datacenter IPs). Output syncs to DSMLP for processing.
- **Politeness:** robots.txt honored, 1 request/s per host, identifying user agent, backoff on 429/5xx. YouTube: captions only, no media, ~1.5 s between videos.

## Components

| Module | Does | Depends on |
|---|---|---|
| `etl/shards.py` | `ShardWriter` (sharded parquet, flush every N rows) and `DoneSet` (append-only resume log) | pandas |
| `etl/ingest_web.py` | robots → sitemaps → recipe URLs → fetch → `recipe_scrapers.scrape_html` (schema.org fallback for unsupported hosts) → rows | requests, recipe-scrapers |
| `etl/ingest_youtube.py` | per-language native queries → `ytsearch` seeds → top channels → channel uploads; per video metadata + description + chapters + caption transcript (manual preferred, else auto) | yt-dlp, requests |

Both expose `--probe` (10 items, prints a summary) and `--lang a,b --limit N`.

## Data layout

```
data/raw/web/{lang}/{host}.urls.txt       discovered recipe URLs (cache)
data/raw/web/{lang}/{host}.done.txt       url \t status   (resume log)
data/raw/web/{lang}/{host}-00000.parquet  shards
data/raw/youtube/{lang}/seeds.json        search seeds + channel counts
data/raw/youtube/{lang}/videos.done.txt
data/raw/youtube/{lang}/videos-00000.parquet
```

## Column contract extension

| Column | Type | Note |
|---|---|---|
| `lang` | str | requested language |
| `source_kind` | `web` / `youtube` | |
| `url` | str | |
| `published` | str (YYYY-MM-DD or YYYYMMDD) | |
| `view_count`, `like_count`, `comment_count` | int64 / NaN | YouTube engagement = reproduction proxy |
| `transcript`, `transcript_kind`, `transcript_lang` | str | YouTube only |
| `description`, `chapters` | str / json str | YouTube only |
| `review_texts` | list[str] | web only, when the page exposes reviews |
| `ingredients`, `steps`, `rating_mean`, `rating_n`, `title`, `minutes` | as Phase 0 | empty for YouTube until the extraction pass |

## Accepted limits

1. Transcripts are raw. Structuring them into ingredients/steps is a later language-model extraction stage with its own cost.
2. `REMAKE_RE` in `etl/confidence.py` is English-only. Per-language phrase lists are a small follow-up before step 2 tiers apply to this data.
3. Site list after the 2026-09-15 probe (all parse 10/10 unless noted):
   ko 10000recipe (schema.org fallback; ratings sparse, no review text) ·
   ja Cookpad by **ID enumeration** (no sitemap; IDs are global across locales, so rows come back ja/id/ar/es… and `lang` is taken from the page) ·
   zh **not crawled** (xiachufang, meishichina, douguo, xinshipu all 403/429 the crawler agent; Common Crawl holds only ~300 pages). Instead: the published **XiaChuFang corpus** (Liu et al., EMNLP 2022; 1,479,751 recipes after ingest, 1,178,450 with a curated `dish` label over 29,548 dishes; pre-Dec 2020, no ratings/comments) via `etl/ingest_xiachufang.py` → `data/corpus/xiachufang.parquet`. Reproduction signal for zh to come from Bilibili engagement/comments (yt-dlp works; no subtitles) and YouTube zh transcripts (Taiwan/HK/diaspora-skewed, label as such) ·
   es Recetas de Rechupete under abc.es (RecetasGratis' sitemap moved and 404s) ·
   fr Marmiton (slow, ~17 s/page) · de lecker.de (Chefkoch 403s every sitemap path) ·
   it GialloZafferano · pt TudoGostoso.
4. YouTube's caption endpoint returns 429 after bursts; the crawler backs off 30/90/180 s, marks the video `rate_limited`, and retries it on the next run. Pacing is 3 s/video, one process for all languages (parallel processes would share the IP limit).

## Terms

YouTube's terms disallow automated access; this collects captions only, at low rate, for research. Recipe-site terms vary; robots and rate limits are honored. Kyle accepted this on 2026-09-15.
