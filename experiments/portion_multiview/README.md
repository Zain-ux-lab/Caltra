# Paired-view portion training pilot

This experiment is separate from Caltra's production estimator. It uses public Nutrition5k photos and local open-source models; no private user images or paid model APIs are used.

The pre-evaluation choices are recorded in [PROTOCOL.md](PROTOCOL.md). Completed: **the second photo did not meaningfully improve ingredient-weight error.** See [REPORT.md](REPORT.md). Actual results are in `results/metrics.json`, with per-food predictions in `results/test-predictions.csv` and saved checkpoints in `models/`.

## Run

From the Caltra project root, after preparing the first portion experiment:

```sh
PYTHONPATH=. .venv/bin/python -m experiments.portion_multiview.run
PYTHONPATH=. .venv/bin/python -m pytest -q
```

Uses the existing torch/transformers/Pillow/httpx/numpy/safetensors environment and `ffmpeg` executable. The pinned OWL-ViT weights must be available in `../portion_weight/models/detector/`; the probe for this experiment downloaded them there. The first experiment supplies the pinned ResNet18 weights, metadata and original split. Models are loaded locally without contacting an inference service. Initial public-image retrieval requires internet access. Re-runs reuse images and feature caches; changing pipeline source invalidates the feature cache. Checkpoint selection is deterministic with seed42, although CPU/MPS/runtime differences can cause numerical variation.

## Interpretation

- All variants receive correct ingredient identities, including ingredients a photo cannot reveal. This tests weight estimation with oracle identities, not the full recognition/database pipeline.
- Localization uses predicted text-conditioned bounding boxes, not verified ingredient masks. Missing/low-confidence boxes fall back to the full image. Coverage is acceptance rate, not detection accuracy.
- The localized variant adds both crops and normalized box coordinates/fallback indicators. It cannot isolate crops from geometry.
- Four new variants share the regression architecture, training procedure and retained meals. Comparison with the previous checkpoint also changes loss/objective, so an old/new improvement alone would not establish a second-photo benefit.
- The new test uses previously unevaluated dish IDs from the official test split. Different incremental scans of the same underlying plate may occur in the earlier and current test subsets. These subsets are therefore not guaranteed independent at plate level. Neither test subset is used in training; the official split keeps related plates out of the official training pool.
- A first frame from a controlled camera rig is not equivalent to a casual phone photo. This experiment does not establish UK/home-cooking accuracy or macro accuracy.
- Test comparisons use capture-day bootstrap intervals as exploratory uncertainty estimates. Multiple comparisons and a modest sample limit conclusions. A lower average error does not imply every meal improves.

## Sources and attribution

[Nutrition5k](https://github.com/google-research-datasets/Nutrition5k), Thames et al., Google Research dataset authors, CC BY4.0. Only selected overhead images and bounded prefixes of cameraA videos are fetched; the 181GB archive is not needed. Images are resized to at most640pixels and saved as JPEG quality95. The manifest records hashes, retained IDs and missing side frames.

[Google OWL-ViT](https://huggingface.co/google/owlvit-base-patch32), Apache2.0, pinned revision `cbc355fb364588351c5d51c7f74465e8e7ec6f72`, provides frozen open-vocabulary region proposals. [Microsoft ResNet18](https://huggingface.co/microsoft/resnet-18), Apache2.0, revision `65a5785d9156231087c481e0c7dd33a5ff6f7e3e`, provides frozen image features. Only the portion-regression heads are trained here.
