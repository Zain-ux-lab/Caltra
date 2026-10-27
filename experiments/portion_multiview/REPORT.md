# Paired-photo training results — 21 October 2026

**Outcome: no meaningful second-photo benefit in this pilot. Do not deploy these checkpoints.**

All four models completed local supervised training. We reused frozen ResNet18 features and a frozen OWL-ViT region detector, training only small portion-regression heads. No private photos or paid inference APIs were used. The full run took 559.6 seconds (about 9 minutes 20 seconds), excluding initial detector download/probing.

## Held-out results

All comparisons below use the same **128 retained official-test dishes / 956 ingredient portions**. Each model receives the correct ingredient identities. Values are mean absolute errors, so lower is better.

| Method | Ingredient error | Error for ingredients >=10 g | Total-meal-weight error |
| --- | ---: | ---: | ---: |
| Food-specific median baseline | 14.93 g | 34.96 g | 81.44 g |
| Trained food-only control | 14.97 g | 34.51 g | 81.44 g |
| One overhead photo | 14.48 g | 34.05 g | 75.38 g |
| Overhead + angled photo | 14.48 g | 34.80 g | 76.47 g |
| Two-view food crops + box geometry | 14.60 g | 34.40 g | 73.42 g |
| Previous experiment checkpoint | 16.39 g | 38.46 g | 91.24 g |

The one-photo and two-photo models have essentially identical ingredient errors (difference **0.0048 g**, about 0.03%). The two-photo model is slightly worse on larger ingredients and whole-meal error. The crop/geometry variant has the lowest total-meal error, but is worse than the one-photo model on the primary ingredient metric; cancelling ingredient errors can improve totals without improving individual foods.

The new one-photo model performs better than the previous checkpoint on these same meals. This comparison also changes the loss function, training membership and input architecture. It cannot be credited to a second view. Against the matched median baseline, its ingredient MAE improvement is only about 3%.

## Uncertainty

Positive reduction means the candidate has lower ingredient MAE. These are exploratory 95% bootstrap intervals, resampling **44 capture-day clusters**, not treating all ingredients as independent. Every interval includes zero. Multiple comparisons, incremental scans and the small dataset further limit inference.

| Candidate vs reference | MAE reduction | Exploratory 95% interval |
| --- | ---: | ---: |
| One overhead photo vs Trained food-only control | 0.488 g | -0.194 to 1.365 g |
| Overhead + angled photo vs One overhead photo | 0.005 g | -0.776 to 0.737 g |
| Two-view food crops + box geometry vs Overhead + angled photo | -0.126 g | -1.153 to 0.934 g |
| Two-view food crops + box geometry vs Food-specific median baseline | 0.324 g | -0.769 to 1.439 g |

## Localization and failure cases

The detector accepted a region for **35.7%** of overhead ingredient queries and **32.6%** of angled-view queries. Other queries use the entire image. Acceptance is not verified detection accuracy. Manual inspection of fixed training examples showed some accepted boxes covering much of the plate rather than isolating the requested food. Hidden oil and seasonings are not visually resolved.

There were six test ingredient portions with identities absent from training; their predictions use a training-only median fallback. For example, a 228 g tuna-salad portion was predicted as about 5 g. One 570 g egg-white portion was predicted as about 247 g by the one-photo model. Those errors are too large for a dependable nutrition logger.

Only 348 of the 956 test portions weighed at least10g. The overall average is dominated by many tiny seasonings; the larger-food error of around34g better exposes the remaining practical limitation. Calories and macros were not evaluated.

## Training and data checks

- Initially selected600 train /120 validation /160 new official-test dishIDs.149 lacked cameraA footage; retained520 train /83 validation /128 test dishes. All controls use the same retained data. These missing frames introduce availability bias.
- Retained ingredient targets:4193 train /705 validation /956 test.
- Train-only food vocabulary, portion medians and feature normalization. Validation capture days are excluded from training. Each checkpoint is selected using validation MAE, and all four checkpoints are saved before test evaluation.
- Test dishIDs were excluded from the first evaluation. However, separate incremental scans of the same underlying plate may appear in both historical and new test subsets; these subsets are not guaranteed plate-independent. All remain in the official test split and outside the official training pool.
- Four matched heads use seed42, identical head dimensions, gram-space smoothL1 loss, maximum200epochs and early stopping. The saved checkpoints were reloaded for evaluation.
- The entire Python test suite passed:82 tests, with one existing FastAPI/Starlette deprecation warning. A read-only code review found no important leakage or implementation defect.

| Model | Validation-selected epoch | Validation ingredient MAE |
| --- | ---: | ---: |
| Trained food-only control | 45 | 17.51 g |
| One overhead photo | 9 | 16.10 g |
| Overhead + angled photo | 22 | 16.01 g |
| Two-view food crops + box geometry | 31 | 15.95 g |

## Implication for Caltra

This run does not justify asking users for a second photo as an accuracy requirement, or replacing the production estimator with these checkpoints. It also does not disprove multi-view learning in general: this small model uses a controlled rig, weak region proposals and relatively few training meals.

Before another training run, the useful improvement would be better ingredient-region supervision and an independent, measured home-meal benchmark. Evaluating a modern depth/multi-view approach is a separate experiment; this run did not reconstruct3D food volume. User corrections to ingredients and portions remain more actionable than claiming the photo model is now calibrated.

## Artifacts and provenance

- [Fixed pre-evaluation protocol](PROTOCOL.md)
- [Full metrics](results/metrics.json), [per-food predictions](results/test-predictions.csv), [exact IDs and image hashes](results/manifest.json).
- Saved checkpoints and training statistics in `models/`; no production code imports this experiment.
- [Nutrition5k](https://github.com/google-research-datasets/Nutrition5k), Google Research dataset authors, CC BY4.0. [Google OWL-ViT](https://huggingface.co/google/owlvit-base-patch32) and [Microsoft ResNet18](https://huggingface.co/microsoft/resnet-18), Apache2.0. Pinned revisions and source details are in the manifest and README.

Initial public-image retrieval transferred445.9MB. Side images came from bounded video prefixes, not the full181GB archive. Only the first frame of cameraA was used; no depth, other cameras or best-frame selection. A controlled cafeteria rig does not demonstrate accuracy for UK food, unknown products or phone photos.
