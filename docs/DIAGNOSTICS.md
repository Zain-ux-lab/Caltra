# Diary and diagnostic exports

Settings now shows Export diary and Export diagnostics directly. The existing
/api/export link remains compatible; /api/export?diagnostics=true adds recent
traces and model/analysis version metadata. Both downloads are private and use
Cache-Control: no-store.

This private single-user instance retains the most recent 200 diagnostic operations:
photo analysis (including initial resolved portions), correction requests and
results, standalone food/product searches, and saved meal snapshots. Source
selection candidates and product lookup warnings are recorded within operations.
Item IDs and timestamps connect observations to corrections and saved meals.
Raw photos, HTTP headers, API keys and raw provider errors are not recorded.
The export contains personal food descriptions; users should review it before sharing.
Clearing the diary also clears diagnostics. Saving a trace is best effort and
must not prevent a successful meal save. Old correction history cannot be recovered.
Manual edits are captured on meal save, not on every unsaved keystroke. Cached
photo results have no new search trace because no new lookup took place.

These records support debugging and evaluation, not automatic model training.
An exact product match still depends on available source records. Restaurant
menu coverage and photo portion accuracy remain limitations. Unknown nutrients
remain unknown; a brand name alone does not verify nutrient values.

Validation: `python -m unittest discover -s tests -p test_diagnostic_export.py -v`
uses temporary databases and synthetic records, directly invoking endpoint functions.
CI additionally runs pytest and the TypeScript/Vite build. No real diary or image
is included in the tests or repository.
