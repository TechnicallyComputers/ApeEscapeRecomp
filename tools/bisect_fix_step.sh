#!/usr/bin/env bash
# git bisect run script: find the master commit that FIXED the Ape memcard hang.
# exit 0 = fixed (PASS), 1 = broken (FAIL), 125 = skip (inconclusive/build error)
set -u
ROOT=/home/alex/Documents/GitHub/ApeEscapeRecomp
cd "$ROOT/psxrecomp-v4" || exit 125
rev=$(git rev-parse --short HEAD)
git submodule update --init lib/recomp-net >/dev/null 2>&1
git apply "$ROOT/tools/patches/ape_bisect_dualshock_inject.patch" >/dev/null 2>&1 || true
cd "$ROOT" || exit 125
if ! cmake --build build-bisect --target ApeEscapeRecomp -j8 > "/tmp/ape_fixbisect_build_$rev.log" 2>&1; then
    echo "BISECT $rev BUILD_FAIL" >> /tmp/ape_fixbisect.log
    git -C psxrecomp-v4 checkout -- . 2>/dev/null
    exit 125
fi
pkill -x ApeEscapeRecomp 2>/dev/null; sleep 0.5
APE_MEMCARD_FAST=1 python3 tools/ape_memcard_loadtest.py \
    "$ROOT/build-bisect/ApeEscapeRecomp" "$ROOT/game.toml" 4488 \
    > "/tmp/ape_fixbisect_test_$rev.log" 2>&1
rc=$?
pkill -x ApeEscapeRecomp 2>/dev/null
git -C psxrecomp-v4 checkout -- . 2>/dev/null
echo "BISECT $rev test_rc=$rc" >> /tmp/ape_fixbisect.log
case $rc in
    0) exit 0 ;;   # PASS -> fixed
    2) exit 1 ;;   # FAIL -> broken
    *) exit 125 ;; # inconclusive / launch error -> skip
esac
