from unittest.mock import MagicMock

from scripts.scrapers.scrape_wales_surnames import (
    _clean_wiki_name,
    fetch_welsh_origin_surnames,
    fetch_wiktionary_surnames,
    scrape,
)

# --- Fixtures: realistic HTML fragments ---

WIKIPEDIA_WELSH_HTML = """
<html><body>
<div id="mw-pages">
<div>
<div>
<div class="mw-category-group"><h3>D</h3><ul>
<li><a href="/wiki/Davies" title="Davies">Davies</a></li>
<li><a href="/wiki/Davis_(surname)" title="Davis (surname)">Davis (surname)</a></li>
</ul></div>
<div class="mw-category-group"><h3>J</h3><ul>
<li><a href="/wiki/Jones_(surname)" title="Jones (surname)">Jones (surname)</a></li>
</ul></div>
<div class="mw-category-group"><h3>W</h3><ul>
<li><a href="/wiki/Welsh_surnames" title="Welsh surnames">Welsh surnames</a></li>
</ul></div>
</div>
</div>
</div>
</body></html>
"""

WIKTIONARY_HTML = """
<html><body>
<dl>
<dd>1. <a href="/wiki/Smith" title="Smith">Smith</a> 714,480</dd>
<dd>2. <a href="/wiki/Jones" title="Jones">Jones</a> 502,091</dd>
<dd>3. <a href="/wiki/Williams" title="Williams">Williams</a> 311,256</dd>
</dl>
</body></html>
"""

WIKTIONARY_NO_COUNT_HTML = """
<html><body>
<dl>
<dd>1. <a href="/wiki/Smith" title="Smith">Smith</a> </dd>
</dl>
</body></html>
"""


class TestCleanWikiName:
    def test_strips_surname_suffix(self):
        assert _clean_wiki_name("Jones (surname)") == "Jones"

    def test_no_suffix(self):
        assert _clean_wiki_name("Davies") == "Davies"

    def test_decodes_html_entities(self):
        assert _clean_wiki_name("O&#039;Brien") == "O'Brien"


class TestFetchWelshOriginSurnames:
    def test_extracts_names(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = WIKIPEDIA_WELSH_HTML
        mock_client.get.return_value = resp

        rows = fetch_welsh_origin_surnames(mock_client)

        names = [r["name"] for r in rows]
        assert "Davies" in names
        assert "Davis" in names
        assert "Jones" in names

    def test_skips_meta_entries(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = WIKIPEDIA_WELSH_HTML
        mock_client.get.return_value = resp

        rows = fetch_welsh_origin_surnames(mock_client)
        names = [r["name"] for r in rows]
        assert "Welsh surnames" not in names

    def test_tags_welsh_origin(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = WIKIPEDIA_WELSH_HTML
        mock_client.get.return_value = resp

        rows = fetch_welsh_origin_surnames(mock_client)
        assert all(r["origin"] == "welsh" for r in rows)

    def test_empty_page(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = "<html><body>Nothing here</body></html>"
        mock_client.get.return_value = resp

        assert fetch_welsh_origin_surnames(mock_client) == []


class TestFetchWiktionarySurnames:
    def test_extracts_ranked_entries(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = WIKTIONARY_HTML
        mock_client.get.return_value = resp

        rows = fetch_wiktionary_surnames(mock_client)

        assert len(rows) == 3
        assert rows[0] == {"name": "Smith", "rank": 1, "count": 714480, "origin": "eaw_top250"}
        assert rows[1] == {"name": "Jones", "rank": 2, "count": 502091, "origin": "eaw_top250"}

    def test_missing_count(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = WIKTIONARY_NO_COUNT_HTML
        mock_client.get.return_value = resp

        rows = fetch_wiktionary_surnames(mock_client)
        assert len(rows) == 1
        assert rows[0]["count"] is None


class TestScrape:
    def test_deduplication_merges_origins(self, tmp_path, monkeypatch):
        """Jones appears in both Wikipedia (welsh) and Wiktionary (eaw_top250)."""
        mock_client = MagicMock()

        wiki_resp = MagicMock()
        wiki_resp.text = WIKIPEDIA_WELSH_HTML
        wikt_resp = MagicMock()
        wikt_resp.text = WIKTIONARY_HTML

        def mock_get(url):
            if "wikipedia" in url:
                return wiki_resp
            return wikt_resp

        mock_client.get.side_effect = mock_get
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "scripts.scrapers.scrape_wales_surnames.httpx.Client",
            lambda **kw: mock_client,
        )

        output = scrape(tmp_path)

        import csv

        with open(output) as f:
            rows = list(csv.DictReader(f))

        # Jones is in both sources
        jones = next(r for r in rows if r["name"] == "Jones")
        assert "welsh" in jones["origin"]
        assert "eaw_top250" in jones["origin"]

        # Davies and Davis only in Wikipedia
        davies = next(r for r in rows if r["name"] == "Davies")
        assert davies["origin"] == "welsh"

        # Smith only in Wiktionary
        smith = next(r for r in rows if r["name"] == "Smith")
        assert smith["origin"] == "eaw_top250"

    def test_dry_run(self, tmp_path):
        output = scrape(tmp_path, dry_run=True)
        assert output == tmp_path / "wales_surnames.csv"
        assert not output.exists()

    def test_writes_csv_with_correct_columns(self, tmp_path, monkeypatch):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = WIKTIONARY_HTML

        wiki_resp = MagicMock()
        wiki_resp.text = WIKIPEDIA_WELSH_HTML

        def mock_get(url):
            if "wikipedia" in url:
                return wiki_resp
            return resp

        mock_client.get.side_effect = mock_get
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "scripts.scrapers.scrape_wales_surnames.httpx.Client",
            lambda **kw: mock_client,
        )

        output = scrape(tmp_path)
        assert output.exists()

        import csv

        with open(output) as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == ["name", "rank", "count", "origin"]
            rows = list(reader)
        assert len(rows) > 0
