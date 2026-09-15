from pathlib import Path

from etl.ingest_web import SITES, parse_recipe, parse_sitemap

FIX = Path(__file__).parent / "fixtures"


def test_parse_schema_org_recipe_in_korean():
    html = (FIX / "web_recipe_fixture.html").read_text(encoding="utf-8")
    row = parse_recipe(html, "https://www.10000recipe.com/recipe/999")
    assert row["title"] == "돼지고기 김치찌개"
    assert len(row["ingredients"]) == 5 and "두부 1/2모" in row["ingredients"]
    assert len(row["steps"]) == 3 and row["steps"][0].startswith("돼지고기를")
    assert row["rating_mean"] == 4.7 and row["rating_n"] == 123
    assert row["minutes"] == 30
    assert any("세 번째" in t for t in row["review_texts"])


def test_parse_returns_none_without_recipe_markup():
    assert parse_recipe("<html><body><p>nothing</p></body></html>", "https://example.com/x") is None


def test_sitemap_index_vs_urlset():
    index = b'<?xml version="1.0"?><sitemapindex><sitemap><loc>https://h/a.xml</loc></sitemap></sitemapindex>'
    urlset = b'<?xml version="1.0"?><urlset><url><loc>https://h/recipe/1</loc></url><url><loc>https://h/about</loc></url></urlset>'
    assert parse_sitemap(index) == (["https://h/a.xml"], [])
    assert parse_sitemap(urlset) == ([], ["https://h/recipe/1", "https://h/about"])


def test_site_url_patterns_match_real_shapes():
    import re
    samples = {
        "ko": "https://www.10000recipe.com/recipe/6845489",
        "ja": "https://cookpad.com/jp/recipes/19318765-title",
        "es": "https://www.abc.es/recetasderechupete/receta-de-espaguetis-con-pate-y-verduras/863/",
        "fr": "https://www.marmiton.org/recettes/recette_gratin-dauphinois_12345.aspx",
        "de": "https://www.lecker.de/falscher-hase-5.html",
        "it": "https://ricette.giallozafferano.it/Tiramisu.html",
        "pt": "https://www.tudogostoso.com.br/receita/123-bolo-de-cenoura.html",
    }
    for lang, url in samples.items():
        assert re.search(SITES[lang][0].url_re, url), (lang, url)
    assert re.search(SITES["ja"][0].url_re, "https://cookpad.com/id/resep/22610424")  # locale redirect still matches
