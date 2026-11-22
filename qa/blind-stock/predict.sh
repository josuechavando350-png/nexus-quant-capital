#!/usr/bin/env bash
set -euo pipefail
# Usage: bash predict.sh PRODUCT_CHECKOUT QA_GIT_CHECKOUT OBSERVATIONS_JSON
product=$(realpath "$1")
repository=$(realpath "$2")
observations=$(realpath "$3")
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
hunter=066cf0876cc921b89c8a2f2229b39e9e1a2b3366
controls=2a0b1d7e97e8d43ab67ad65013018ef3af53e089
git -C "$product" archive "$hunter" superhunter/{__init__,bridge,balance_reconciliation,native_runtime,privacy,safe_io}.py | tar -x -C "$root"
git -C "$repository" archive "$controls" qa/metric-accounting/{report_fields,study,observe}.py | tar -x -C "$root"
runtime=$(python3.12 -I -c 'import sys; print(sys.base_prefix)')
script=$(realpath "$(dirname "$0")/predict.py")
unshare --user --map-current-user --net bwrap --unshare-pid --die-with-parent --clearenv \
  --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin \
  --ro-bind "$runtime" "$runtime" --dev /dev --tmpfs /tmp \
  --ro-bind "$root/superhunter" /hunter/superhunter --ro-bind "$root/qa/metric-accounting" /controls \
  --ro-bind "$observations" /data.json --ro-bind "$script" /predict.py \
  "$runtime/bin/python3.12" -IB /predict.py
