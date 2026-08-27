"""The `azarch-sshd` build variant: the second ISO a single build produces,
identical to the base one but named azarch-sshd-<ver>-x86_64.iso and auto-running
`azarch --sshd-hypervisor` at boot.

A single `compile.sh` run builds BOTH ISOs (there is no build-time flag to pick
one): every step up to mkarchiso is variant-independent, so the flow is
compile.sh -> compiler.py -> compiler.run(), which loops over compiler.VARIANTS
("base", "sshd") applying each variant's tiny differences via compiler._apply_variant
and running one mkarchiso pass each.

The two observable per-variant effects, both checked here as pure data/emit (no
mkarchiso):

  1. profiledef's iso_name flips azarch -> azarch-sshd, so mkarchiso writes the
     azarch-sshd-*.iso filename the prompt asked for.
  2. _apply_variant emits + enables sshd-hypervisor-setup.service (a systemd
     oneshot that runs `azarch --sshd-hypervisor`) ONLY for the sshd variant; the
     base ISO gets NEITHER the unit nor its enable link, so there it stays a manual
     `sudo azarch --sshd-hypervisor`.

A drift in any of these silently ships the wrong ISO name or an sshd ISO that does
NOT actually start sshd on boot (or a base ISO that unexpectedly does).
"""

from __future__ import annotations

import inspect
import os
import re

import pytest

import compiler
import profile
import system


# --- VARIANTS is the canonical MAX set; the sshd ISO is OPT-IN ----------------

def test_variants_are_base_and_sshd():
    # VARIANTS is the canonical MAXIMUM set a build can produce (base first). It sizes
    # the progress bar's two mkarchiso weights. Which variants ACTUALLY build is decided
    # at runtime by _variants_for(): base always, sshd only with --ssh (see below).
    assert compiler.VARIANTS == ("base", "sshd")


# --- Method A: the --ssh=<PASSWORD> build-time flag --------------------------

def test_parse_ssh_flag_absent_is_none():
    # No flag -> no sshd ISO. An empty/missing string "demands a string or it doesn't
    # work": the flag must be present AND non-empty to opt in.
    assert compiler.parse_ssh_flag([]) is None
    assert compiler.parse_ssh_flag(["--full-compile"]) is None


def test_parse_ssh_flag_empty_value_is_none():
    # `--ssh=` with a blank value is treated as absent (no sshd ISO), never as a blank
    # password. This is the "empty string -> no sshd ISO" rule.
    assert compiler.parse_ssh_flag(["--ssh="]) is None


def test_parse_ssh_flag_returns_password():
    assert compiler.parse_ssh_flag(["--ssh=hunter2"]) == "hunter2"
    # Order-independent, and coexists with other flags.
    assert compiler.parse_ssh_flag(["--full-compile", "--ssh=s3cret"]) == "s3cret"


def test_parse_ssh_flag_preserves_equals_in_password():
    # split("=", 1): a password containing '=' must NOT be truncated (the CLI precedent
    # in command_line_interface.py uses the same rule).
    assert compiler.parse_ssh_flag(["--ssh=a=b=c"]) == "a=b=c"


def test_ssh_password_hash_produces_sha512_crypt():
    # The supplied password is stored as a proper sha-512 crypt hash ($6$...), never
    # plaintext, never blank. openssl passwd -6 emits $6$ for sha-512.
    import shutil
    import subprocess
    if not shutil.which("openssl"):
        pytest.skip("openssl not available on this host")
    password = "correct horse battery staple"
    h = compiler.ssh_password_hash(password)
    assert h.startswith("$6$")
    # A real crypt hash has three '$'-delimited parts: $6$salt$digest.
    assert h.count("$") >= 3
    # Round-trip: re-hashing the same password with the SAME salt reproduces the hash
    # (proves it verifies). Python's crypt module is gone as of 3.13, so verify via
    # openssl with the salt extracted from the hash.
    salt = h.split("$")[2]
    again = subprocess.run(
        ["openssl", "passwd", "-6", "-salt", salt, "-stdin"],
        input=password, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert again == h


def test_ssh_password_hash_rejects_blank():
    # An empty password can never be hashed into the image (belt-and-suspenders on top
    # of parse_ssh_flag returning None for "").
    with pytest.raises(ValueError):
        compiler.ssh_password_hash("")


# --- run() selects variants at runtime from the ssh hash ---------------------

def test_variants_for_base_only_without_ssh():
    # No ssh hash -> ONLY the base ISO is built (the sshd ISO is opt-in).
    assert compiler._variants_for(None) == ("base",)


def test_variants_for_includes_sshd_with_hash():
    # A real hash -> both the base and the sshd ISO, base first (VARIANTS order).
    assert compiler._variants_for("$6$salt$digest") == ("base", "sshd")


def test_run_threads_ssh_hash_into_variant_selection():
    # run() must build the runtime-selected variants (not the static VARIANTS tuple)
    # and thread the ssh hash into the shadow it writes.
    src = inspect.getsource(compiler.run)
    assert "_variants_for(" in src, "run() must pick variants at runtime from the ssh hash"
    assert "shadow_for(" in src, "run() must write the variant's shadow via system.shadow_for"


def test_run_signature_takes_ssh_password_hash():
    # The build-time password (already hashed) is plumbed into run() as a keyword arg.
    params = inspect.signature(compiler.run).parameters
    assert "ssh_password_hash" in params


def test_apply_variant_sshd_requires_a_hash(tmp_path):
    # Emitting the sshd variant without a password hash is a programming error: the
    # sshd ISO must NEVER be built with the base (locked) shadow -- that would ship an
    # sshd nobody can log into, or worse, hide that the credential was dropped.
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    with pytest.raises(ValueError):
        compiler._apply_variant(W, airootfs, "sshd", ssh_password_hash=None)


def test_apply_variant_sshd_writes_hashed_shadow(tmp_path):
    # The sshd variant's airootfs /etc/shadow must carry the real hash for `main`
    # (never blank, never the base locked value).
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    fake_hash = "$6$abcdefghijklmnop$" + "x" * 86
    compiler._apply_variant(W, airootfs, "sshd", ssh_password_hash=fake_hash)
    shadow = (airootfs / "etc/shadow").read_text()
    main_line = next(l for l in shadow.splitlines() if l.startswith("main:"))
    assert main_line.split(":")[1] == fake_hash
    # root stays locked in the sshd variant too.
    root_line = next(l for l in shadow.splitlines() if l.startswith("root:"))
    assert root_line.split(":")[1] in ("!", "*")


def test_apply_variant_base_writes_locked_shadow(tmp_path):
    # The base variant must (re)write the LOCKED shadow -- so even if a prior sshd pass
    # left a hashed shadow in the shared airootfs, the base ISO ships locked accounts.
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    fake_hash = "$6$abcdefghijklmnop$" + "x" * 86
    compiler._apply_variant(W, airootfs, "sshd", ssh_password_hash=fake_hash)  # leaves hashed shadow
    compiler._apply_variant(W, airootfs, "base", ssh_password_hash=fake_hash)  # base pass must relock
    shadow = (airootfs / "etc/shadow").read_text()
    for line in shadow.splitlines():
        assert line.split(":")[1] in ("!", "*"), f"base shadow must be locked: {line}"


# --- profiledef iso_name per variant ----------------------------------------

def _iso_name(pd: str) -> str:
    m = re.search(r'iso_name="([^"]+)"', pd)
    assert m, "profiledef has no iso_name"
    return m.group(1)


def test_iso_name_for_maps_variants():
    assert profile.iso_name_for("base") == "azarch"
    assert profile.iso_name_for("sshd") == "azarch-sshd"
    # An unknown variant must fall back to the base name, never crash the build.
    assert profile.iso_name_for("nonsense") == "azarch"
    assert profile.iso_name_for() == "azarch"


def test_profiledef_base_is_azarch():
    assert _iso_name(profile.profiledef_sh("base")) == "azarch"
    # Default (no arg) is the base ISO.
    assert _iso_name(profile.profiledef_sh()) == "azarch"


def test_profiledef_sshd_is_azarch_sshd():
    # This is what makes mkarchiso name the artifact azarch-sshd-<ver>-x86_64.iso.
    assert _iso_name(profile.profiledef_sh("sshd")) == "azarch-sshd"


def test_only_iso_name_differs_between_variants():
    # The variants must be otherwise byte-identical: same bootmodes, permissions,
    # squashfs options, everything. Normalizing the one iso_name line makes the rest
    # comparable, proving the variant changes ONLY the name (packages/behaviour
    # parity is what "basically like the normal one" requires).
    base = profile.profiledef_sh("base")
    sshd = profile.profiledef_sh("sshd")
    norm = lambda s: s.replace('iso_name="azarch-sshd"', 'iso_name="azarch"')
    assert norm(sshd) == base


# --- the auto-setup systemd unit --------------------------------------------

def test_sshd_service_runs_the_cli_subcommand():
    svc = system.SSHD_HYPERVISOR_SETUP_SERVICE
    # It must invoke exactly the documented subcommand -- this IS "on by default".
    assert "ExecStart=/usr/local/bin/azarch --sshd-hypervisor" in svc


def test_sshd_service_targets_main_via_sudo_user():
    # Run as root with SUDO_USER=main: the azarch command line interface keys off ${SUDO_USER:-...} and
    # refuses a bare-root target, so this is what makes the pubkey land in
    # /home/main/.ssh (the account sshd accepts) without needing a PAM session.
    svc = system.SSHD_HYPERVISOR_SETUP_SERVICE
    assert "Environment=SUDO_USER=main" in svc
    assert "Type=oneshot" in svc


def test_sshd_service_ordering_is_sane():
    svc = system.SSHD_HYPERVISOR_SETUP_SERVICE
    # After pkgs-setup (whose `ufw enable` default-denies incoming) so our
    # `ufw allow ssh` wins and :22 is reachable.
    assert "After=pkgs-setup.service" in svc
    assert "WantedBy=multi-user.target" in svc
    # MUST NOT order after the target that pulls it in (anti-pattern / cycle risk).
    assert "After=multi-user.target" not in svc


def test_sshd_service_guarded_on_cli_presence():
    # ConditionPathExists keeps it from failing loudly if the azarch command line interface is absent.
    assert "ConditionPathExists=/usr/local/bin/azarch" in system.SSHD_HYPERVISOR_SETUP_SERVICE


# --- always-on links: identical for both variants ---------------------------

def _link_dest(airootfs):
    return (airootfs / "etc/systemd/system/multi-user.target.wants"
            / "sshd-hypervisor-setup.service")


def test_link_services_never_creates_the_sshd_link(tmp_path):
    # _link_services now only enables the variant-INDEPENDENT daemons; the sshd
    # enable-link is applied per-variant by _apply_variant, never here.
    root = tmp_path / "root"
    compiler._link_services(root)
    assert not _link_dest(root).is_symlink()
    # The three always-on daemon links ARE created (sanity that the helper ran).
    always = root / "etc/systemd/system/multi-user.target.wants/NetworkManager.service"
    assert always.is_symlink()


# --- compiler._apply_variant: emit + enable only for the sshd variant ----------

def _svc_dest(airootfs):
    return airootfs / "etc/systemd/system/sshd-hypervisor-setup.service"


def test_apply_variant_sshd_emits_and_enables_service(tmp_path):
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    compiler._apply_variant(W, airootfs, "sshd", ssh_password_hash="$6$s$" + "x" * 86)
    # The unit file is written...
    svc = _svc_dest(airootfs)
    assert svc.is_file()
    assert "azarch --sshd-hypervisor" in svc.read_text()
    # ...and enabled via a multi-user.target.wants symlink to it.
    link = _link_dest(airootfs)
    assert link.is_symlink()
    assert os.readlink(link) == "/etc/systemd/system/sshd-hypervisor-setup.service"
    # profiledef at the profile root carries the sshd iso_name.
    assert _iso_name((W / "profiledef.sh").read_text()) == "azarch-sshd"


def test_apply_variant_base_has_no_sshd_service_or_link(tmp_path):
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    compiler._apply_variant(W, airootfs, "base", ssh_password_hash=None)
    assert not _svc_dest(airootfs).exists()
    assert not _link_dest(airootfs).is_symlink()
    assert _iso_name((W / "profiledef.sh").read_text()) == "azarch"


def test_apply_variant_base_after_sshd_removes_the_leftover(tmp_path):
    # The finalize loop reuses ONE shared airootfs across passes. If sshd were built
    # before base, base's pass MUST strip the sshd unit + enable link the sshd pass
    # left behind -- otherwise the base ISO would silently auto-start sshd too. Assert
    # _apply_variant("base") affirmatively removes both even when they pre-exist.
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    hh = "$6$s$" + "x" * 86
    compiler._apply_variant(W, airootfs, "sshd", ssh_password_hash=hh)  # leave the sshd artifacts
    assert _svc_dest(airootfs).is_file()
    assert _link_dest(airootfs).is_symlink()
    compiler._apply_variant(W, airootfs, "base", ssh_password_hash=hh)  # base pass must clean them up
    assert not _svc_dest(airootfs).exists()
    assert not _link_dest(airootfs).is_symlink()


def test_run_signature_has_no_variant_param():
    # There is no build-time variant flag anymore: run() always builds both ISOs, so
    # it must NOT take a `variant` argument (a stray one would resurrect the old
    # one-ISO-per-run behaviour).
    import inspect
    params = inspect.signature(compiler.run).parameters
    assert "variant" not in params


def test_run_calls_mkarchiso_once_per_variant():
    # run() must invoke _run_mkarchiso once per variant (both ISOs in one build), and
    # append each returned ISO. Assert the finalize loop iterates VARIANTS and calls
    # _run_mkarchiso inside it.
    src = inspect.getsource(compiler.run)
    # Iterates the RUNTIME-selected variants (base always; sshd only with --ssh), not
    # the static VARIANTS tuple.
    assert "for variant in " in src
    assert "_variants_for(" in src
    assert "_run_mkarchiso(" in src
    assert "_apply_variant(" in src


def test_mkarchiso_pass_resets_work_dir_before_running():
    # THE two-variant integration hazard: mkarchiso guards every build step with a
    # `_run_once` sentinel file under work/ (work/base.<fn>, work/iso.<fn>) and refuses
    # to delete a pre-existing work dir. If the second (sshd) pass reused the first
    # pass's work/, mkarchiso would skip airootfs/squashfs/ISO-write as "already done"
    # and NEVER write azarch-sshd-*.iso. So each pass MUST wipe work/ before invoking
    # mkarchiso. Assert the reset (rm -rf of the work dir) happens in _run_mkarchiso
    # BEFORE the mkarchiso subprocess is spawned.
    import inspect
    src = inspect.getsource(compiler._run_mkarchiso)
    # A work-dir wipe must be present...
    assert 'rm", "-rf"' in src and 'W / "work"' in src, \
        "_run_mkarchiso must rm -rf the work dir so each variant is a fresh mkarchiso pass"
    # ...and it must come BEFORE the mkarchiso invocation (else the sentinels from a
    # prior pass are still present when mkarchiso decides what to skip).
    reset_at = src.index('"work"')
    mkarchiso_at = src.index('"mkarchiso"')
    assert reset_at < mkarchiso_at, "work/ must be reset BEFORE mkarchiso runs"


def test_iso_selection_glob_distinguishes_base_from_sshd():
    # output/ can hold BOTH azarch-*.iso and azarch-sshd-*.iso. The base pass must
    # never pick up the sshd ISO. mkarchiso names artifacts <iso_name>-<YYYY.MM.DD>-
    # <arch>.iso, so anchoring the glob with a digit after "{iso_name}-" separates
    # them ("azarch-2026..." matches base; "azarch-sshd-..." does not, since 's' is
    # not a digit). Emulate the exact glob _run_mkarchiso uses and assert the split.
    import fnmatch
    both = ["azarch-2026.07.31-x86_64.iso", "azarch-sshd-2026.07.31-x86_64.iso"]
    base_hits = [f for f in both if fnmatch.fnmatch(f, "azarch-[0-9]*.iso")]
    sshd_hits = [f for f in both if fnmatch.fnmatch(f, "azarch-sshd-[0-9]*.iso")]
    assert base_hits == ["azarch-2026.07.31-x86_64.iso"]
    assert sshd_hits == ["azarch-sshd-2026.07.31-x86_64.iso"]
    # And the source really uses the digit-anchored glob (not a bare "-*.iso").
    import inspect
    src = inspect.getsource(compiler._run_mkarchiso)
    assert '{iso_name}-[0-9]*.iso' in src
