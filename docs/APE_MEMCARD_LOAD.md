# Ape Escape — LOAD GAME memcard (offline)

Title: **Ape Escape (USA)** (`SCUS-944.23`). Symptom this doc covers: offline
**LOAD GAME** hangs on an empty navy Checking starfield after confirming the
title menu.

This path is **load-bearing for Ape Escape**. Do not strip or “simplify” the
offline SIO / nest repairs in `psxrecomp-v4` without re-running the oracle
below. MotK netplay must stay uncapped / unstick-off (gated on
`psx_netplay_active()`).

## Oracle

```bash
# Full UI oracle (PASS = file-list overlay, CardMenuMode==2)
APE_DISC="/path/to/Ape Escape (USA).cue" APE_MEMCARD_DUMP=1 \
  python3 tools/ape_memcard_loadtest.py build-bisect/ApeEscapeRecomp game.toml 4488

# Fast bisect (probe follow-up only; not UI truth)
APE_MEMCARD_FAST=1 … python3 tools/ape_memcard_loadtest.py …
```

| Result | Meaning |
|--------|---------|
| PASS | `mc_read_done` advanced past boot **and** screenshot is `filelist` **and** `CardMenuMode@0x8013AF50 == 2` |
| FAIL | Card path started but still empty Checking starfield after I/O quiet |
| INCONCLUSIVE | Never reached LOAD |

**Classifier pitfall:** the healthy Load file list keeps the navy starfield
*behind* red `FileN` / white labels. Mean RGB looks like Checking — the
harness classifies `filelist` via red/bright chrome before the starfield gate.
`mc_read_done` alone is a false PASS.

Env knobs: `PSX_APE_CARD_UNSTICK=0` disables offline nest repair;
`APE_MEMCARD_NO_TURBO=1` breaks nav (avoid for oracle).

## Failure model (libcard)

Guest symbols: `symbols.toml` / `psx_symbols.h` (`CardMenuDispatch`,
`LibCardIntRP`, nest/busy objects). Sync with `python3 tools/sync_symbols.py`.

| Object | Addr | Role |
|--------|------|------|
| Nest depth | `0x800A6C10` | Idle = **bit31** (`0xFFFFFFFF`), not `== 0` |
| Busy code | `0x800B4E30` | `1` = Busy1 (file list), `2` = Busy2 (Checking) |
| Ready flag | `0x800B4E38` | Latched by `LibCardIntRP` only when a pop leaves nest idle |
| Menu mode | `0x8013AF50` | `5` Checking, `2` file list |

`LibCardIntRP` (`0x800226C8`) pops one nest level per SIO IRQ7 edge and
publishes (`B4E38` + copy busy→result) only when the pop leaves bit31 set.
Merged IRQ7 edges → one pop for two bytes → nest stuck at depth 1 after the
LOAD presence probe (`81 52 00` + SELECT abort) → directory never starts /
Checking never becomes the file list.

## Runtime fix (psxrecomp-v4)

Important offline-only paths (search `Ape Escape` / `Ape LOAD` in these files):

| File | What |
|------|------|
| `runtime/src/sio.c` | Offline `MAX_TRANSITIONS=1`; defer card ACK while `I_STAT.7`; flush ACK on SELECT; after probe abort **IRQ-only** nest unwind (**never poke `A6C10`**); pulse pump until idle/`B4E38` |
| `runtime/src/memory.c` | Briefly hold `I_MASK.7` when BIOS clears it with nest still stuck |
| `runtime/src/bios_hle.c` | Refuse call-HLE when OpenBIOS has no `deliver_event_ret` (silent callback skip wedges HwCARD/SwCARD flags) |

**Do not** host-synth `B4E20`/`B4E30`/`B4E38` or collapse `A6C10→0` mid-probe —
those storm `81 52` or tear nest levels (phase `0x1F` Busy2 dead-end).

Netplay: unstick / bit7-hold / ACK-defer card path off or uncapped so MotK
leftover-time SIO walks stay deterministic.

## Related

- Progressive symbols practice: workspace rule + `symbols.toml`
- Framework pin: `docs/framework_pin_history.md` (submodule `psxrecomp-v4`)
