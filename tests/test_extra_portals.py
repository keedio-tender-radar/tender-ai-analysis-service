from tender_ingestion.connectors.generic_atom_connector import GenericAtomConnector
from tender_ingestion.connectors.portal_registry import extra_portal_sources
from tender_ingestion.normalizers import generic_normalizer

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://portal.es/lic/123</id>
    <title>Servicio de plataforma de datos e inteligencia artificial</title>
    <summary>Big data y APIs</summary>
    <updated>2026-06-20T10:00:00Z</updated>
    <link href="https://portal.es/lic/123"/>
  </entry>
</feed>"""


def test_generic_atom_parse():
    rows = GenericAtomConnector("http://x", "REGIONAL_X").parse(ATOM)
    assert len(rows) == 1
    r = rows[0]
    assert r["source"] == "REGIONAL_X"
    assert r["source_id"] == "123"
    assert "plataforma" in r["title"].lower()


def test_generic_normalizer():
    rows = GenericAtomConnector("http://x", "REGIONAL_X").parse(ATOM)
    payload = generic_normalizer.normalize(rows[0])
    assert payload.source == "REGIONAL_X"
    assert payload.url == "https://portal.es/lic/123"


def test_portal_registry_builds_sources():
    cfg = '[{"source":"REG_X","connector_type":"generic_atom","feed_url":"http://x/feed.atom","enabled":true},{"source":"OFF","feed_url":"http://y","enabled":false}]'
    sources = extra_portal_sources(cfg)
    assert len(sources) == 1
    assert sources[0].connector.name == "REG_X"


def test_portal_registry_bad_json():
    assert extra_portal_sources("not json") == []
    assert extra_portal_sources("") == []
