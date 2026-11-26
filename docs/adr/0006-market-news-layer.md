# ADR-0006: Gold/dollar market layer + news intelligence (addendum)

- **Status:** Accepted (2026-11-26)
- **Context:** The product addendum requires real gold/USD/Iran-market data
  (A), verified sourcing (B), a news pipeline (C), a drivers layer (D),
  dashboard views (E), honesty/safety rules (F) and tests (G). The build
  sandbox cannot reach any market/news host, so nothing can be verified live
  in this environment.

## Decisions

1. **Units:** one tested conversion utility (`app/services/units.py`).
   Canonical storage: RIAL for money, GRAMS for weight; toman (×10) and
   troy-ounce (×31.1035) are display/ingest units only. Every series carries
   an explicit `UnitSpec`; coins use fixed fine-gold content
   (Emami = 8.136 g gross at 900 fine = 7.3224 g fine gold).
2. **Derived series** (`app/services/markets/derived.py`) are formula-driven
   and unit-tested: implied global gram IRR = XAU/USD × USD/IRR ÷ 31.1035;
   coin bubble = market − intrinsic (abs + %); USD gap = (free−official)/
   official; cross-market deviations beyond a threshold raise **quality
   warnings and are never silently corrected**.
3. **Multi-source consensus:** median + MAD outlier rejection
   (`consensus.py`); per-source values and disagreement % are always
   exposed. With < 3 sources the small sample is stated instead of
   pretending robustness.
4. **Sourcing:** providers probe-capable (`probe()` in
   `scripts/verify_sources.py`) with capabilities/verified-live flags. In
   this build environment every remote source stays `verified_live=False`
   with status "unreachable/unverified" — recorded honestly in
   docs/DATA_SOURCES.md. **No scraping of sources that forbid it:** where no
   legitimate public API exists (several Iran trackers), the sanctioned path
   is CSV/Excel import + manual entry with provenance labels. Iran-market
   quotes are ALWAYS labelled unofficial market quotes.
5. **News:** RSS/Atom only, metadata + snippet + link-back (no full text
   where disallowed), ETag/If-Modified-Since, ≥15-min polls with exponential
   backoff, fail-soft. Point-in-time rule: `available_at = max(published,
   fetched)`; all aggregates are past-window only (negative-tested against
   leakage). Dedup/threading via deterministic shingle-Jaccard clustering.
   Topics: rules-first keyword lexicon. Sentiment: inspectable FA/EN lexicon
   baseline with model name+version persisted (`lexicon-fa-en/1`) — a
   transformer would live in the `full` profile and is out of scope here.
   Reliability tiers + rumor/unattributed flags; a single low-credibility
   source must not drive forecasts ("unconfirmed" labels in UI copy).
6. **News value:** with-news vs without-news walk-forward comparison with a
   Diebold-Mariano test on paired losses; verdict strings are honest ("no
   significant difference — news kept as context only" is a valid, expected
   result). News is only allowed in a champion model if the test says it
   helps; otherwise contextual only.
7. **Iran calendar:** Tehran UTC+3:30, weekend Thu/Fri (configurable), fixed
   Jalali holidays computed; lunar (Islamic) holidays live in a curated JSON
   file with honest coverage reporting (they cannot be computed offline).
   Timestamps stored UTC; displayed Jalali + Gregorian.
8. **Demo mode** for all new instruments: deterministic, mutually
   consistent with the derived formulas, and badged `is_demo` everywhere;
   cached/demo is never shown as live (data timestamp + age + "stale" shown).

## Consequences

- Real history depth per series depends on what the user's networked machine
  verifies via `scripts/verify_sources.py`; until then all new series show
  demo/unverified state honestly.
- The DM news-value test runs on real forecast losses when experiments run
  with news features; the demo verdict panel is clearly marked demo.
