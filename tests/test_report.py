"""Tests for Phase 7: Persian report generator (computed outputs only)."""

from __future__ import annotations

import json

from app.services.report.generator import render_report

BOARD = {
    "run_id": "experiment-abc123",
    "generated_at": "2026-11-26T10:00:00+00:00",
    "scheme": "expanding",
    "n_splits": 3,
    "horizons": [1, 7],
    "pairs": ["EUR/USD"],
    "config_hash": "cfg1234567890abcdef",
    "snapshot_hash": "snap1234567890abcdef",
    "rows": [
        {
            "pair_symbol": "EUR/USD",
            "target_horizon": 7,
            "model_name": "ml_ridge",
            "mae": 0.00123,
            "rmse": 0.00234,
            "directional_accuracy": 0.53,
            "dm_p_holm": 0.42,
            "verdict": "beats baseline, not significantly",
            "beats_baseline": True,
        },
        {
            "pair_symbol": "EUR/USD",
            "target_horizon": 7,
            "model_name": "baseline_naive",
            "mae": 0.0012,
            "rmse": 0.0023,
            "directional_accuracy": 0.5,
            "dm_p_holm": None,
            "verdict": "baseline (yardstick)",
            "beats_baseline": False,
        },
    ],
    "coverage": [
        {
            "pair_symbol": "EUR/USD",
            "target_horizon": 7,
            "method": "split_conformal[ml_ridge]",
            "nominal_level": 0.9,
            "empirical_coverage": 0.87,
            "mean_width": 0.0045,
            "n": 157,
        }
    ],
}


class TestReport:
    def test_report_contains_only_input_numbers(self):
        html = render_report(BOARD)
        # every reported number appears verbatim from the input
        assert "experiment-abc123" in html
        assert "۰.۰۰۱۲۳" in html  # mae with Persian digits
        assert "۰.۸۷" in html  # empirical coverage
        assert "۱۵۷" in html  # n
        # nothing invented: a number NOT in the input must not appear
        assert "۹۹.۹۹" not in html

    def test_report_honesty_labels(self):
        html = render_report(BOARD)
        assert "beats baseline, not significantly" in html  # verdict verbatim
        assert "baseline (yardstick)" in html
        assert "Educational and analytical use only. Not financial advice." in html
        assert "توصیه مالی" in html  # Persian disclaimer
        assert "purging" in html or "purge" in html
        assert "هولم" in html  # Holm correction mentioned

    def test_report_missing_sections_say_not_reported(self):
        html = render_report({"run_id": "x", "rows": [], "coverage": []})
        assert "گزارش نشده" in html
        assert "رتبه‌بندی" in html

    def test_report_is_print_friendly_rtl(self):
        html = render_report(BOARD)
        assert 'dir="rtl"' in html
        assert "@media print" in html
        assert "page-break" in html

    def test_report_escapes_html(self):
        board = json.loads(json.dumps(BOARD))
        board["rows"][0]["model_name"] = "<script>alert(1)</script>"
        html = render_report(board)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_report_via_api(self, client, tmp_path, monkeypatch):

        monkeypatch.setattr(
            "app.services.report.generator.load_board", lambda rid, base=None: BOARD
        )
        r = client.get("/api/v1/reports/latest")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "experiment-abc123" in r.text

    def test_report_404_unknown_run(self, client):
        r = client.get("/api/v1/reports/does-not-exist")
        assert r.status_code == 404
