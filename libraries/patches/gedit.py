"""gedit "notepad mode" patch -- one window per file, NO tabs, minimal headerbar, Ctrl+W exits.

    WHY THIS EXISTS (the design intent, verbatim from the request)
    -------------------------------------------------------------
    This is inspired by Windows' old-school Notepad. gedit should be a BASIC,
    featureless application: it does not need features -- it is a simple tool that
    serves a very simple goal. Modern gedit's multi-tab approach does not fit Az'arch,
    a distribution that wants to "get out of the way". So: STRAIGHT UP REMOVE the
    multi-tab feature (open something twice -> ANOTHER WINDOW, never a tab), strip the
    headerbar down to ONLY the hamburger menu + the window controls (min/max/close),
    and make Ctrl+W a straight EXIT (close = close; no leftover empty window).

    THE FORK, AND WHY CONFIG FILES ALONE ARE NOT ENOUGH
    ---------------------------------------------------
    Az'arch ships gedit 50 -- the gedit-technology fork (GTK3, libgedit-amtk/tepl), NOT
    GNOME's GTK4 gedit. On this fork:
      * The tab bar is a GeditMultiNotebook; show-tabs-mode='never' hides the STRIP but
        the "New Tab" (win.new-tab) affordance and Ctrl+T still exist.
      * The headerbar is a GeditHeaderBar (a GtkHeaderBar built in C, NOT from any .ui or
        GSetting). Its Open / Open-recent / New-Tab / Save buttons cannot be removed by
        GTK CSS (GTK3 CSS has no display/visibility and cannot hide a GtkButton) nor by
        any GSetting.
      * win.close closes the current DOCUMENT and leaves an EMPTY window (the "double
        exit"); only the WM close button / app.quit terminate the process. No GSetting or
        accels file can rebind these GActions (the accels file feeds the legacy
        GtkAccelMap, which these GAction accelerators never consult).
      * Python plugin support was REMOVED in gedit 49.0 (verified: libpeas ships only the
        Lua loader here, and lua-lgi is not installed), so the classic Python plugins that
        would do this cannot load.
    The ONLY supported hook that can remove the New Tab action, strip the headerbar
    buttons and rebind Ctrl+W is a COMPILED libpeas plugin implementing
    GeditWindowActivatable, whose activate() fires once per window. Az'arch already
    compiles C for the application menu, so this fits the same pattern.

    WHAT WE SHIP (three system files, all root-owned) + one compiled plugin .so
    --------------------------------------------------------------------------
    A. The launcher override -- /usr/share/applications/org.gnome.gedit.desktop
       (desktop_entry()). The stock gedit launcher with:
         * Exec = `gedit --standalone --new-window %U`
             --standalone (-s): run gedit as its OWN process, NOT the single-instance
                 D-Bus service, so a launch can never fold into a running gedit's window.
             --new-window: a fresh top-level window per file.
         * DBusActivatable = false -- force the desktop launch to run that Exec line
             instead of the D-Bus Activate/Open path (which would route the file into the
             running instance as a tab). Load-bearing.
         * The two window/document Actions also run --standalone.
       Everything else (Icon, MimeType, Categories, Keywords, StartupNotify) kept as the
       gedit package ships it.

    B. The GSettings override -- /usr/share/glib-2.0/schemas/<name>.gschema.override
       (gschema_override()). A glib schema OVERRIDE (changes the DEFAULT of a key without
       editing the packaged schema, so a gedit upgrade cannot revert it). It sets:
         org.gnome.gedit.preferences.ui  show-tabs-mode = 'never'   (never draw a tab strip)
         org.gnome.gedit.plugins         active-plugins = [gedit defaults + 'azarch-notepad']
             so OUR notepad-mode plugin is enabled out of the box (added to gedit's own
             default plugin set, not replacing it). glib override files MUST be compiled
             (`glib-compile-schemas`); compiler.py and the live-apply path both run that
             (RUN_COMPILE_SCHEMAS is the single source of truth for the command).

    C. The plugin metadata -- /usr/lib/gedit/plugins/azarch-notepad.plugin
       (plugin_metadata(), read verbatim from the source tree). The libpeas .plugin INI
       that registers the module name so gedit lists/loads it.

    D. The compiled plugin -- /usr/lib/gedit/plugins/libazarch-notepad.so. NOT a content
       string: build_plugin() compiles gedit_plugin/azarch-notepad.c against the gedit +
       GTK3 + libpeas dev stack (pkg-config `gedit`) and installs the .so. compiler.py
       calls it during _emit_apps (like application_menu.build_daemon). Its activate():
         1. disables win.new-tab (the "+" button goes dead, Ctrl+T no-ops);
         2. hides the Open box (button + open-recent dropdown), the New-Tab "+" and the
            Save button, leaving ONLY the hamburger + window controls;
         3. replaces win.close with a destroy-the-window action and maps Ctrl+W to it, so
            Ctrl+W terminates the process cleanly (close = close, no empty window).

    NET EFFECT: gedit is a plain one-window-per-file editor with a Notepad-minimal
    headerbar and a Ctrl+W that exits. No tab bar, no tab routing, no single-instance
    folding, no New Tab, no Open/Save headerbar buttons, no double-exit.

    compiler.py iterates emit_plan() (builder/dest/mode/owner + the plugin-metadata entry)
    and calls build_plugin(); all shipped files are owner="root" SYSTEM files.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import paths

# --- Where the system files go ----------------------------------------------
# The gedit launcher (system-wide, one file for all users) and the glib schema override
# dir. Both root-owned; the OFFLINE Calamares install rsyncs the live rootfs, so they
# carry onto the installed system with no separate installer step.
DESKTOP_ENTRY_PATH = "/usr/share/applications/org.gnome.gedit.desktop"
GSCHEMA_OVERRIDE_PATH = "/usr/share/glib-2.0/schemas/90_azarch-gedit.gschema.override"

# The exact command that MUST be run after the override lands so glib recompiles the
# machine-readable gschemas.compiled (dropping the override file alone does nothing).
# compiler.py and the live-apply path both run this; kept here as the single source of
# truth so they cannot drift.
GLIB_SCHEMAS_DIR = "/usr/share/glib-2.0/schemas"
RUN_COMPILE_SCHEMAS = ["glib-compile-schemas", GLIB_SCHEMAS_DIR]

# The GSettings keys we override: hide the notebook tab bar entirely, and enable OUR
# notepad-mode plugin (added to gedit's own default plugin set).
GEDIT_UI_SCHEMA = "org.gnome.gedit.preferences.ui"
SHOW_TABS_MODE = "never"   # 'never' | 'auto' | 'always' (case-sensitive)
GEDIT_PLUGINS_SCHEMA = "org.gnome.gedit.plugins"
# gedit 50's shipped default active-plugins (from its gschema); we KEEP these and ADD ours,
# so notepad mode does not disable the editor's stock plugins.
GEDIT_DEFAULT_PLUGINS = ["filebrowser", "sort", "spell", "textsize"]
NOTEPAD_PLUGIN_MODULE = "azarch-notepad"      # the .plugin Module= / active-plugins id
ACTIVE_PLUGINS = GEDIT_DEFAULT_PLUGINS + [NOTEPAD_PLUGIN_MODULE]

# --- The compiled libpeas plugin (notepad mode) -----------------------------
# The plugin source tree (C + Makefile + .plugin), built by build_plugin() into the .so.
# It lives beside this module under patches/gedit_plugin/ (the same "sources next to the
# build-wiring module" layout the application-menu package uses).
GEDIT_PLUGIN_SRC_DIR = paths.PATCHESDIR / "gedit_plugin"
GEDIT_PLUGIN_SO_NAME = "libazarch-notepad.so"           # the built shared object
GEDIT_PLUGIN_SO_DEST = f"/usr/lib/gedit/plugins/{GEDIT_PLUGIN_SO_NAME}"
GEDIT_PLUGIN_METADATA_NAME = "azarch-notepad.plugin"    # the libpeas .plugin INI
GEDIT_PLUGIN_METADATA_DEST = f"/usr/lib/gedit/plugins/{GEDIT_PLUGIN_METADATA_NAME}"

# Host BUILD dependencies for compiling the plugin (Arch package names). Present on the
# build HOST only (NOT shipped in the ISO -- the live system carries the compiled .so plus
# the gedit + GTK3 + libpeas RUNTIME libs, already in the manifest). gedit provides the
# `gedit` pkg-config module (pulling in gtk+-3.0 and libpeas-1.0); base-devel provides gcc.
GEDIT_PLUGIN_BUILD_DEPS = ["gedit", "gcc", "pkgconf"]


def desktop_entry() -> str:
    """/usr/share/applications/org.gnome.gedit.desktop -- the notepad-mode launcher.

    The stock gedit launcher with Exec forced to `--standalone --new-window` and
    DBusActivatable=false, so every open is an independent new window (never a tab in a
    running instance). All other fields are kept as the gedit package ships them (see the
    module docstring). The two right-click Actions also run standalone."""
    return """\
[Desktop Entry]
# Az'arch notepad-mode gedit launcher. Generated by patches/gedit.py (edit the Python,
# not this file). Exec forces --standalone --new-window and DBusActivatable is false so
# opening a file always makes a NEW WINDOW (never a tab in a running gedit). Everything
# else is stock gedit.
Name=gedit
Comment=Edit text files
# --standalone: own process, not the single-instance D-Bus service; --new-window: fresh
# top-level window. Together: open a file -> new window; open another -> another window.
Exec=gedit --standalone --new-window %U
Terminal=false
Type=Application
StartupNotify=true
MimeType=text/plain;application/x-zerosize;
Icon=org.gnome.gedit
Categories=GNOME;GTK;Utility;TextEditor;
Actions=new-window;new-document;
# DBusActivatable=false is load-bearing: with it true, the desktop launch routes files
# over D-Bus into the RUNNING gedit as tabs and IGNORES the Exec flags above.
DBusActivatable=false
Keywords=Text;Editor;Plaintext;Write;gedit;

[Desktop Action new-window]
Name=New Window
Exec=gedit --standalone --new-window

[Desktop Action new-document]
Name=New Document
Exec=gedit --standalone --new-document
"""


def gschema_override() -> str:
    """/usr/share/glib-2.0/schemas/90_azarch-gedit.gschema.override -- hide the tab bar
    AND enable the notepad-mode plugin.

    A glib schema override: sets the DEFAULTS of two keys without editing the packaged
    schema (so a gedit upgrade cannot revert them):
      * org.gnome.gedit.preferences.ui show-tabs-mode = 'never' (never draw a tab strip)
      * org.gnome.gedit.plugins active-plugins = gedit's defaults + 'azarch-notepad'
        (enable OUR plugin out of the box without dropping gedit's stock plugins).
    MUST be compiled afterwards with `glib-compile-schemas` (see RUN_COMPILE_SCHEMAS) or it
    has no effect. The 90_ prefix sorts it AFTER the stock schema so our values win."""
    plugins_literal = "[" + ", ".join(f"'{p}'" for p in ACTIVE_PLUGINS) + "]"
    return f"""\
# Az'arch gedit override -- notepad mode. Generated by patches/gedit.py (edit the Python,
# not this file). Requires `glib-compile-schemas {GLIB_SCHEMAS_DIR}` to take effect.
# show-tabs-mode: never draw the notebook tab strip.
# active-plugins: gedit's default plugins PLUS azarch-notepad (removes New Tab, strips the
#   headerbar to hamburger + window controls, makes Ctrl+W exit).
[{GEDIT_UI_SCHEMA}]
show-tabs-mode='{SHOW_TABS_MODE}'

[{GEDIT_PLUGINS_SCHEMA}]
active-plugins={plugins_literal}
"""


def plugin_metadata() -> str:
    """/usr/lib/gedit/plugins/azarch-notepad.plugin -- the libpeas .plugin INI, read
    verbatim from the source tree (single source of truth). Registers the module name so
    gedit lists/loads the compiled plugin. The active-plugins override (above) enables it."""
    return (GEDIT_PLUGIN_SRC_DIR / GEDIT_PLUGIN_METADATA_NAME).read_text(encoding="utf-8")


# --- Build the plugin .so ---------------------------------------------------
# The plugin is COMPILED, not copied. compiler._emit_apps calls build_plugin() during the
# app emit; it runs `make` against a private copy of the C sources (so the repo tree is
# never dirtied with .o/.so artifacts) and installs the resulting .so into the airootfs.
def _plugin_src_files() -> list[Path]:
    """The plugin build inputs (C sources + Makefile) copied into the scratch build dir."""
    d = GEDIT_PLUGIN_SRC_DIR
    names = sorted(
        p.name
        for p in d.iterdir()
        if p.is_file() and (p.suffix in (".c", ".h") or p.name == "Makefile")
    )
    return [d / n for n in names]


def build_plugin(dest: Path, *, make: str = "make") -> Path:
    """Compile the libpeas notepad-mode plugin and install the .so at `dest`.

    Builds in a throwaway temp dir populated with a copy of the C sources (NOT in the repo,
    so no object/.so file ever lands in version control), then copies the produced .so to
    `dest` with mode 0755. Raises CalledProcessError if the build fails -- a broken plugin
    MUST fail the ISO build loudly rather than ship gedit without notepad mode. Returns the
    destination path."""
    dest = Path(dest)
    with tempfile.TemporaryDirectory(prefix="azarch-gedit-plugin-build-") as tmp:
        build_dir = Path(tmp)
        for src in _plugin_src_files():
            shutil.copy2(src, build_dir / src.name)
        subprocess.run([make, GEDIT_PLUGIN_SO_NAME], cwd=build_dir, check=True)
        built = build_dir / GEDIT_PLUGIN_SO_NAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dest)
        dest.chmod(0o755)
    return dest


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode -> owner), the same shape compiler.py
# iterates for patches/openbox and patches/librewolf. Three root-owned SYSTEM files
# (plain data, 0o644): the launcher override, the glib schema override, and the plugin
# metadata. The override entry carries "compile_schemas" so compiler.py re-runs
# glib-compile-schemas. The compiled plugin .so is installed separately by build_plugin().
_CONF = 0o644


def emit_plan() -> list[dict]:
    """Return the emit plan for notepad-mode gedit: the launcher override, the glib schema
    override (show-tabs-mode + active-plugins; carries compile_schemas), and the plugin
    metadata .plugin file.

    Shape matches openbox.emit_plan()/librewolf.emit_plan() (builder/dest/mode/owner), with
    the "compile_schemas" flag on the override entry. The compiled plugin .so itself is NOT
    in this plan -- it is produced by build_plugin() (compiler._emit_apps calls it), because
    it is compiled by `make`, not read as a content string. Returns FRESH dicts so a caller
    cannot mutate module state."""
    return [
        {
            "builder": desktop_entry,
            "dest": DESKTOP_ENTRY_PATH,
            "mode": _CONF,
            "owner": "root",
        },
        {
            "builder": gschema_override,
            "dest": GSCHEMA_OVERRIDE_PATH,
            "mode": _CONF,
            "owner": "root",
            "compile_schemas": True,
        },
        {
            "builder": plugin_metadata,
            "dest": GEDIT_PLUGIN_METADATA_DEST,
            "mode": _CONF,
            "owner": "root",
        },
    ]
