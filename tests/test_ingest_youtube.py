import json
from pathlib import Path

from etl.ingest_youtube import json3_to_text, pick_caption, video_row
from etl.shards import DoneSet, ShardWriter, read_shards

FIX = Path(__file__).parent / "fixtures"
INFO = json.loads((FIX / "youtube_info_fixture.json").read_text(encoding="utf-8"))


def test_pick_caption_prefers_manual_json3_in_requested_language():
    assert pick_caption(INFO, "ko") == ("https://example.test/manual.json3", "manual", "ko")


def test_pick_caption_falls_back_to_auto_orig_variant():
    info = {k: v for k, v in INFO.items() if k != "subtitles"}
    url, kind, clang = pick_caption(info, "ko")
    assert kind == "auto" and clang == "ko" and url == "https://example.test/auto.json3"


def test_pick_caption_none_when_language_missing():
    assert pick_caption(INFO, "fr") is None


def test_json3_to_text_joins_segments_and_drops_newlines():
    data = {"events": [{"segs": [{"utf8": "먼저 "}, {"utf8": "고기를\n"}]}, {"segs": [{"utf8": "볶아요"}]}, {"aAppend": 1}]}
    assert json3_to_text(data) == "먼저 고기를 볶아요"


def test_video_row_carries_engagement_and_empty_structure():
    row = video_row(INFO, "ko", ("text", "manual", "ko"))
    assert row["view_count"] == 120000 and row["comment_count"] == 210
    assert row["ingredients"] == [] and row["steps"] == []
    assert row["url"].endswith("abc123XYZ00") and json.loads(row["chapters"])[0]["title"] == "재료"


def test_shards_and_done_resume(tmp_path):
    done = DoneSet(tmp_path / "d.txt")
    done.add("a"); done.add("b", "fetch_fail")
    assert "a" in DoneSet(tmp_path / "d.txt") and "b" in DoneSet(tmp_path / "d.txt")
    w = ShardWriter(tmp_path, "v", flush_every=2)
    w.add({"x": 1, "l": ["a"]}); w.add({"x": 2, "l": []}); w.add({"x": 3, "l": ["b", "c"]})
    w.flush()
    assert len(list(tmp_path.glob("v-*.parquet"))) == 2
    assert ShardWriter(tmp_path, "v").n == 2          # resumes numbering
    assert read_shards(tmp_path, "v")["x"].tolist() == [1, 2, 3]
