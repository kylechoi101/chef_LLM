"""YouTube cooking-video ingest: native-language search seeds -> top channels -> channel
uploads; per video: metadata + description + chapters + caption transcript (manual
preferred, else auto). Captions only, no media. Resumable. Runs on the Mac.
"""
import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
import yt_dlp

from etl.shards import DoneSet, ShardWriter

DATA = Path(__file__).resolve().parent.parent / "data"
SLEEP = 3.0
CAPTION_BACKOFF = (30, 90, 180)  # seconds, on HTTP 429 from the timedtext endpoint
SEARCH_N = 200
TOP_CHANNELS = 15
CHANNEL_CAP = 1500

QUERIES: dict[str, list[str]] = {
    "ko": ["레시피", "만드는 법", "집밥 요리", "요리 레시피", "간단 요리", "반찬 만들기", "찌개 끓이는 법", "국 끓이는 법", "볶음 레시피", "한식 요리"],
    "ja": ["レシピ", "作り方", "簡単レシピ", "料理", "おかず レシピ", "夕飯 レシピ", "お弁当 レシピ", "煮物 作り方", "炒め物 レシピ", "お菓子 作り方"],
    "zh": ["食谱", "做法", "家常菜", "菜谱", "怎么做 好吃", "烹饪 教程", "家常菜 做法", "炒菜 教程", "汤 做法", "烘焙 教程"],
    "es": ["receta", "cómo hacer", "recetas fáciles", "receta casera", "cocina fácil", "recetas de cocina", "postre receta", "guiso receta", "receta tradicional", "comida casera"],
    "fr": ["recette", "recette facile", "comment faire", "cuisine maison", "recette rapide", "recette dessert", "recette traditionnelle", "plat facile", "recette de chef", "cuisine française"],
    "de": ["Rezept", "einfaches Rezept", "schnelle Rezepte", "Kochen", "selber machen", "Rezept Abendessen", "Kuchen Rezept", "Hausmannskost", "Rezept einfach lecker", "Kochrezept"],
    "it": ["ricetta", "ricette facili", "come fare", "cucina italiana", "ricetta veloce", "ricetta dolce", "primi piatti ricetta", "ricetta della nonna", "ricetta tradizionale", "ricetta semplice"],
    "pt": ["receita", "como fazer", "receita fácil", "receitas caseiras", "receita rápida", "receita de bolo", "comida caseira", "receita simples", "receita tradicional", "receita deliciosa"],
    "en": ["recipe", "how to make", "easy recipe", "easy dinner recipe", "homemade", "dessert recipe", "weeknight dinner", "one pot recipe", "baking recipe", "classic recipe"],
}


def _ydl(flat: bool) -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL({
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": "in_playlist" if flat else False,
        "ignoreerrors": True, "noplaylist": False,
    })


def search(query: str, n: int = SEARCH_N) -> list[dict]:
    info = _ydl(flat=True).extract_info(f"ytsearch{n}:{query}", download=False) or {}
    return [e for e in info.get("entries") or [] if e and e.get("id")]


def channel_videos(channel_id: str, cap: int = CHANNEL_CAP) -> list[str]:
    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True,
                            "extract_flat": True, "ignoreerrors": True, "playlistend": cap})
    info = ydl.extract_info(f"https://www.youtube.com/channel/{channel_id}/videos", download=False) or {}
    return [e["id"] for e in info.get("entries") or [] if e and e.get("id")]


# ---- captions ----------------------------------------------------------------

def pick_caption(info: dict, lang: str) -> tuple[str, str, str] | None:
    """Return (url, kind, caption_lang) preferring manual subtitles, then auto captions,
    and exact language, then `<lang>-orig`, then any `<lang>*` variant. json3 format."""
    for kind, key in (("manual", "subtitles"), ("auto", "automatic_captions")):
        tracks = info.get(key) or {}
        for cand in ([lang, f"{lang}-orig"] + sorted(k for k in tracks if k.startswith(lang + "-") or k.startswith(lang + "_"))):
            fmts = tracks.get(cand) or []
            for f in fmts:
                if f.get("ext") == "json3" and f.get("url"):
                    return f["url"], kind, cand
    return None


def json3_to_text(data: dict) -> str:
    out = []
    for ev in data.get("events") or []:
        t = "".join(s.get("utf8", "") for s in ev.get("segs") or []).replace("\n", " ").strip()
        if t:
            out.append(t)
    return " ".join(out)


def fetch_transcript(session: requests.Session, info: dict, lang: str) -> tuple[str | None, str | None, str | None]:
    pick = pick_caption(info, lang)
    if not pick:
        return None, None, None
    url, kind, clang = pick
    for attempt, backoff in enumerate(CAPTION_BACKOFF + (None,)):
        try:
            r = session.get(url, timeout=25)
        except requests.RequestException:
            return None, kind, clang
        if r.status_code == 429:
            if backoff is None:
                return None, "rate_limited", clang
            time.sleep(backoff)
            continue
        if not r.ok:
            return None, kind, clang
        try:
            return json3_to_text(r.json()), kind, clang
        except ValueError:
            return None, kind, clang
    return None, kind, clang


# ---- per video ---------------------------------------------------------------

def video_row(info: dict, lang: str, transcript: tuple) -> dict:
    text, kind, clang = transcript
    return {
        "video_id": info.get("id"), "lang": lang, "source": "youtube", "source_kind": "youtube",
        "url": f"https://www.youtube.com/watch?v={info.get('id')}",
        "title": info.get("title"), "description": info.get("description"),
        "channel": info.get("channel") or info.get("uploader"), "channel_id": info.get("channel_id"),
        "published": info.get("upload_date"), "duration": info.get("duration"),
        "view_count": info.get("view_count"), "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "video_lang": info.get("language"),
        "tags": [str(t) for t in info.get("tags") or []],
        "chapters": json.dumps(info.get("chapters") or [], ensure_ascii=False),
        "transcript": text, "transcript_kind": kind, "transcript_lang": clang,
        "ingredients": [], "steps": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def crawl(lang: str, limit: int, probe: bool = False) -> dict:
    d = DATA / "raw" / "youtube" / lang
    d.mkdir(parents=True, exist_ok=True)
    done = DoneSet(d / "videos.done.txt")
    done.keys -= done.with_status("rate_limited")  # retry those next run
    writer = ShardWriter(d, "videos", flush_every=5 if probe else 100)
    session = requests.Session()
    ydl = _ydl(flat=False)
    stats = {"lang": lang, "seed_videos": 0, "channels": 0, "candidates": 0, "fetched": 0, "with_transcript": 0, "skipped_done": 0}

    seeds_path = d / "seeds.json"
    if seeds_path.exists() and not probe:
        seeds = json.loads(seeds_path.read_text())
    else:
        vids, chans = [], Counter()
        queries = QUERIES[lang][:1] if probe else QUERIES[lang]
        for q in queries:
            for e in search(q, n=10 if probe else SEARCH_N):
                vids.append(e["id"])
                if e.get("channel_id"):
                    chans[e["channel_id"]] += 1
            time.sleep(SLEEP)
        seeds = {"videos": list(dict.fromkeys(vids)), "channels": chans.most_common(TOP_CHANNELS)}
        if not probe:
            seeds_path.write_text(json.dumps(seeds, ensure_ascii=False))
    stats["seed_videos"], stats["channels"] = len(seeds["videos"]), len(seeds["channels"])

    def candidates():
        yield from seeds["videos"]
        if probe:
            return
        for cid, _ in seeds["channels"]:
            try:
                yield from channel_videos(cid)
            except Exception:
                continue
            time.sleep(SLEEP)

    for vid in candidates():
        stats["candidates"] += 1
        if vid in done:
            stats["skipped_done"] += 1
            continue
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        except Exception:
            info = None
        if not info:
            done.add(vid, "fetch_fail")
            continue
        tr = fetch_transcript(session, info, lang)
        writer.add(video_row(info, lang, tr))
        done.add(vid, "ok" if tr[0] else ("rate_limited" if tr[1] == "rate_limited" else "no_transcript"))
        stats["fetched"] += 1
        stats["with_transcript"] += bool(tr[0])
        if stats["fetched"] >= limit:
            break
        time.sleep(SLEEP)
    writer.flush()
    stats["shards"] = writer.n
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=",".join(QUERIES))
    ap.add_argument("--limit", type=int, default=8000)
    ap.add_argument("--probe", action="store_true", help="1 query, 5 videos per language")
    a = ap.parse_args()
    for lang in a.lang.split(","):
        t0 = time.time()
        st = crawl(lang, limit=5 if a.probe else a.limit, probe=a.probe)
        st["seconds"] = round(time.time() - t0)
        print(json.dumps(st, ensure_ascii=False), file=sys.stderr, flush=True)
