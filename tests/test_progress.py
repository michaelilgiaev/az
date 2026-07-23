"""azarch.progress -- the weighted, pinned-to-bottom build progress bar.

The bar's numbers are what the human watches for the whole multi-minute build,
and its milestone lines are the only durable checkpoints written to steps.log.
Every value here is integer arithmetic over the step weights, so an off-by-one
in the prefix sums, the width budget, or the clip boundary silently prints a
wrong percentage or a wrapped line that unsticks the pinned scroll region --
nothing crashes, the display just lies. These tests pin the pure logic:
the accum prefix sums, the _layout fill/percent math, the _clip boundary,
the milestone/phase string formats (including the exact spacing and the
U+203A separator), sub()'s monotonic clamp, and the non-TTY finalize bar.

The ProgressBar constructor opens paths.STEPS_LOG in append mode, so every
test redirects that Path into tmp_path first; nothing touches a real terminal
(tty=False) and no escape codes are asserted against the live screen.
"""

from __future__ import annotations

import io

import pytest

from azarch import progress
from azarch.progress import ProgressBar


@pytest.fixture
def steps_log(tmp_path, monkeypatch):
    """Redirect paths.STEPS_LOG (opened in the ctor) into tmp_path and return it."""
    p = tmp_path / "steps.log"
    monkeypatch.setattr(progress.paths, "STEPS_LOG", p)
    return p


def make_bar(steps_log, weights, tty=False):
    """Construct a bar with STEPS_LOG already redirected (see the steps_log fixture)."""
    return ProgressBar(weights, tty=tty)


# --- construction / prefix sums -------------------------------------------

def test_init_prefix_sums(steps_log):
    # accum[i] must be the running sum of weights[1..i]; the bar reads accum[i-1]
    # as "weight completed before step i", so a bad prefix sum shifts every %.
    bar = make_bar(steps_log, [0, 2, 3, 5])
    assert bar.total_steps == 3
    assert bar.total_weight == 10
    assert bar.accum == [0, 2, 5, 10]


def test_init_starts_at_zero(steps_log):
    bar = make_bar(steps_log, [0, 2, 3, 5])
    assert bar.current == 0
    assert bar.done_weight == 0
    assert bar.cur_weight == 0
    assert bar.subfrac == 0
    assert bar.label == ""


# --- _layout: fill/percent width math -------------------------------------

def test_layout_bar_fill_at_80cols(steps_log):
    # done_weight=5 of total_weight=10 -> exactly 50%. At cols=80 the pct field is
    # "  50% " (6 cols), the bar gets 45% of the remaining 74 -> 33 cells, and
    # 50% of 33 rounds down to 16 filled / 17 empty.
    bar = make_bar(steps_log, [0, 2, 3, 5])
    bar.done_weight = 5
    bar.cur_weight = 0
    bar.subfrac = 0
    out = bar._layout(80)
    assert out.count("█") == 16   # filled block
    assert out.count("░") == 17   # light shade
    assert " 50% " in out


def test_layout_percent_string_is_three_wide(steps_log):
    # The pct is rendered "%3d" so it is always three columns; at 50% that is
    # a leading space -> "  50% " (two spaces before the digits).
    bar = make_bar(steps_log, [0, 2, 3, 5])
    bar.done_weight = 5
    out = bar._layout(80)
    assert "  50% " in out


def test_layout_pct_clamps_to_100(steps_log):
    # eff can exceed total_weight*1000 (done_weight overshoot); pct is min()'d to 100
    # so the field never widens past three digits and the bar never over-fills.
    bar = make_bar(steps_log, [0, 2, 3, 5])
    bar.done_weight = 20          # 200% of total_weight before clamping
    bar.cur_weight = 0
    bar.subfrac = 0
    out = bar._layout(80)
    assert " 100% " in out
    assert out.count("░") == 0   # bar fully filled, no empty cells


def test_layout_zero_total_weight_no_div_by_zero(steps_log):
    # total_weight==0 must short-circuit pct/filled to 0 rather than ZeroDivisionError.
    bar = make_bar(steps_log, [0])   # total_weight == 0
    out = bar._layout(80)
    assert "   0% " in out


def test_layout_never_exceeds_cols_visible_width(steps_log):
    # The visible (non-escape) width is budgeted from cols up front; assert the
    # printable characters never exceed the terminal width for a long label.
    bar = make_bar(steps_log, [0, 10])
    bar.done_weight = 0
    bar.cur_weight = 10
    bar.subfrac = 500
    bar.label = "a very long step label that would otherwise wrap the row entirely"
    out = bar._layout(40)
    # strip the ANSI escape sequences to count only visible columns
    import re
    visible = re.sub(r"\033\[[0-9;]*m", "", out)
    assert len(visible) <= 40


# --- _clip: off-by-one truncation boundary --------------------------------

def test_clip_boundary(steps_log, monkeypatch):
    # cols=10: a 10-char line is left alone (len>cols is False at equality); an
    # 11-char line becomes 9 chars + the one-char ellipsis, staying within 10.
    monkeypatch.setattr(progress.shutil, "get_terminal_size", lambda fallback=(80, 24): (10, 24))
    bar = make_bar(steps_log, [0, 5], tty=True)
    assert bar._clip("0123456789") == "0123456789"          # len 10, unchanged
    clipped = bar._clip("0123456789X")                        # len 11
    assert clipped == "012345678…"
    assert len(clipped) == 10


def test_clip_non_tty_returns_verbatim(steps_log):
    # Non-TTY output goes to a log/pipe, which must keep the full untruncated text.
    bar = make_bar(steps_log, [0, 5], tty=False)
    long = "x" * 500
    assert bar._clip(long) == long


# --- step(): milestone format + counter -----------------------------------

def test_step_advances_counter_and_weights(steps_log):
    bar = make_bar(steps_log, [0, 2, 3, 5])
    bar.step("Bootstrap")
    assert bar.current == 1
    assert bar.done_weight == 0        # accum[current-1] == accum[0] == 0
    assert bar.cur_weight == 2         # weights[1]
    assert bar.subfrac == 0
    assert bar.label == "Bootstrap"
    assert bar._base_label == "Bootstrap"


def test_step_milestone_written_to_steps_log(steps_log):
    # The milestone uses "%2d" for the step number, so step 1 of 3 renders as
    # "[  1/3 ] Bootstrap" (two spaces: one literal after '[', one from %2d).
    bar = make_bar(steps_log, [0, 2, 3, 5])
    bar.step("Bootstrap")
    # close so the append-mode file is flushed to disk before reading
    bar.cleanup()
    contents = steps_log.read_text(encoding="utf-8")
    assert contents.endswith("[  1/3 ] Bootstrap\n")


def test_step_second_step_uses_prefix_sum(steps_log):
    # After two steps, done_weight is the sum of the first step's weight (accum[1]).
    bar = make_bar(steps_log, [0, 2, 3, 5])
    bar.step("first")
    bar.step("second")
    assert bar.current == 2
    assert bar.done_weight == 2        # accum[1]
    assert bar.cur_weight == 3         # weights[2]


# --- sub(): monotonic clamp -----------------------------------------------

def test_sub_monotonic_and_clamped(steps_log):
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.sub(300)
    assert bar.subfrac == 300
    bar.sub(200)                       # lower -> ignored (monotonic)
    assert bar.subfrac == 300
    bar.sub(5000)                      # above 1000 -> clamped to 1000
    assert bar.subfrac == 1000
    bar.sub(-10)                       # below 0 -> clamped to 0, not > 1000, ignored
    assert bar.subfrac == 1000


def test_sub_done_snaps_to_full(steps_log):
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.sub(400)
    bar.sub_done()
    assert bar.subfrac == 1000


# --- phase(): sub-label prefix + separator --------------------------------

def test_phase_prefixes_base_label_with_separator(steps_log):
    # phase() must join the step's base label and the sub-phase with a U+203A
    # (single right-pointing angle quote) and NOT advance the step counter.
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.step("Pkg cache")
    before = bar.current
    bar.phase("downloading")
    assert bar.label == "Pkg cache › downloading"
    assert bar.current == before       # step counter unchanged


def test_phase_without_base_label_uses_sublabel_only(steps_log):
    # With no base label yet, phase() shows the sublabel bare (no leading separator).
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.phase("standalone")
    assert bar.label == "standalone"


def test_phase_writes_indented_subcheckpoint(steps_log):
    # The steps.log line for a phase is the indented "    -> <sublabel>" form.
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.step("Pkg cache")
    bar.phase("downloading")
    bar.cleanup()
    contents = steps_log.read_text(encoding="utf-8")
    assert "    -> downloading\n" in contents


# --- finalize(): non-TTY ASCII completion bar -----------------------------

def test_finalize_ascii_bar(steps_log, monkeypatch):
    # Non-TTY finalize prints a plain 40-cell '#/.' bar with no escapes so it is
    # safe in full.log. weights=[0,10] + one step -> 100%, all 40 cells filled.
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.step("Build")
    fake = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake)
    bar.finalize()
    assert fake.getvalue() == "[" + "#" * 40 + "] 100%  Build\n"


def test_finalize_partial_ascii_bar(steps_log, monkeypatch):
    # done_weight=5 of 10 with cur_weight=0 -> finalize forces cur to full slice;
    # eff = 5*1000 + 0*1000 = 5000 -> 50%, 20 of 40 cells filled.
    bar = make_bar(steps_log, [0, 5, 5], tty=False)
    bar.step("first")                  # done=0, cur=5
    bar.step("second")                 # done=5, cur=5
    # roll back cur_weight to 0 so finalize's eff = done*1000 + 0*1000
    bar.done_weight = 5
    bar.cur_weight = 0
    bar.label = "half"
    fake = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake)
    bar.finalize()
    out = fake.getvalue()
    assert out == "[" + "#" * 20 + "." * 20 + "]  50%  half\n"


# --- _log_step / cleanup: durability + swallowed errors --------------------

def test_log_step_appends_and_flushes(steps_log):
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar._log_step("checkpoint one")
    bar._log_step("checkpoint two")
    # flush happens inside _log_step; read without closing to prove real-time write
    contents = steps_log.read_text(encoding="utf-8")
    assert contents == "checkpoint one\ncheckpoint two\n"


def test_log_step_swallows_closed_file(steps_log):
    # Writing after close raises ValueError inside _log_step, which is swallowed
    # (the bar must never crash the build over a broken log handle).
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.steps_log.close()
    bar._log_step("after close")        # must not raise


def test_cleanup_is_idempotent_on_closed_log(steps_log):
    # cleanup closes steps_log inside a (ValueError, OSError) guard, so a second
    # cleanup (double-close) does not raise.
    bar = make_bar(steps_log, [0, 10], tty=False)
    bar.cleanup()
    bar.cleanup()                       # must not raise


# --- non-TTY guards: no escape codes emitted on draw/init ------------------

def test_non_tty_draw_and_init_noop(steps_log, monkeypatch):
    # On a non-TTY, draw()/init()/_arm() short-circuit so no cursor/scroll escapes
    # leak into a piped log. Assert nothing is written to sys.stdout by them.
    bar = make_bar(steps_log, [0, 10], tty=False)
    fake = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake)
    bar.init()
    bar.draw()
    assert fake.getvalue() == ""
