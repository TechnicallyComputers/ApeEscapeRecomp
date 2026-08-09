#!/usr/bin/env python3
"""Headless Ape Escape title → LOAD GAME memcard oracle (PASS/FAIL).

Exit codes:
  0 PASS  — LOAD left the empty starfield after card I/O (real UI recovery)
  2 FAIL  — card path started but scene stayed on starfield (wedge)
  3 INCONCLUSIVE — never reached LOAD / debug port dead
  4 BUILD/LAUNCH error

Proven sequence (integrate hang repro):
  boot settle → TRIANGLE×4 → START → title → DOWN → CROSS
  Starfield during directory scan is normal; FAIL only if I/O quiets and
  the scene is still starfield (mc_read_done alone is a false PASS).

Fast bisect mode (APE_MEMCARD_FAST=1):
  After the shared LOAD probe (abort_other after 81 52 00), PASS if a
  follow-up card txn starts within ~120ms (prefer 0x57 / post-probe
  traffic). Does not wait for UI; use full oracle for starfield truth.

DualShock seat required (bisect settings.toml: p1_device=auto, p1_mode=analog).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build-bisect" / "ApeEscapeRecomp"
TOML = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "game.toml"
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 4488
DISC = os.environ.get(
    "APE_DISC",
    "/mnt/crucial4tb/Emulation/roms/ps/Ape Escape (USA)/Ape Escape (USA).cue",
)
# PSX active-low: Up=4 Right=5 Down=6 Left=7 Start=3 Cross=14 Triangle=12
CROSS, START, TRIANGLE, DOWN = 0xBFFF, 0xFFF7, 0xEFFF, 0xFFBF
# Fast post-probe follow-up window (master starts 0x57 write inside ~40ms).
FAST_FOLLOW_S = float(os.environ.get("APE_MEMCARD_FAST_S", "0.12"))
FAST_MODE = os.environ.get("APE_MEMCARD_FAST", "").strip() in ("1", "true", "yes")


def q(cmd: str, **kw):
    d = {"cmd": cmd}
    d.update(kw)
    try:
        s = socket.socket()
        s.settimeout(4.0)
        s.connect(("127.0.0.1", PORT))
        s.sendall((json.dumps(d) + "\n").encode())
        buf = b""
        dc = ds = 0
        ins = esc = started = False
        while True:
            ch = s.recv(65536)
            if not ch:
                break
            for b in ch:
                buf += bytes([b])
                c = chr(b)
                if ins:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        ins = False
                    continue
                if c == '"':
                    ins = True
                elif c == "{":
                    dc += 1
                    started = True
                elif c == "}":
                    dc -= 1
                elif c == "[":
                    ds += 1
                elif c == "]":
                    ds -= 1
                if started and dc == 0 and ds == 0:
                    s.close()
                    return json.loads(buf.decode().strip())
    except Exception as e:
        return {"err": str(e)}
    return {"err": "truncated"}


def frame():
    return q("frame").get("frame")


def sio():
    return q("sio_state")


def hold(buttons: int, seconds: float = 0.35):
    # Fold D-pad onto left stick so DualShock-locked Ape menus respond even
    # when the runtime ignores button bits for stick-only paths (and so bisect
    # tips without the kind==0→p.mode main.cpp fix still navigate).
    lx = ly = 0x80
    pressed = (~buttons) & 0xFFFF
    if pressed & 0x0010:  # Up
        ly = 0x00
    if pressed & 0x0040:  # Down
        ly = 0xFF
    if pressed & 0x0080:  # Left
        lx = 0x00
    if pressed & 0x0020:  # Right
        lx = 0xFF
    q("set_input", buttons=f"0x{buttons:04X}", lx=lx, ly=ly, rx=0x80, ry=0x80)
    time.sleep(seconds)
    q("clear_input")
    time.sleep(0.2)


def kill_exe():
    subprocess.run(["pkill", "-x", "ApeEscapeRecomp"], capture_output=True)
    exe = str(EXE.resolve())
    try:
        out = subprocess.check_output(["pgrep", "-f", f"^{exe}( |$)"], text=True)
        for pid in out.split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    except subprocess.CalledProcessError:
        pass
    time.sleep(0.4)


def launch() -> subprocess.Popen:
    kill_exe()
    env = os.environ.copy()
    # Do NOT force SDL_VIDEODRIVER=dummy / PSX_HEADLESS=1 — that path missed the
    # LOAD hang repro that works with --headless alone.
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    cwd = EXE.parent
    cmd = [
        str(EXE),
        "--no-launcher",
        "--headless",
        "--renderer",
        "software",
        "--debug-port",
        str(PORT),
        "--game",
        str(TOML),
        "--disc",
        DISC,
        "--memcard-dir",
        str(ROOT / "saves"),
    ]
    log = open(cwd / "ape_memcard_loadtest.log", "w")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def wait_ping(timeout: float = 60.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if q("ping").get("ok"):
            return True
        time.sleep(0.4)
    return False


def advancing(settle: float = 0.8) -> bool:
    a = frame()
    if a is None:
        return False
    time.sleep(settle)
    b = frame()
    return b is not None and b != a


def enable_turbo():
    # APE_MEMCARD_NO_TURBO=1: isolate turbo×card nesting (tip starfield hang).
    if os.environ.get("APE_MEMCARD_NO_TURBO", "").strip() in ("1", "true", "yes"):
        print("  turbo disabled (APE_MEMCARD_NO_TURBO)")
        return
    q("turbo_loads", n=1)
    q("turbo", enabled=1)


def classify_screen(path: Path) -> str:
    im = Image.open(path).convert("RGB")
    px = list(im.getdata())
    n = len(px)
    if n == 0:
        return "other"
    r = sum(p[0] for p in px) / n
    g = sum(p[1] for p in px) / n
    b = sum(p[2] for p in px) / n
    green = sum(1 for p in px if p[1] > p[0] + 10 and p[1] > p[2] + 10) / n
    dark = sum(1 for p in px if p[0] < 40 and p[1] < 40 and p[2] < 80) / n
    # Title LOAD/NEW menu (calibrated start1b ~0.73 green).
    # g>90 (was 95): older tips / software renderer land ~g=62..92 on the
    # same green menu and were falsely classified "other", killing the nav.
    if green >= 0.70 and g > 60 and b < 60 and r < 100:
        return "title"
    # File-list overlay keeps the navy starfield behind red "FileN" / white
    # labels. Mean RGB still looks like empty Checking — require chrome
    # before the starfield gate (timeout.png: File1..4 No Data + [Return]).
    red_ui = sum(
        1 for p in px if p[0] > 90 and p[0] > p[1] + 25 and p[0] > p[2] + 10
    ) / n
    bright = sum(1 for p in px if (p[0] + p[1] + p[2]) > 140) / n
    if red_ui >= 0.0015 or bright >= 0.008:
        return "filelist"
    # Empty LOAD starfield is dark navy (mean B ~10–50 depending on star
    # density / screenshot timing). Requiring b > g+20 false-negatives to
    # "other" and false-PASSes the UI oracle.
    if dark >= 0.55 and b > g + 2 and b > r + 2 and g < 30 and r < 30:
        return "starfield"
    return "other"


def grab_class(shot_dir: Path, tag: str) -> str:
    path = shot_dir / f"{tag}.png"
    r = q("screenshot_file", path=str(path))
    if r.get("err"):
        return "other"
    try:
        return classify_screen(path)
    except Exception:
        return "other"


def reach_load_and_confirm(base_reads: int, shot_dir: Path) -> bool:
    """nav2 repro: settle → TRIANGLE×4 → START → wait title → DOWN → CROSS."""
    enable_turbo()
    # Match the working nav2 wall-clock settle (12×1.5s). Extra waits push
    # past the title window into attract gameplay where START opens Options.
    for i in range(12):
        time.sleep(1.5)
        if i % 4 == 3:
            print(f"  boot settle {i} frame={frame()}")
    for _ in range(4):
        hold(TRIANGLE, 0.3)
    hold(START, 0.5)
    time.sleep(1.0)
    # Poll for title BEFORE any DOWN/CROSS — premature menu traffic leaves
    # the shell on the wrong screen and never bumps mc_reads (tip bisect).
    kind = "other"
    for extra in range(10):
        kind = grab_class(shot_dir, f"title_{extra}")
        print(f"  wait title {extra} screen={kind} frame={frame()}")
        if kind in ("title", "starfield"):
            break
        if extra in (3, 6):
            hold(START, 0.45)
            time.sleep(0.8)
        else:
            time.sleep(0.8)
    if kind == "starfield":
        print("  already on starfield after START")
        return True
    if kind != "title":
        print("  WARN: no title classify; trying DOWN+CROSS anyway")
    for seq in range(12):
        hold(DOWN, 0.35)
        # Poll through CROSS so we can see the probe while I_MASK still has bit7.
        q("set_input", buttons=f"0x{CROSS:04X}", lx=0x80, ly=0x80, rx=0x80, ry=0x80)
        t_cross = time.time()
        saw = False
        while time.time() - t_cross < 0.55:
            st = sio()
            reads = int(st.get("mc_reads") or 0)
            done = int(st.get("mc_read_done") or 0)
            if reads > base_reads or reads > done:
                print(f"  card path reached mid-CROSS (mc={reads}/{done})")
                if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
                    print(f"  LIVE irq={q('irq_state')}")
                    print(f"  LIVE sio={st}")
                    print(f"  LIVE txn={_txn_entries(6)}")
                    print(f"  LIVE sio_irq={q('sio_irq_dump', count=20)}")
                    print(f"  LIVE imask={q('imask_trace', count=12)}")
                    # Probe byte_seq window (card ACKs may have scrolled out of ring dump).
                    ents = _txn_entries(4)
                    last = ents[-1] if ents else {}
                    b0 = int(last.get('start_byte_seq') or 0)
                    if b0:
                        print(f"  LIVE irq_win={q('sio_irq_window', byte_seq=b0, before=4, after=100)}")
                    print(f"  LIVE thr={q('thread_trace', count=12)}")
                    # Wider window: Fix #3 / thread-smear fingerprints live on
                    # the probe ACK deliveries (same_thread/restored/v0/v1).
                    print(f"  LIVE irqctx={q('irqctx_ring', count=48)}")
                saw = True
                break
            time.sleep(0.002)
        q("clear_input")
        time.sleep(0.2)
        if saw:
            return True
        st = sio()
        reads = int(st.get("mc_reads") or 0)
        done = int(st.get("mc_read_done") or 0)
        kind = grab_class(shot_dir, f"nav_{seq}")
        print(
            f"  nav {seq} mc={reads}/{done} screen={kind} frame={frame()}"
        )
        if reads > base_reads or reads > done or kind == "starfield":
            print(f"  card path reached (mc={reads}/{done} screen={kind})")
            if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
                print(f"  NAV irq={q('irq_state')}")
                print(f"  NAV sio={sio()}")
                print(f"  NAV txn={_txn_entries(6)}")
                print(f"  NAV sio_irq={q('sio_irq_dump', count=20)}")
                print(f"  NAV imask={q('imask_trace', count=12)}")
            return True
    return False


def _txn_entries(count: int = 8):
    r = q("card_txn_dump", count=count)
    return r.get("entries") or []


def _dump_evcb_card(tag: str = "DUMP") -> None:
    """EvCB / SwCARD lever dump for tip-vs-master LOAD diagnosis."""
    stats = q("evcb_walk_stats")
    print(f"  {tag} evcb_stats={stats}")
    snap = q("evcb_snapshot")
    s = (snap or {}).get("snapshot") or {}
    entries = s.get("entries") or []
    cardish = []
    for e in entries:
        i = e.get("i", "?")
        cls = str(e.get("class") or e.get("cls") or "")
        fh = str(e.get("fhandler") or "")
        if (
            "F0000011" in cls.upper()
            or "F0000012" in cls.upper()
            or fh.lower().startswith("0x800229")
            or fh.lower().startswith("0x80020")
        ):
            cardish.append((i, e, cls))
    print(f"  {tag} evcb_base={s.get('evcb_base')} n={s.get('entry_count')} cardish={len(cardish)}")
    for i, e, cls in cardish[:24]:
        print(
            f"  {tag} evcb[{i}] class={cls} st={e.get('status')} "
            f"spec={e.get('spec')} mode={e.get('mode')} fh={e.get('fhandler')}"
        )
    walk = q("evcb_walk_dump", count=16)
    snaps = (walk or {}).get("snapshots") or []
    pairs = []
    for sn in snaps:
        pairs.append(f"{sn.get('tag')}:{sn.get('a0')}/{sn.get('a1')}")
    print(f"  {tag} evcb_recent={pairs}")
    # B0 HLE may service DeliverEvent without dispatching RAM 0x1B44 — check ring.
    hle_sum = q("hle_dump")
    print(f"  {tag} hle_status={hle_sum}")
    hle = q("hle_dump", tail=4000, fn=7)  # B0:07 DeliverEvent across ring window
    deliv = []
    card_deliv = []
    for e in hle.get("entries") or []:
        a0 = str(e.get("a0") or "")
        a1 = str(e.get("a1") or "")
        item = f"r{e.get('route')}:{a0}/{a1}"
        deliv.append(item)
        if "F0000011" in a0.upper() or "F4000001" in a0.upper():
            card_deliv.append(item)
    print(
        f"  {tag} hle_deliver_n={len(deliv)} card_deliv_n={len(card_deliv)} "
        f"last_card={card_deliv[-16:]} last_any={deliv[-8:]}"
    )
    # Broader B0 tail (card Open/Test/Enable often nearby).
    hle_b0 = q("hle_dump", tail=40)
    print(
        f"  {tag} hle_b0_tail="
        f"{[{k: e.get(k) for k in ('fn', 'a0', 'a1', 'v0', 'route')} for e in (hle_b0.get('entries') or [])]}"
    )
    # B0 card-ish fns: 0x4E.. card, 0x08 OpenEvent, 0x0B TestEvent, 0x0C EnableEvent
    for fn, label in ((8, "OpenEvent"), (11, "TestEvent"), (12, "EnableEvent"), (78, "card?")):
        r = q("hle_dump", tail=4000, fn=fn)
        ents = r.get("entries") or []
        print(f"  {tag} hle_fn_{fn:02X}_{label}_n={len(ents)} last={[{k:e.get(k) for k in ('a0','a1','v0','route')} for e in ents[-4:]]}")
    print(f"  {tag} ram_b4ee0={q('mem_words', addr='0x800B4EE0', count=12)}")
    print(f"  {tag} ram_b4f00={q('mem_words', addr='0x800B4F00', count=8)}")
    print(f"  {tag} ram_b4e90={q('mem_words', addr='0x800B4E90', count=8)}")
    print(f"  {tag} ram_7260={q('mem_words', addr='0x80007260', count=8)}")


def _txn_has_followup(entries) -> bool:
    """True if we see a post-probe card txn (0x57 write or a later success)."""
    saw_abort_probe = False
    for e in entries:
        tx = e.get("tx") or []
        # Normalize hex strings from debug server.
        tx0 = [str(x).lower() for x in tx[:3]]
        reason = e.get("end_reason")
        nbytes = e.get("bytes")
        if reason == "abort_other" and nbytes == 3 and tx0[:2] == ["0x81", "0x52"]:
            saw_abort_probe = True
            continue
        if not saw_abort_probe:
            continue
        # Anything after the probe abort counts as follow-up.
        if reason in ("success", "open") or nbytes not in (None, 0, 3):
            return True
        if len(tx) >= 2 and tx0[:2] == ["0x81", "0x57"]:
            return True
    # Also: any 0x57 in the window (probe may have scrolled out).
    for e in entries:
        tx = [str(x).lower() for x in (e.get("tx") or [])[:2]]
        if tx == ["0x81", "0x57"]:
            return True
    return False


def verdict_probe_followup(bump_reads: int, bump_done: int, shot_dir: Path) -> int:
    """Fast bisect predicate: card traffic resumes after the presence probe."""
    t0 = time.time()
    saw_probe_abort = False
    samples = 0
    del shot_dir  # FAST does not wait on UI; full oracle owns starfield truth.

    while time.time() - t0 < FAST_FOLLOW_S:
        st = sio()
        reads = int(st.get("mc_reads") or 0)
        done = int(st.get("mc_read_done") or 0)
        ents = _txn_entries(8)
        for e in ents:
            if (
                e.get("end_reason") == "abort_other"
                and e.get("bytes") == 3
                and [str(x).lower() for x in (e.get("tx") or [])[:2]]
                == ["0x81", "0x52"]
            ):
                saw_probe_abort = True
        if _txn_has_followup(ents):
            if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
                print(f"  DUMP irq={q('irq_state')}")
                print(f"  DUMP sio={sio()}")
                print(f"  DUMP txn={_txn_entries(4)}")
            print(
                f"  FAST PASS follow-up txn after probe "
                f"(+{(time.time()-t0)*1000:.0f}ms)"
            )
            return 0
        # Prefer follow-up txn; bare done/reads climb can be another probe.
        if done > bump_done or reads > bump_reads + 1:
            print(
                f"  FAST PASS mc {bump_reads}/{bump_done}->{reads}/{done} "
                f"(+{(time.time()-t0)*1000:.0f}ms)"
            )
            return 0
        if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
            if samples < 6:
                irq = q("irq_state")
                print(
                    f"  T+{(time.time()-t0)*1000:.0f}ms mc={reads}/{done} "
                    f"imask={irq.get('i_mask')} istat={irq.get('i_stat')} "
                    f"txn0={ents[-1] if ents else None}"
                )
                if samples == 0:
                    print(f"  Tmid sio_irq={q('sio_irq_dump', count=16)}")
                    print(f"  Tmid imask={q('imask_trace', count=40)}")
                    print(f"  Tmid imask_b7c={q('imask_trace', count=40, only_b7c=1)}")
                    print(f"  Tmid txn={ents}")
                    print(f"  Tmid thr={q('thread_trace', count=20)}")
                samples += 1
        time.sleep(0.005)
    # One more sample at the deadline.
    st = sio()
    reads = int(st.get("mc_reads") or 0)
    done = int(st.get("mc_read_done") or 0)
    ents = _txn_entries(8)
    if done > bump_done or reads > bump_reads + 1 or _txn_has_followup(ents):
        print(f"  FAST PASS late mc={reads}/{done}")
        return 0
    last = ents[-1] if ents else {}
    print(
        f"  FAST FAIL mc={reads}/{done} stuck after probe "
        f"(saw_abort={saw_probe_abort} last_txn="
        f"{last.get('txn_seq')}/{last.get('bytes')}/{last.get('end_reason')} "
        f"tx={(last.get('tx') or [])[:6]})"
    )
    # Extra post-mortem for tip-vs-master diagnosis (env APE_MEMCARD_DUMP=1).
    if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
        irq = q("irq_state")
        print(f"  DUMP irq={irq}")
        print(f"  DUMP sio={sio()}")
        print(f"  DUMP txn={_txn_entries(6)}")
        print(f"  DUMP irqctx={q('irqctx_ring', count=8)}")
        print(f"  DUMP imask={q('imask_trace', count=60)}")
        print(f"  DUMP card_handoff={q('card_handoff', count=48)}")
        print(f"  DUMP thr={q('thread_trace', count=24)}")
        # Always-on libcard / card-menu state (see debug_server wtrace ranges 16-21).
        print(
            f"  DUMP libcard={q('wtrace_dump', addr_lo='0x000B4E2C', addr_hi='0x000B4ED4', count=40, newest=1)}"
        )
        print(f"  DUMP ram_a6c10={q('mem_words', addr='0x800A6C10', count=4)}")
        print(f"  DUMP ram_b4e38={q('mem_words', addr='0x800B4E38', count=4)}")
        print(
            f"  DUMP scene={q('wtrace_dump', addr_lo='0x000E3880', addr_hi='0x000E3888', count=20, newest=1)}"
        )
        print(
            f"  DUMP cardmenu={q('wtrace_dump', addr_lo='0x0013AF50', addr_hi='0x0013AF60', count=20, newest=1)}"
        )
        print(
            f"  DUMP kcard={q('wtrace_dump', addr_lo='0x00007260', addr_hi='0x00007270', count=20, newest=1)}"
        )
        print(f"  DUMP ram_b4e30={q('mem_words', addr='0x800B4E30', count=8)}")
        print(f"  DUMP ram_e3880={q('mem_words', addr='0x800E3880', count=4)}")
        print(f"  DUMP ram_13af50={q('mem_words', addr='0x8013AF50', count=4)}")
        print(f"  DUMP ram_7264={q('mem_words', addr='0x80007264', count=4)}")
    return 2


def _ui_left_starfield(shot_dir: Path, tag: str, settle_s: float = 2.5) -> tuple[bool, str]:
    """Poll until classify ≠ starfield, or settle_s elapses."""
    deadline = time.time() + settle_s
    kind = "other"
    while time.time() < deadline:
        kind = grab_class(shot_dir, tag)
        if kind != "starfield":
            return True, kind
        time.sleep(0.25)
    return False, kind


def _txn_saw_cmd(entries, cmd_hi: str) -> bool:
    want = cmd_hi.lower()
    for e in entries:
        tx = [str(x).lower() for x in (e.get("tx") or [])[:2]]
        if len(tx) >= 2 and tx[0] == "0x81" and tx[1] == want:
            return True
    return False


def verdict_after_card(base_done: int, base_reads: int, shot_dir: Path) -> int:
    """PASS only when LOAD leaves starfield after card I/O has started.

    Directory scan keeps the navy starfield while mc_read_done climbs — that
    is not failure. Fail when I/O goes quiet and the scene is still starfield.
    """
    t0 = time.time()
    last_reads = base_reads
    last_done = base_done
    quiet_t = None
    saw_progress = False
    saw_57 = False
    # Wall clock for full directory + UI transition under turbo.
    limit_s = float(os.environ.get("APE_MEMCARD_UI_S", "45"))
    quiet_need_s = float(os.environ.get("APE_MEMCARD_QUIET_S", "3.0"))
    while time.time() - t0 < limit_s:
        st = sio()
        if st.get("err"):
            time.sleep(0.4)
            continue
        reads = int(st.get("mc_reads") or 0)
        done = int(st.get("mc_read_done") or 0)
        ents = _txn_entries(10)
        if _txn_saw_cmd(ents, "0x57"):
            saw_57 = True
        if done > base_done or reads > base_reads:
            saw_progress = True
        kind = grab_class(shot_dir, "verdict")
        # RAM gate: CardMenuMode 2 = file list (master). Classifier alone can
        # false-PASS mid-scan frames.
        mode = 0
        try:
            mode = int((q("mem_words", addr="0x8013AF50", count=1).get("words") or ["0"])[0], 0)
        except Exception:
            mode = 0
        if saw_progress and kind != "starfield" and mode == 2:
            print(
                f"  UI left Checking done={done} reads={reads} "
                f"screen={kind} mode={mode} saw_57={saw_57}  PASS"
            )
            return 0
        if (
            saw_progress
            and kind != "starfield"
            and mode != 2
            and os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes")
        ):
            # One-line, rate-limited by quiet_t reset — avoid spam.
            if quiet_t is not None and time.time() - quiet_t < 0.4:
                print(
                    f"  note: screen={kind} CardMenuMode={mode} "
                    f"(want 2) done={done}"
                )
        if reads > last_reads or done > last_done:
            last_reads = max(last_reads, reads)
            last_done = max(last_done, done)
            quiet_t = None
        else:
            if quiet_t is None:
                quiet_t = time.time()
            elif (
                saw_progress
                and time.time() - quiet_t >= quiet_need_s
                and kind == "starfield"
            ):
                print(
                    f"  UI STILL STARFIELD after quiet "
                    f"done={done} reads={reads} saw_57={saw_57}  FAIL"
                )
                if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
                    print(f"  DUMP irq={q('irq_state')}")
                    print(f"  DUMP sio={sio()}")
                    print(f"  DUMP txn={_txn_entries(8)}")
                    print(f"  DUMP card_handoff={q('card_handoff', count=48)}")
                    print(f"  DUMP ram_a6c10={q('mem_words', addr='0x800A6C10', count=4)}")
                    print(f"  DUMP ram_b4e20={q('mem_words', addr='0x800B4E20', count=8)}")
                    print(f"  DUMP ram_b4e90={q('mem_words', addr='0x800B4E90', count=8)}")
                    print(f"  DUMP ram_b4ed0={q('mem_words', addr='0x800B4ED0', count=4)}")
                    print(f"  DUMP ram_b4f00={q('mem_words', addr='0x800B4F00', count=8)}")
                    print(f"  DUMP ram_e3880={q('mem_words', addr='0x800E3880', count=2)}")
                    print(f"  DUMP ram_13af50={q('mem_words', addr='0x8013AF50', count=4)}")
                    print(f"  DUMP libcard={q('wtrace_dump', addr_lo='0x000B4E2C', addr_hi='0x000B4ED4', count=40, newest=1)}")
                    _dump_evcb_card("DUMP")
                return 2
        if not advancing(0.6):
            print(f"  FROZEN frame={frame()} reads={reads} done={done}  FAIL")
            return 2
        time.sleep(0.35)
    st = sio()
    reads = int(st.get("mc_reads") or 0)
    done = int(st.get("mc_read_done") or 0)
    kind = grab_class(shot_dir, "timeout")
    mode = 0
    try:
        mode = int((q("mem_words", addr="0x8013AF50", count=1).get("words") or ["0"])[0], 0)
    except Exception:
        mode = 0
    if saw_progress and kind != "starfield" and mode == 2:
        print(f"  late UI left starfield done={done} screen={kind} mode={mode}  PASS")
        return 0
    print(
        f"  TIMEOUT reads={reads} done={done} screen={kind} mode={mode} "
        f"saw_57={saw_57} progress={saw_progress}  FAIL"
    )
    if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
        print(f"  DUMP sio={sio()}")
        print(f"  DUMP ram_a6c10={q('mem_words', addr='0x800A6C10', count=4)}")
        print(f"  DUMP ram_b4e20={q('mem_words', addr='0x800B4E20', count=8)}")
        _dump_evcb_card("DUMP")
    return 2


def attempt() -> int:
    proc = launch()
    shot_dir = Path("/tmp/ape_oracle_last")
    if shot_dir.exists():
        for old in shot_dir.glob("*.png"):
            old.unlink()
    else:
        shot_dir.mkdir(parents=True)
    try:
        if not wait_ping(90.0):
            print("  debug port never came up")
            return 3
        enable_turbo()
        time.sleep(2.0)
        st0 = sio()
        base_reads = int(st0.get("mc_reads") or 0)
        base_done = int(st0.get("mc_read_done") or 0)
        print(f"  boot mc_reads={base_reads} mc_read_done={base_done} frame={frame()}")
        pad = q("pad_status").get("slot0") or {}
        print(f"  pad0 analog={pad.get('analog')} connected={pad.get('connected')}")
        if pad.get("analog") is not True:
            print("  WARN: pad0 not analog — need DualShock settings.toml")
        if not reach_load_and_confirm(base_reads, shot_dir):
            print("  never reached card path")
            return 3
        st1 = sio()
        bump_reads = int(st1.get("mc_reads") or base_reads)
        bump_done = int(st1.get("mc_read_done") or base_done)
        if os.environ.get("APE_MEMCARD_DUMP", "").strip() in ("1", "true", "yes"):
            # Immediate snapshot at card-path edge (before the follow-up window).
            print(f"  T0 irq={q('irq_state')}")
            print(f"  T0 sio={st1}")
            print(f"  T0 txn={_txn_entries(4)}")
            print(f"  T0 sio_irq={q('sio_irq_dump', count=12)}")
            print(f"  T0 imask={q('imask_trace', count=8)}")
        if FAST_MODE:
            # done already past boot ⇒ LOAD card path already moving (handoff OK).
            if bump_done > base_done or bump_reads > base_reads + 1:
                print(
                    f"  FAST PASS done {base_done}->{bump_done} "
                    f"reads={bump_reads} (UI check is full-oracle only)"
                )
                return 0
            print(
                f"  FAST mode: probe window {FAST_FOLLOW_S*1000:.0f}ms "
                f"from mc={bump_reads}/{bump_done}"
            )
            return verdict_probe_followup(bump_reads, bump_done, shot_dir)
        return verdict_after_card(base_done, bump_reads, shot_dir)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass
        kill_exe()
        time.sleep(0.3)


def main() -> int:
    if not EXE.is_file():
        print(f"RESULT: LAUNCH_ERROR missing exe {EXE}")
        return 4
    if not Path(DISC).is_file():
        print(f"RESULT: LAUNCH_ERROR missing disc {DISC}")
        return 4
    for a in range(3):
        print(f"=== attempt {a} ({EXE}) ===")
        r = attempt()
        if r in (0, 2):
            print("RESULT:", "PASS" if r == 0 else "FAIL")
            return r
        print("  inconclusive; retry")
    print("RESULT: INCONCLUSIVE")
    return 3


if __name__ == "__main__":
    sys.exit(main())
