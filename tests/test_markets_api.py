"""Market/news API tests (addendum E)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


class TestMarketsOverview:
    def test_overview_shape_and_honesty_fields(self):
        r = client.get("/api/v1/markets/overview")
        assert r.status_code == 200
        doc = r.json()
        assert doc["data_mode"] == "demo"
        gold = doc["global"]["gold"]
        assert gold["unit"] == {"currency": "USD", "quantity": "unit"}
        assert gold["is_demo"] is True
        free = doc["iran"]["usd_free"]
        assert free["is_unofficial"] is True
        assert "غیررسمی" in doc["iran"]["unofficial_badge"]

    def test_derived_series_present_with_formulas(self):
        doc = client.get("/api/v1/markets/overview").json()
        d = doc["derived"]
        assert "implied_gram_irr" in d and "formula" in d["implied_gram_irr"]
        assert "bubble_pct" in d["coin_bubble"]
        assert "gap_pct" in d["usd_gap"]
        assert doc["cross_market"]["status"] in ("ok", "warning", "insufficient_data")

    def test_toman_rial_toggle(self):
        toman = client.get("/api/v1/markets/overview", params={"prefer_toman": True}).json()
        rial = client.get("/api/v1/markets/overview", params={"prefer_toman": False}).json()
        assert toman["units"]["currency_display"] == "TOMAN"
        assert rial["units"]["currency_display"] == "IRR"
        vt = toman["derived"]["implied_gram_irr"]["display"][0]
        vr = rial["derived"]["implied_gram_irr"]["display"][0]
        assert abs(vr - vt * 10) < 1  # toman = rial/10

    def test_never_live_claim(self):
        doc = client.get("/api/v1/markets/overview").json()
        assert doc["data_mode"] in ("demo", "live")
        # demo state must be flagged
        assert doc["global"]["gold"]["is_demo"] is True


class TestNewsEndpoints:
    def test_feed_honest_coverage_note(self):
        doc = client.get("/api/v1/markets/news").json()
        assert "پوشش کامل" in doc["coverage_note"]  # never claims complete coverage
        assert "last_successful_fetch" in doc
        assert all(it["is_demo"] for it in doc["items"])

    def test_feed_filters(self):
        doc = client.get("/api/v1/markets/news", params={"topic": "gold"}).json()
        assert all("gold" in it["topics"] for it in doc["items"])

    def test_value_verdicts_are_honest(self):
        doc = client.get("/api/v1/markets/news/value").json()
        assert "Diebold-Mariano" in doc["method"]
        assert doc["verdicts"]
        for v in doc["verdicts"]:
            assert v["verdict"]  # non-empty verdict string


class TestDrivers:
    def test_drivers_shape_and_caution(self):
        doc = client.get("/api/v1/markets/drivers", params={"instrument": "XAU_USD"}).json()
        assert doc["data_mode"] == "demo"
        assert "spurious" in doc["caution"] or "کاذب" in doc["caution"]
        assert "USD_IRR_FREE" in doc["series"]
        assert "lead_lag" in doc["series"]["USD_IRR_FREE"]
        assert "regime_dependence" in doc
