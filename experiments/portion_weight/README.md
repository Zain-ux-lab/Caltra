# Experimental supervised portion model

This is a completed local research pilot, separate from Caltra. **Do not deploy this checkpoint: it performed worse than its baseline on the held-out test.** No private meal photos or paid APIs were used.

## Actual result — 20 October 2026

| Held-out test metric | Training-food median baseline | Trained model |
| --- | ---: | ---: |
| Mean absolute ingredient-weight error | 16.65 g | 17.87 g |
| Ingredient error for portions at least 10 g | 35.37 g | 39.42 g |
| Ingredient absolute error / total true weight (WAPE) | 58.08% | 62.33% |
| Mean absolute total-meal-weight error | 72.32 g | 76.37 g |
| Signed total-meal-weight bias | -22.04 g | -24.50 g |

Test: **160 dishes, 1,054 ingredient portions**, including three food identities unseen in training. Negative bias means underestimation. These results do not support a universal 10% downward adjustment to Caltra's current guesses; this is a different estimator and dataset.

Validation ingredient MAE improved from 19.86 g to 18.64 g. The selected checkpoint was epoch 24; early stopping ended at epoch 54. That improvement did not carry over to the untouched official test subset. We have not tuned another model against these test results.

Small ingredients dominate the ingredient count: only 426 test portions weighed at least 10 g. Accordingly, the all-ingredient average alone understates errors on substantial foods. WAPE is an aggregate error measure, not an accuracy percentage. Total-meal errors may hide cancelling ingredient errors. No calorie or macro accuracy was measured.

## What was trained

- Frozen ImageNet-pretrained ResNet18, with a small trainable ingredient embedding and weight-prediction head. This is transfer learning, not Gemini fine-tuning or training an entire vision model from scratch.
- Inputs: an overhead RGB plate image and the **correct ingredient identity supplied by the dataset**. Targets: measured grams per ingredient. No calorie values, test weights, depth images or side views are model inputs.
- Baseline: median grams for each food, computed only from training dishes, with a training-only median fallback for unknown foods.
- 600 training dishes / 4,525 ingredient portions; 120 validation dishes / 773 portions. Validation capture days are excluded from training. Test IDs come from the dataset's official held-out split, which keeps incremental scans of a plate within the same official split.
- Vocabulary, baseline weights and feature normalization use training rows only. Validation selects the checkpoint; test evaluation follows selection.

The dataset provides known food identities, making this an easier task than Caltra faces. Whole-image features do not localize each food. There is also no trained ingredient-only control, so even an improvement over medians would not establish that visual information caused it.

## Data and provenance

[Nutrition5k](https://github.com/google-research-datasets/Nutrition5k), Google Research dataset authors, CC BY 4.0. It contains measured cafeteria meals in a particular capture environment; it is not a representative UK home-cooking benchmark. We selected 880 available overhead images rather than downloading its 181 GB archive. Invalid/inconsistent metadata and unavailable RGB files are excluded before deterministic split sampling. Exact IDs, exclusions, metadata hashes and saved-image hashes are in `results/manifest.json`. Images are converted to RGB JPEG at quality 95, capped at 640 pixels.

Encoder: [Microsoft ResNet18](https://huggingface.co/microsoft/resnet-18), Apache 2.0, pinned revision `65a5785d9156231087c481e0c7dd33a5ff6f7e3e`. Features are frozen. Seeds are fixed at 42; CPU runtime and dependency differences can still affect numerical reproducibility.

## Re-run and inspect

From the Caltra project root, using its existing Python environment:

```sh
PYTHONPATH=. .venv/bin/python -m experiments.portion_weight.run
PYTHONPATH=. .venv/bin/python -m pytest tests/test_portion_training.py -q
```

Requires the project's installed torch, transformers, safetensors, numpy, Pillow and httpx. Initial runs require internet for public metadata, selected images and the pinned encoder; later runs reuse local artifacts. Nothing is imported by the production app.

Outputs:

- `results/metrics.json`: full metrics and validation history.
- `results/test-predictions.csv`: individual food predictions and measured targets.
- `results/test-dish-predictions.json`: summed meal predictions.
- `results/manifest.json`: exact split and provenance.
- `models/portion-head.safetensors` and `models/portion-model.json`: experimental weights, priors, vocabulary and normalization.

## Next experiment

Keep this result as a failed baseline experiment. A stronger study would localize individual foods, include a trained food-only control, and train/evaluate paired overhead and angled views against measured weights. A separate UK/home-meal test set is needed before deployment. Ground-truth measurements are needed when building and validating a model; that does not require app users to weigh every meal. A second photo may add shape information but cannot reveal hidden oil or uniquely determine weight without scale and density assumptions.
