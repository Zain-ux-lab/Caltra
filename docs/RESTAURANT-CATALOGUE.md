# Shared UK restaurant catalogue

The application now seeds 1,068 official menu records for every installation: 268 Greggs, 466 PizzaExpress, 196 Popeyes and 138 Nando's. No paid data service is used. Open Food Facts remains the live UK supermarket lookup; CoFID remains the generic food source. This is a substantial restaurant expansion, not MyFitnessPal-level coverage or automatic model training.

## Source and portion rules

`data/restaurant-sources.json` records official URLs, retrieval dates, versions and regional scope. `data/restaurant-rows/*.csv` contains factual item names and published nutrient values. `python scripts/import_restaurants.py` validates these rows and reproducibly builds `data/uk-restaurants.json`, which is included in the Docker image and upserted at startup. Existing diary snapshots are unchanged.

Restaurant nutrients are **per menu serving**, not per 100 g. `nutritionBasis=serving` means the legacy `Item.grams` field stores the number of servings: 1 is the complete named item, 0.5 half, 0.125 one eighth. Both frontend and backend calculations use divisor 1; g/ml records still use divisor 100. Export consumers must read nutritionBasis. No restaurant serving weights are fabricated. A correction carrying grams cannot silently reuse those grams as serving counts. For a pizza slice, select the correct pizza variant and enter the fraction of the whole pizza eaten.

Search normalizes Pizza Express/PizzaExpress and apostrophes. Explicit restaurant searches stay within that brand. A query ending in meal/combo can offer matching individual items, with a warning to add the chosen sides and drink separately. Matching local restaurant searches do not wait on Open Food Facts. Restaurant records are excluded from supermarket default ingredient selection.

Published fibre, sugars, saturates and salt populate the same-day nutrient view. Unpublished vitamins and minerals remain unknown. Source links and scope notes appear with each item. Nando's records explicitly warn about excluded spices, platter sides, cream, gelado and refills where applicable.

## Import review, exclusions and maintenance

- Greggs: September 2026 official guide; all 268 numeric product rows. Per-serving columns avoid the guide's combined g/ml weight heading.
- PizzaExpress: September 2026 England/Wales/Scotland guide. Classic, Romana, Large Classic, gluten-free, vegan, Piccolo and airport categories stay distinct. Wrapped item names were joined. Two conflicting Classic Garlic Prawn rows and an incomplete Oasis row were excluded. The guide excludes special menus at Brixton, Finsbury Park and Earl's Court; Northern Ireland has a separate guide.
- Popeyes: live public UK nutrition table retrieved 1 November 2026, 201 rows. Five explicitly Ireland-only rows were excluded. Names were whitespace-normalized. The public table's JSON is at `https://app-allergenplatform-prod-westeurope-001.azurewebsites.net/api/recipes/get-information?pagination[page]=0&pagination[pageSize]=500&allergens=false&nutrition=true`; follow its `pages` count. Only public nutrition-table fields are used, without authentication.
- Nando's: general UK menu build 1793104315519, 128 menu items; one configurable starter selection has no complete nutrients and is omitted. Eleven two-size sides produce separate regular/large rows. Regional pricing trials are excluded. Milligram nutrient fields are converted to grams. The public page data is linked by the official menu app script. Base-dish values exclude customisations; sharing portions are not divided by the advertised number of people.

Update the reviewed CSVs and source manifest together, run the importer, then the full checks before deploying. The source-availability workflow can check the official links without modifying the live catalogue. Newly discovered or changed menu data still needs review; availability checks do not establish unchanged recipes. User corrections do not automatically become shared facts or retrain the model. Daily diary exports are not required to use this catalogue.

Validation includes published serving values, half portions, mixed g/serving meals, source boundaries, both reported Popeyes searches, restaurant variants, database seeding and a mobile browser test against the real application for search → save → today's nutrients → reload.
