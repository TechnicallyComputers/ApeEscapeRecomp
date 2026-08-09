#!/usr/bin/env bash
# git bisect run helper — cwd must be psxrecomp-v4.
# Exit: 0=good (memcard PASS), 1=bad (FAIL), 125=skip (build/inconclusive).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${APE_BISECT_BUILD:-$ROOT/build-bisect}"
EXE="$BUILD/ApeEscapeRecomp"
PORT="${APE_BISECT_PORT:-4488}"
LOG="$BUILD/bisect_step.log"

cd "$ROOT/psxrecomp-v4" || exit 125
rev=$(git rev-parse --short HEAD)
echo "=== bisect step $rev ===" | tee -a "$LOG"

# Always drop DualShock inject before exiting so `git bisect` can checkout.
cleanup_tree() {
  git checkout -- runtime/src/main.cpp 2>/dev/null || true
}
trap cleanup_tree EXIT

# Headless DualShock injection (kind==0 → p.mode + D-pad→stick fold). Without
# this, Ape's analog-locked menus ignore set_input and the oracle never reaches
# LOAD. Apply after checkout; ignore failure on tips that already have it or
# whose main.cpp moved too far (nav may then be inconclusive → 125).
PATCH="$ROOT/tools/patches/ape_bisect_dualshock_inject.patch"
if [[ -f "$PATCH" ]]; then
  git checkout -- runtime/src/main.cpp 2>/dev/null || true
  if git apply --check "$PATCH" >>"$LOG" 2>&1; then
    git apply "$PATCH" >>"$LOG" 2>&1 || true
    echo "applied DualShock inject patch" | tee -a "$LOG"
  else
    echo "DualShock inject patch skipped (does not apply cleanly)" | tee -a "$LOG"
  fi
fi

# Rebuild runtime against this psxrecomp tip (debug server required for oracle).
# Re-run cmake lightly so tip changes that alter cmake options still apply.
# Mid-integrate tips always compile psx_netplay_*.c and need recomp-net
# headers even for offline runs. Keep NETPLAY linked; oracle stays offline.
# Prefer tip-pinned submodule so older midpoints match recomp-net API.
git submodule update --init lib/recomp-net >>"$LOG" 2>&1 || true
RECOMP_NET="${RECOMP_NET_ROOT:-$ROOT/psxrecomp-v4/lib/recomp-net}"
if ! cmake "$ROOT" -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DPSX_NETPLAY=ON -DRECOMP_NET_ROOT="$RECOMP_NET" \
      -DPSX_DEBUG_TOOLS=ON -DAPE_BISECT_WEAK_STUBS=ON \
      -B "$BUILD" >>"$LOG" 2>&1; then
  echo "CMAKE FAIL $rev — skip" | tee -a "$LOG"
  exit 125
fi
# Cap parallelism: -j$(nproc)/-j4 OOM-kills mid-build here (25Gi swap thrash).
JOBS="${APE_BISECT_JOBS:-1}"
if ! cmake --build "$BUILD" --target ApeEscapeRecomp -j"$JOBS" >>"$LOG" 2>&1; then
  echo "BUILD FAIL $rev — skip" | tee -a "$LOG"
  exit 125
fi
# Sanity: debug tools must be linked (Release defaults them OFF).
if ! nm "$EXE" 2>/dev/null | grep -q ' debug_server_init$'; then
  # still accept T/t with address prefix
  if ! nm "$EXE" 2>/dev/null | grep -q 'T debug_server_init'; then
    echo "NO debug_server_init in $EXE — skip" | tee -a "$LOG"
    exit 125
  fi
fi

# Kill prior exe only (never pkill -f "$EXE" — that matches the python argv).
pkill -x ApeEscapeRecomp 2>/dev/null || true
sleep 0.3

export APE_DISC="${APE_DISC:-/mnt/crucial4tb/Emulation/roms/ps/Ape Escape (USA)/Ape Escape (USA).cue}"

# Seed a fast settings.toml beside the exe (turbo + software + bios_hle).
# Ape is DualShock-locked: default P1 "keyboard" presents id 0x41 and the
# title ignores injected START/CROSS. Force an analog DualShock seat even
# with no physical pad (kind=auto, open_player fails, SIO still reports 0x73).
SETTINGS="$BUILD/settings.toml"
cat >"$SETTINGS" <<EOF
[video]
renderer          = "software"
bios_hle          = true
turbo_loads       = true
auto_skip_fmv     = true
supersampling     = 1

[launcher]
skip_launcher = true

[disc]
path = "$APE_DISC"

[memcard]
# Use the real save card — LOAD GAME path that wedges on integrate.
dir     = "$ROOT/saves"
card1   = "/mnt/crucial4tb/Emulation/saves/ps/card1.mcd"
card2   = "$ROOT/saves/card2.mcd"
enable1 = true
enable2 = true

[controller]
# DualShock seat (Ape ignores digital/keyboard pads for menu confirm).
p1_device = "auto"
p1_mode   = "analog"
p2_device = "none"
EOF

# Fast post-probe predicate (txn 75 / mc climb). Override with APE_MEMCARD_FAST=0
# for the full starfield oracle.
export APE_MEMCARD_FAST="${APE_MEMCARD_FAST:-1}"

rc=3
for try in 1 2 3; do
  echo "loadtest try $try @ $rev (FAST=$APE_MEMCARD_FAST)" | tee -a "$LOG"
  set +e
  python3 "$ROOT/tools/ape_memcard_loadtest.py" "$EXE" "$ROOT/game.toml" "$PORT" \
    2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  set -e
  if [[ $rc -eq 0 ]]; then
    echo "GOOD $rev" | tee -a "$LOG"
    exit 0
  fi
  if [[ $rc -eq 2 ]]; then
    echo "BAD $rev" | tee -a "$LOG"
    exit 1
  fi
  echo "inconclusive rc=$rc — retry" | tee -a "$LOG"
  pkill -x ApeEscapeRecomp 2>/dev/null || true
  sleep 1
done

echo "SKIP $rev (inconclusive)" | tee -a "$LOG"
exit 125
