# Earth Engine scripts and reproducible probes

Executable Earth Engine JavaScript and task-specific Python cloud/probe drivers
live under this top-level `gee/` directory. Raster/NPY fixtures, download payloads,
QA results, task records and data provenance remain under `data/pantanal_covariates/`.
Shared Python library/CLI implementation remains under `jaguar_irl/training/`.

The existing immutable SRTM jobs bundle is `spring_srtm_roughness_v1/jobs/`.
It moved intact, so its original plan/script hashes remain valid. The configured
published script is `spring_srtm_roughness_v1/cloud_scripts/extract_roughness.js`;
its publication metadata remains with the data under `cloud_scripts/publication.json`.

Active probe scripts resolve the repository and associated data directory from
their location. Run Python probes from the repository root with the isolated EE
environment and `PYTHONPATH="$PWD"`. They are cloud computations except for the
explicit offline verifier. Historical access probes are audit tools, not approved
production extraction recipes. Some scripts may write outputs or stage data;
read their descriptions before running. No probes were re-run in the layout move.

To verify the completed roughness data without cloud access:

```bash
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python \
  gee/spring_srtm_roughness_v1/cloud_scripts/verify_outputs.py
```

The verifier writes `verification_after_script_move.json` and preserves the
original historical `verification.json`. Cloud acquisition reruns use existing
ledgers rather than automatically resubmitting completed tasks.

`_historical/20261103/` preserves exact pre-move Python source bytes for provenance.
Those archived sources retain obsolete paths and are not the runnable entry points.
The relocation map, original/current hashes and archive locations are recorded in
`data/pantanal_covariates/script_migration.json`. Historical JSON manifests keep
their original meanings; consult the migration map for current code locations.
