# Caltra

**Photo-first nutrition tracking, with a focus on UK foods.**

Caltra is an early-stage nutrition tracker: photograph a meal, add what the camera cannot see, review the estimated foods and portions, and log them to your daily diary. It combines Gemini image analysis with UK food records, saved product labels and deterministic nutrient calculations.

It runs locally on your own machine, or as a private single-user deployment behind a password (see [docs/FREE_CLOUD_SETUP.md](docs/FREE_CLOUD_SETUP.md)). It isn't a public multi-user service, and there's no native mobile app.

## Why I built it and what I contributed

I wanted a food diary that lets me correct what a photo cannot reliably tell:
the food identity, portion, hidden ingredients and product used. I shaped the
photo-review workflow around that problem and worked on the Python API,
source matching, quantity correction, diary and reliability checks, with
AI-assisted development and tests. The UI is built with React and TypeScript;
this is project experience, not a claim that I wrote every line unaided.

The key decision is to keep food identification separate from nutrient
arithmetic: the app matches a reviewed food to a source record, then calculates
nutrients from the reviewed amount. Missing nutrient data stays unknown unless
a labelled generic estimate is available (see below).
See [estimation](backend/estimation.py), [photo analysis](backend/vision.py)
and the [tests](tests/) for the implementation. Portion accuracy remains an
open problem, so this is a working prototype rather than a validated
nutrition tool.

## What it does

- **Photo + context:** upload a photo and optionally describe hidden ingredients. Caltra inventories the pictured meal automatically, including possible shared foods with estimated amounts. A side photo and product-default controls are optional. Review, halve or remove foods afterward; different foods on the same plate remain separate entries when identified.
- **Manual food logging:** search UK foods or products, or scan a barcode, without a photo; select a supplied serving or enter grams/ml, preview macros and add multiple foods to a meal.
- **Editable food breakdown:** review each food, portion, source and macro estimate; halve one food or the whole meal, answer optional follow-up questions and undo AI corrections.
- **Hidden extras:** one tap adds cooking oil, butter, milk, sugar or honey in spoon or splash measures, using your usual product for that ingredient if you've saved one.
- **Your usual portions:** once you've entered your own amount for a food at least twice, later photo estimates for that food start from the median of your last five amounts. Accepting that suggestion doesn't count as a new entry, so it can't reinforce itself.
- **UK food lookup:** UK CoFID generic foods, UK-market Open Food Facts product records and 2,185 restaurant records with official per-serving nutrition from nine UK chains (Greggs, PizzaExpress, Popeyes, Nando's, KFC, McDonald's, Pret, Subway and Caffè Nero; see [the catalogue notes](docs/RESTAURANT-CATALOGUE.md)), with barcode scanning (photo of the barcode) and manual label entry.
- **Restaurants Caltra doesn't hold:** when a search finds no exact match, a "Not on Caltra?" panel links to the chain's official nutrition page (13 UK chains, checked by hand) and a Google search, then lets you enter one menu serving yourself. Your entry is saved, so the same search finds it next time.
- **Your usual products:** save specific products for compatible ingredients in homemade meals.
- **Daily diary:** calories, protein, carbohydrate and fat remaining against your saved targets; foods grouped by breakfast, lunch, dinner and snacks for a selected date.
- **Nutrient details:** fibre, vitamins and minerals where source data is available. When a product record has no vitamin or mineral values, Caltra fills them from the closest generic UK CoFID food and marks them as estimates. Anything still missing is shown as unknown, and partial totals are marked.
- **Target setup:** a local starting-target calculator, optional Gemini explanation, and editable targets that require your review before saving.
- **Remembered meals:** reuse a saved meal without another image-analysis request.

## Screenshots

Screenshots use fictional demonstration entries, not a personal food diary.

![Caltra daily diary](docs/images/diary-desktop.png)

## Getting started

Use Python 3.12 and Node.js 20+ with pnpm.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
pnpm install --frozen-lockfile
pnpm build
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [localhost:8000](http://127.0.0.1:8000). On macOS, `start.command` can launch the app after setup.

1. Open **Targets** and calculate or enter your daily targets.
2. To enable photo analysis, connect your own Gemini key in **Settings**. Alternatively copy `.env.example` to `.env` and set the key there.
3. Add your usual UK products in **Settings → My usual products**.
4. Choose **Log food**, select a meal/date, then either take a photo or choose **Search foods**. Review portions and save the meal to your diary.

Basic diary, source search and nutrient arithmetic can work without Gemini. Photo recognition and AI help require an accessible configured model. The sample model name reflects the development configuration; replace it if your Google project does not support it. Google API quotas and pricing apply separately. Caltra does not enable billing for you.

The complete legacy development environment in `requirements.txt` includes optional ML experiment dependencies. They are unnecessary for the current app; use `requirements-app.txt` for the smaller installation.

## How estimates work

```text
Photo + your description
        ↓
Gemini identifies foods and proposes rough portions
        ↓
UK food/product records are retrieved and matched
        ↓
Source nutrients × reviewed amount → meal and daily totals
```

The source-selection stage chooses existing records; it cannot edit their nutrient values. When no suitable record is found, a separate Gemini call can propose clearly labelled, unverified nutrition estimates. Food corrections trigger matching and recalculation. A photograph cannot reliably reveal ingredient amounts, added oil or hidden components, so the review step matters.

There is no demonstrated 90% accuracy guarantee or validated accuracy advantage over commercial trackers. The current weak point is portion estimation. Repeatable output and passing software tests do not establish nutritional accuracy.

## Tests

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
GEMINI_API_KEY='' .venv/bin/python -m pytest -q
pnpm build
```

With the app running, the current browser flows can be checked with:

```sh
node tests/manual-search-browser.cjs
node tests/daily-diary-browser.cjs
node tests/plated-pieces-browser.cjs
```

These browser scripts currently expect Google Chrome at its standard macOS installation path. They mock analysis/diary requests where specified and do not upload private photos. Older browser scripts reflect earlier UI versions. Historical parser tests explicitly use bundled legacy USDA fixtures; production nutrition lookup remains UK-only.

## Privacy and deployment

Caltra has two modes, chosen by environment variables in [backend/access.py](backend/access.py) and [backend/store.py](backend/store.py):

- **Local (default):** the server only answers requests to `localhost`. Meals, remembered meals, usual products and cached analysis results go in a SQLite file in the project folder. The Gemini key lives in `.env` or `~/.config/caltra/.env`.
- **Private cloud beta:** set `CALTRA_PUBLIC_ORIGIN`, `CALTRA_ACCESS_PASSWORD` and `CALTRA_DATABASE_URL`. Every request except the health check and app icons needs the shared password (HTTP Basic auth), writes from other origins are rejected, and data goes in PostgreSQL. Set `GEMINI_API_KEY` in the hosting dashboard. The Settings key form is hidden in this mode and the API refuses to save keys, because the container's filesystem doesn't survive a restart.

In both modes:

- It's one diary for one person. There are no user accounts and no per-user data isolation, so don't share the password. Separate accounts are needed before more than one person can use it.
- Photo analyses are cached by fingerprint. The original image bytes aren't stored.
- Uploaded images and requested AI context go to Google. UK branded-food searches send search terms to Open Food Facts. Saving a meal can send product names to Google so it can pick a generic food for missing vitamins. The restaurant and Google links only open in your own browser when you tap them; Caltra itself sends nothing to those sites. The barcode reader's WebAssembly file is downloaded from the jsDelivr CDN on your first scan; the photo itself stays in your browser. Check provider terms before submitting anything sensitive.
- Corrections update the saved meal and show up in diagnostic exports. They don't train or change the model.
- Keys, food images, databases, evaluation outputs and downloaded weights are kept out of Git.

## Technology

React 19 · TypeScript · Vite · FastAPI · Pydantic · SQLite / PostgreSQL · Gemini API

Portion-estimation research code is retained under `experiments/`; its downloaded datasets, weights and results are excluded. Those experiments are not a trained production model used by the current photo flow.

## Data and attribution

- **UK CoFID 2021**, Public Health England, [official dataset and user guide](https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid), contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). The bundled normalized data includes macro and available micronutrient values. `scripts/import_cofid.py` imports the official workbook.
- **Open Food Facts**, [database and licensing](https://world.openfoodfacts.org/terms-of-use): UK-market community product records queried at runtime, subject to ODbL and applicable content/image licences. Product completeness and correctness vary. No Open Food Facts product-image collection is bundled.
- **USDA FoodData Central**, [dataset downloads](https://fdc.nal.usda.gov/download-datasets/): legacy public-domain parser/test fixtures only, excluded from production UK lookup.
- **Mifflin–St Jeor**, [original equation paper](https://pubmed.ncbi.nlm.nih.gov/2305711/): starting estimate of resting energy for the target calculator. Activity and macro-split defaults remain editable estimates.

Third-party data and dependencies retain their own terms. No blanket open-source licence has been selected for Caltra's application code yet.

## Dietary patterns and data coverage

The Nutrients tab includes 3-day and 7-day reviews ending on the selected diary date. Optionally mark days as finished logging. A recurring low-intake flag needs at least three complete days with full data coverage for that nutrient; missing dates and missing nutrient values never count as zero. Initial food suggestions use general adult NHS references for fibre, calcium and vitamin C. Other nutrients show recorded averages where available, without personalised deficiency claims. This is an in-app review, not a background notification service or clinical assessment.

Vitamins and minerals missing from a product label or AI estimate are filled when you save the meal. CoFID search makes a shortlist of generic foods, Gemini picks the closest one or none (protein powders and soft drinks usually get none), and the values are copied from that CoFID record. Gemini never writes nutrient values itself. Each filled value is marked in the diary with the CoFID food it came from, and the dietary review says when its averages include estimates. The choice is remembered per product, so each product is only asked about once. Label values are never overwritten, per-serving records are skipped, and without a Gemini key values stay unknown. For meals logged before estimates existed, **Settings → Fill missing vitamins** fills the same gaps across your diary in one go. Logged calories and macros aren't touched. Exact plain UK ingredient aliases can use CoFID references when source selection finds no match; product labels and composite recipes are not silently replaced with generic ingredients. Historical meal snapshots are preserved.

Photo analysis makes no automatic retry. Incomplete provider replies, timeouts and service failures have separate messages; descriptive metadata is bounded without relaxing nutrition or quantity validation. Corrections that change an AI-estimated food's identity or preparation no longer reuse its old calorie density. Portion accuracy remains limited by image evidence.
