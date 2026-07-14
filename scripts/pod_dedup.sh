#!/usr/bin/env bash
# Batch-pod runner: launch via
#   /opt/launch-sh/bin/launch-scipy-ml.sh -W RITS_HDSI_PRISMDATA -c 4 -m 8 -p low -f -- bash ~/private/Chef_LLM/scripts/pod_dedup.sh
# Inside pods, pod-$HOME is the shared workspace volume (10G, group's quota):
# the repo lives on the REAL home, mounted at ~/private. pip targets /scratch
# (node-local, ephemeral) so nothing lands on the workspace volume.
set -euo pipefail
cd ~/private/Chef_LLM
pip install -q --no-warn-script-location --target /scratch/pylibs datasketch
export PYTHONPATH=/scratch/pylibs
python -m etl.dedup data/corpus/foodcom.parquet
python -m etl.report data/corpus/foodcom.parquet
