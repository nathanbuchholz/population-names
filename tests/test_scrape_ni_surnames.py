from unittest.mock import MagicMock

from scripts.scrapers.scrape_ni_surnames import (
    _clean_wiki_name,
    _get_next_page_url,
    _is_meta_entry,
    _parse_category_page,
    fetch_category,
    scrape,
)

# --- Fixtures: realistic Wikipedia category HTML fragments ---

CATEGORY_PAGE_1 = (
    "<html><body>"
    '<div id="mw-pages">'
    "<div><div>"
    '<div class="mw-category-group"><h3>B</h3><ul>'
    '<li><a href="/wiki/Barry_(surname)" title="Barry (surname)">Barry (surname)</a></li>'
    '<li><a href="/wiki/Brennan_(surname)" title="Brennan (surname)">Brennan (surname)</a></li>'
    "</ul></div>"
    '<div class="mw-category-group"><h3>C</h3><ul>'
    '<li><a href="/wiki/Callaghan" title="Callaghan">Callaghan</a></li>'
    "</ul></div>"
    "</div></div></div>"
    '<a href="/w/index.php?title=Category:Test&amp;pagefrom=D" title="Category:Test">next page</a>'
    "</body></html>"
)

CATEGORY_PAGE_2 = (
    "<html><body>"
    '<div id="mw-pages">'
    "<div><div>"
    '<div class="mw-category-group"><h3>D</h3><ul>'
    '<li><a href="/wiki/Doyle_(surname)" title="Doyle (surname)">Doyle (surname)</a></li>'
    '<li><a href="/wiki/Duffy_(name)" title="Duffy (name)">Duffy (name)</a></li>'
    "</ul></div>"
    "</div></div></div>"
    "</body></html>"
)

CATEGORY_PAGE_WITH_ENTITIES = (
    "<html><body>"
    '<div id="mw-pages">'
    "<div><div>"
    '<div class="mw-category-group"><h3>O</h3><ul>'
    '<li><a href="/wiki/O%27Brien">O&#039;Brien</a></li>'
    '<li><a href="/wiki/O%27Connor">O&#039;Connor</a></li>'
    '<li><a href="/wiki/List_of_people">List of people with surname O&#039;Donnell</a></li>'
    '<li><a href="/wiki/Clan_ODwyer">Clan O&#039;Dwyer</a></li>'
    "</ul></div>"
    "</div></div></div>"
    "</body></html>"
)

EMPTY_CATEGORY_PAGE = "<html><body><p>No results.</p></body></html>"


class TestCleanWikiName:
    def test_strips_surname_suffix(self):
        assert _clean_wiki_name("Barry (surname)") == "Barry"

    def test_strips_name_suffix(self):
        assert _clean_wiki_name("Duffy (name)") == "Duffy"

    def test_strips_disambiguation(self):
        assert _clean_wiki_name("Kelly (disambiguation)") == "Kelly"

    def test_no_suffix(self):
        assert _clean_wiki_name("Callaghan") == "Callaghan"

    def test_whitespace(self):
        assert _clean_wiki_name("  O'Brien  ") == "O'Brien"

    def test_decodes_html_entities(self):
        assert _clean_wiki_name("O&#039;Brien") == "O'Brien"

    def test_decodes_amp(self):
        assert _clean_wiki_name("O&apos;Neill") == "O'Neill"


class TestIsMetaEntry:
    def test_list_of(self):
        assert _is_meta_entry("List of people with surname O'Donnell")

    def test_clan(self):
        assert _is_meta_entry("Clan O'Dwyer")

    def test_category(self):
        assert _is_meta_entry("Category:Irish surnames")

    def test_normal_name(self):
        assert not _is_meta_entry("O'Brien")

    def test_case_insensitive(self):
        assert _is_meta_entry("list of Irish names")


class TestParseCategoryPage:
    def test_extracts_names(self):
        names = _parse_category_page(CATEGORY_PAGE_1)
        assert "Barry (surname)" in names
        assert "Brennan (surname)" in names
        assert "Callaghan" in names

    def test_empty_page(self):
        assert _parse_category_page(EMPTY_CATEGORY_PAGE) == []


class TestGetNextPageUrl:
    def test_finds_next_page(self):
        url = _get_next_page_url(CATEGORY_PAGE_1, "https://en.wikipedia.org/wiki/Category:Test")
        assert url == "https://en.wikipedia.org/w/index.php?title=Category:Test&pagefrom=D"

    def test_no_next_page(self):
        url = "https://en.wikipedia.org/wiki/Category:Test"
        assert _get_next_page_url(CATEGORY_PAGE_2, url) is None


class TestFetchCategory:
    def test_follows_pagination(self):
        mock_client = MagicMock()
        resp1 = MagicMock()
        resp1.text = CATEGORY_PAGE_1
        resp2 = MagicMock()
        resp2.text = CATEGORY_PAGE_2
        mock_client.get.side_effect = [resp1, resp2]

        names = fetch_category(mock_client, "https://en.wikipedia.org/wiki/Category:Test")

        assert mock_client.get.call_count == 2
        assert len(names) == 5  # 3 from page 1, 2 from page 2

    def test_single_page(self):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = CATEGORY_PAGE_2  # no "next page" link
        mock_client.get.return_value = resp

        names = fetch_category(mock_client, "https://en.wikipedia.org/wiki/Category:Test")
        assert len(names) == 2


class TestScrape:
    def test_deduplication(self, tmp_path, monkeypatch):
        """Names appearing in both categories get merged origin tags."""
        # Both categories return "Barry (surname)"
        page_anglicised = CATEGORY_PAGE_2.replace("Doyle (surname)", "Barry (surname)").replace(
            "Duffy (name)", "Murphy (surname)"
        )
        page_irish = CATEGORY_PAGE_2.replace("Doyle (surname)", "Barry (surname)").replace(
            "Duffy (name)", "Kelly"
        )

        call_count = 0

        def mock_get(url):
            nonlocal call_count
            resp = MagicMock()
            if call_count == 0:
                resp.text = page_anglicised
            else:
                resp.text = page_irish
            call_count += 1
            return resp

        mock_client = MagicMock()
        mock_client.get.side_effect = mock_get
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "scripts.scrapers.scrape_ni_surnames.httpx.Client",
            lambda **kw: mock_client,
        )

        output = scrape(tmp_path)

        import csv

        with open(output) as f:
            rows = list(csv.DictReader(f))

        names = [r["name"] for r in rows]
        assert "Barry" in names

        barry = next(r for r in rows if r["name"] == "Barry")
        assert "anglicised" in barry["origin"]
        assert "irish_origin" in barry["origin"]

        # Murphy only in anglicised, Kelly only in irish_origin
        assert "Murphy" in names
        assert "Kelly" in names

    def test_dry_run(self, tmp_path):
        output = scrape(tmp_path, dry_run=True)
        assert output == tmp_path / "ni_surnames.csv"
        assert not output.exists()

    def test_decodes_entities_and_filters_meta(self, tmp_path, monkeypatch):
        """HTML entities are decoded and meta entries (List of, Clan) are filtered out."""
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = CATEGORY_PAGE_WITH_ENTITIES
        mock_client.get.return_value = resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "scripts.scrapers.scrape_ni_surnames.httpx.Client",
            lambda **kw: mock_client,
        )

        output = scrape(tmp_path)

        import csv

        with open(output) as f:
            rows = list(csv.DictReader(f))

        names = [r["name"] for r in rows]
        # Entities decoded
        assert "O'Brien" in names
        assert "O'Connor" in names
        # Meta entries filtered
        assert not any("List of" in n for n in names)
        assert not any("Clan" in n for n in names)

    def test_writes_csv(self, tmp_path, monkeypatch):
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = CATEGORY_PAGE_2
        mock_client.get.return_value = resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            "scripts.scrapers.scrape_ni_surnames.httpx.Client",
            lambda **kw: mock_client,
        )

        output = scrape(tmp_path)
        assert output.exists()

        import csv

        with open(output) as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == ["name", "origin"]
            rows = list(reader)
        assert len(rows) > 0
