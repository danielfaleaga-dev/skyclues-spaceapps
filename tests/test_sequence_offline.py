"""Offline tests of the multi-epoch selection logic and the player state machine.
Synthetic objects here exercise logic only; they are never shown as data."""

import json
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from skyclues import config
from skyclues.pairing import Candidate
from skyclues.player import PLAYER_CORE_JS
from skyclues.sequence import _compatible, choose, propose_sequences


def _cand(name, det, mjd, lam, slope=0.0, coll="spherex_dr1", bw=0.035):
    rec = SimpleNamespace(detector=det, mjd_mid=mjd, collection=coll, file_name=name, obs_id=name)
    pts = lam + slope * np.linspace(-1, 1, 9)
    return Candidate(rec=rec, x=1000, y=1000, margin_px=100, lam_um=lam, bw_um=bw,
                     xs=np.zeros(9), ys=np.zeros(9), lam_pts=pts)


def test_proposals_are_globally_compatible_distinct_and_chronological():
    c = [
        _cand("a", 2, 100.0, 1.500), _cand("b", 2, 130.0, 1.503), _cand("c", 2, 160.0, 1.505),
        _cand("d", 2, 160.2, 1.501),             # same day as c -> not a distinct epoch
        _cand("e", 2, 190.0, 1.540),             # spectrally incompatible (> 0.25 BW)
        _cand("f", 2, 220.0, 1.500, slope=0.02), # gradient mismatch across the field
        _cand("g", 5, 100.0, 4.30, bw=0.04), _cand("h", 5, 300.0, 4.30, bw=0.04),
    ]
    props = propose_sequences(c, max_frames=8)
    assert props, "expected at least one proposal"
    best = props[0]
    assert best["n"] == 3 and best["detector"] == 2
    for p in props:
        mem = p["members"]
        assert len({m.rec.detector for m in mem}) == 1
        mjd = [m.rec.mjd_mid for m in mem]
        assert mjd == sorted(mjd)
        assert all(abs(x - y) >= config.MIN_TIME_SEPARATION_DAYS for i, x in enumerate(mjd) for y in mjd[i + 1:])
        assert all(_compatible(x, y) for i, x in enumerate(mem) for y in mem[i + 1:])  # all pairs, not consecutive
        names = {m.rec.file_name for m in mem}
        assert "e" not in names and not {"c", "d"} <= names and "f" not in names


class _Opt:
    def __init__(self, n, cov, warns=0, fail=False, s5="pass", span=10.0):
        self.n, self.metrics = n, {"coverage_common_valid": cov, "span_days": span}
        self.criteria = [{"id": "S5", "status": s5}] + [{"id": f"W{i}", "status": "warn"} for i in range(warns)]
        if fail:
            self.criteria.append({"id": "S1", "status": "fail"})

    @property
    def admissible(self):
        return all(c["status"] != "fail" for c in self.criteria)

    @property
    def warnings(self):
        return [c for c in self.criteria if c["status"] == "warn"]


def test_more_epochs_do_not_beat_much_better_coverage():
    pair, triple = _Opt(2, 0.97), _Opt(3, 0.62)
    assert choose([pair, triple]) is pair          # 0.62 < 0.97 - tolerance


def test_more_epochs_win_when_coverage_is_comparable():
    pair, triple = _Opt(2, 0.97), _Opt(3, 0.90)
    assert choose([pair, triple]) is triple


def test_quality_before_quantity_and_failures_excluded():
    four_warn, three_clean = _Opt(4, 0.90, warns=1), _Opt(3, 0.88)
    assert choose([four_warn, three_clean]) is three_clean
    assert choose([_Opt(5, 0.99, fail=True), _Opt(4, 0.99, s5="warn")]) is None


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_player_state_machine_with_node(tmp_path):
    core = tmp_path / "core.js"
    core.write_text(PLAYER_CORE_JS, encoding="utf-8")
    script = tmp_path / "run.js"
    script.write_text("""
const { createPlayer } = require(%s);
const out = {};
let p = createPlayer(4, {fps: 1, loop: true});
p.play(); const seq = []; for (let k = 0; k < 6; k++) seq.push(p.tick());
out.loop = seq;                                   // 1,2,3,0,1,2
p.pause(); const before = p.current(); p.tick(); out.pausedStays = p.current() === before;
p = createPlayer(3, {loop: false}); p.play(); out.noLoop = [p.tick(), p.tick(), p.tick()]; out.stopped = !p.state.playing;
p.play(); out.restartFromStart = p.current();     // play at the end without loop restarts at 0
p = createPlayer(3, {loop: true}); out.prevWrap = p.prev(); out.nextWrap = p.next();
p.setLoop(false); p.seek(2); out.nextClamp = p.next(); p.seek(0); out.prevClamp = p.prev();
out.seekClamp = [p.seek(-5), p.seek(99)];
p = createPlayer(5, {}); p.setBlink(true, 1, 3, 4); out.blinkStart = p.current();
const b = []; for (let k = 0; k < 4; k++) b.push(p.tick()); out.blink = b; out.blinkMs = p.intervalMs();
out.stepLeavesBlink = (p.next(), !p.state.blink && !p.state.playing);
p = createPlayer(1, {}); p.play(); out.singleFrameNoPlay = !p.state.playing;
console.log(JSON.stringify(out));
""" % json.dumps(str(core)), encoding="utf-8")
    res = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["loop"] == [1, 2, 3, 0, 1, 2]
    assert out["pausedStays"]
    assert out["noLoop"] == [1, 2, 2] and out["stopped"]
    assert out["restartFromStart"] == 0
    assert out["prevWrap"] == 2 and out["nextWrap"] == 0
    assert out["nextClamp"] == 2 and out["prevClamp"] == 0
    assert out["seekClamp"] == [0, 2]
    assert out["blinkStart"] == 1 and out["blink"] == [3, 1, 3, 1] and out["blinkMs"] == 250
    assert out["stepLeavesBlink"] and out["singleFrameNoPlay"]
