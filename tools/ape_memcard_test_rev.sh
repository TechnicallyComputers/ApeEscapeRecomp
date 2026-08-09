#!/usr/bin/env bash
# Checkout one psxrecomp-v4 rev, rebuild, run memcard oracle.
# Prints GOOD/BAD/SKIP and exits 0/1/125.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REV="${1:?usage: ape_memcard_test_rev.sh <rev>}"
BUILD="${APE_BISECT_BUILD:-$ROOT/build-bisect}"
EXE="$BUILD/ApeEscapeRecomp"
PORT="${APE_BISECT_PORT:-4488}"
LOG="$BUILD/bisect_step.log"

cd "$ROOT/psxrecomp-v4" || exit 125
git checkout "$REV" --force >>"$LOG" 2>&1 || exit 125
git submodule update --init lib/recomp-net >>"$LOG" 2>&1 || true
RECOMP_NET="${RECOMP_NET_ROOT:-$ROOT/psxrecomp-v4/lib/recomp-net}"
rev=$(git rev-parse --short HEAD)
echo "=== test rev $rev ===" | tee -a "$LOG"

PATCH="$ROOT/tools/patches/ape_bisect_dualshock_inject.patch"
if [[ -f "$PATCH" ]]; then
  git checkout -- runtime/src/main.cpp 2>/dev/null || true
  if git apply --check "$PATCH" >>"$LOG" 2>&1; then
    git apply "$PATCH" >>"$LOG" 2>&1 || true
    echo "applied DualShock inject patch" | tee -a "$LOG"
  else
    echo "DualShock inject patch skipped" | tee -a "$LOG"
  fi
fi

if ! cmake "$ROOT" -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DPSX_NETPLAY=ON -DRECOMP_NET_ROOT="$RECOMP_NET" \
      -DPSX_DEBUG_TOOLS=ON -DAPE_BISECT_WEAK_STUBS=ON \
      -B "$BUILD" >>"$LOG" 2>&1; then
  echo "CMAKE FAIL $rev"; exit 125
fi
JOBS="${APE_BISECT_JOBS:-1}"
if ! cmake --build "$BUILD" --target ApeEscapeRecomp -j"$JOBS" >>"$LOG" 2>&1; then
  echo "BUILD FAIL $rev"; exit 125
fi

pkill -x ApeEscapeRecomp 2>/dev/null || true
sleep 0.3
export APE_DISC="${APE_DISC:-/mnt/crucial4tb/Emulation/roms/ps/Ape Escape (USA)/Ape Escape (USA).cue}"
cat >"$BUILD/settings.toml" <<EOF
[video]
renderer = "software"
bios_hle = true
turbo_loads = true
auto_skip_fmv = true
supersampling = 1
[launcher]
skip_launcher = true
[disc]
path = "$APE_DISC"
[memcard]
dir = "$ROOT/saves"
card1 = "/mnt/crucial4tb/Emulation/saves/ps/card1.mcd"
card2 = "$ROOT/saves/card2.mcd"
enable1 = true
enable2 = true
[controller]
p1_device = "auto"
p1_mode = "analog"
p2_device = "none"
EOF

export APE_MEMCARD_FAST="${APE_MEMCARD_FAST:-1}"

for try in 1 2 3; do
  set +e
  python3 "$ROOT/tools/ape_memcard_loadtest.py" "$EXE" "$ROOT/game.toml" "$PORT"
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then echo "GOOD $rev"; exit 0; fi
  if [[ $rc -eq 2 ]]; then echo "BAD $rev"; exit 1; fi
  echo "inconclusive try $try rc=$rc"
  pkill -x ApeEscapeRecomp 2>/dev/null || true
  sleep 1
done
echo "SKIP $rev"
exit 125
