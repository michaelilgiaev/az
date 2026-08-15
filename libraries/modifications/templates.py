"""~/Templates -- the "Create Document" template set for Thunar (PROMPT batch item 8).

Thunar populates its "Create New Document..." submenu from the XDG templates dir: every FILE
in ~/Templates (the dir named by XDG_TEMPLATES_DIR in ~/.config/user-dirs.dirs) becomes a
"Create Document -> <that file's name>" entry that COPIES the template into the current folder.
Out of the box Az'arch shipped no templates AND user-dirs.dirs pointed XDG_TEMPLATES_DIR at the
whole home dir ("$HOME/"), so the submenu was effectively empty (just the "About Templates"
placeholder, now also disabled in modifications/thunar/settings). This module fixes both:

  1. Ships a useful TEMPLATE SET in ~/Templates:
       * "Text Document.txt"          -- a plain empty UTF-8 text file.
       * "LibreOffice Writer.odt"     -- a minimal, VALID empty ODF text document.
       * "LibreOffice Calc.ods"       -- a minimal, VALID empty ODF spreadsheet.
       * "LibreOffice Impress.odp"    -- a minimal, VALID empty ODF presentation.
     The ODF files are generated here as proper ODF ZIP packages (mimetype stored FIRST and
     UNCOMPRESSED per the ODF spec, plus the minimal manifest + content/styles/meta parts) so
     LibreOffice opens the copy cleanly rather than complaining about a 0-byte file.
  2. Ships ~/.config/user-dirs.dirs with XDG_TEMPLATES_DIR="$HOME/Templates" (and the other
     XDG dirs matching the Az'arch home layout) so Thunar (via g_get_user_special_dir) finds
     the templates dir. Without this, xdg-user-dirs-update would regenerate the stock file with
     XDG_TEMPLATES_DIR="$HOME/" and Thunar would scan all of $HOME.

CREATE LINK IN THE CREATE-NEW FLOW. The user wants "Create Link" reachable from the Create-New
flow. A template is a file that gets COPIED, so it cannot run the interactive zenity name/target
prompt the link needs; the supported route is the uca.xml "Create Link" custom action (kept in
modifications/thunar/actions), which appears on the folder background right where Create New
Folder/Document are. So Create Link IS present in that same right-click flow.

WHERE IT GOES. All HOME files (owner "home", skel-mirrored) -- the templates and user-dirs.dirs
belong to the user. compiler emits this module's emit_plan() alongside the others; the ODF
templates ride the bytes_builder plan-entry kind (binary), the text ones the normal builder.
The Templates directory itself is created by compiler._emit_homedir (home_directory.TEMPLATES).
"""

from __future__ import annotations

import io
import zipfile

# The live user's home (matches openbox.HOME / the airootfs /home/main tree).
HOME = "/home/main"

# The templates directory (created by compiler._emit_homedir from home_directory.TEMPLATES).
TEMPLATES_DIRNAME = "Templates"
TEMPLATES_DIR = f"{HOME}/{TEMPLATES_DIRNAME}"

# ~/.config/user-dirs.dirs -- XDG user dirs. The load-bearing line is
# XDG_TEMPLATES_DIR="$HOME/Templates" (so Thunar finds the templates); the rest mirror the
# Az'arch home layout (home_directory.DIRECTORIES) so xdg-aware apps land in the right folders.
USER_DIRS_PATH = f"{HOME}/.config/user-dirs.dirs"


def user_dirs_dirs() -> str:
    """Return ~/.config/user-dirs.dirs. Points XDG_TEMPLATES_DIR at ~/Templates (PROMPT batch
    item 8) so Thunar's Create Document submenu reads our template set, and maps the other XDG
    dirs to the Az'arch home layout. The `# written by xdg-user-dirs-update` banner is kept so
    xdg-user-dirs-update treats it as its own file and preserves these values (it only rewrites
    missing lines)."""
    return (
        "# This file is written by xdg-user-dirs-update\n"
        "# Az'arch ships it (modifications/templates) so XDG_TEMPLATES_DIR points at ~/Templates\n"
        "# (Thunar's Create Document submenu reads that dir). Format is XDG_xxx_DIR=\"$HOME/yyy\".\n"
        'XDG_DESKTOP_DIR="$HOME/Desktop"\n'
        'XDG_DOWNLOAD_DIR="$HOME/Downloads"\n'
        'XDG_TEMPLATES_DIR="$HOME/Templates"\n'
        'XDG_PUBLICSHARE_DIR="$HOME/"\n'
        'XDG_DOCUMENTS_DIR="$HOME/Documents"\n'
        'XDG_MUSIC_DIR="$HOME/Music"\n'
        'XDG_PICTURES_DIR="$HOME/Pictures"\n'
        'XDG_VIDEOS_DIR="$HOME/Videos"\n'
    )


# --- The plain-text template ---------------------------------------------------
TEXT_TEMPLATE_NAME = "Text Document.txt"


def text_template() -> str:
    """A plain empty text document template (an empty UTF-8 file). Thunar copies it as the new
    document; the user then types into it."""
    return ""


# --- The ODF (LibreOffice) templates -------------------------------------------
# ODF is a ZIP package. Two hard rules make the file valid (and openable by LibreOffice):
#   1. The FIRST entry MUST be `mimetype`, STORED (uncompressed), with no extra field, so the
#      magic bytes sit at a fixed offset (this is how the format is sniffed).
#   2. A META-INF/manifest.xml lists the parts and the document mimetype.
# We add minimal content.xml / styles.xml / meta.xml so LibreOffice sees a well-formed, empty
# document of the right type. The three document classes differ only by their ODF mimetype and
# the root body element in content.xml.

# (extension, ODF mimetype, the content.xml <office:body> inner element).
_ODF_KINDS: tuple[tuple[str, str, str, str], ...] = (
    ("LibreOffice Writer.odt",
     "application/vnd.oasis.opendocument.text",
     "text", "<text:p/>"),
    ("LibreOffice Calc.ods",
     "application/vnd.oasis.opendocument.spreadsheet",
     "spreadsheet",
     '<table:table table:name="Sheet1"><table:table-row><table:table-cell/>'
     "</table:table-row></table:table>"),
    ("LibreOffice Impress.odp",
     "application/vnd.oasis.opendocument.presentation",
     "presentation",
     '<draw:page draw:name="Slide 1"/>'),
)

_MANIFEST_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">
 <manifest:file-entry manifest:full-path="/" manifest:version="1.3" manifest:media-type="{mime}"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""

# One content.xml template; the office:body wraps the class-specific root element. The xmlns
# set is broad enough to cover all three document classes' body elements.
_CONTENT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" \
xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" \
xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" \
xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" office:version="1.3">
 <office:body>
  <office:{cls}>{body}</office:{cls}>
 </office:body>
</office:document-content>
"""

_STYLES_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" \
office:version="1.3"><office:styles/></office:document-styles>
"""

_META_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" \
xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" office:version="1.3">
 <office:meta><meta:generator>Az'arch templates</meta:generator></office:meta>
</office:document-meta>
"""


def odf_bytes(mime: str, cls: str, body: str) -> bytes:
    """Return a minimal, valid ODF package (a ZIP) for the given document class. The `mimetype`
    entry is written FIRST and STORED (uncompressed) as the ODF spec requires; the rest are
    deflated. Deterministic (fixed member order, fixed ZipInfo dates) so a test can pin it."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # 1. mimetype -- MUST be first and STORED (uncompressed), no extra field.
        mt = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
        mt.compress_type = zipfile.ZIP_STORED
        zf.writestr(mt, mime)
        # 2. the manifest + the three content parts (deflated is fine for these).
        def _add(name: str, text: str) -> None:
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, text)
        _add("META-INF/manifest.xml", _MANIFEST_XML.format(mime=mime))
        _add("content.xml", _CONTENT_XML.format(cls=cls, body=body))
        _add("styles.xml", _STYLES_XML)
        _add("meta.xml", _META_XML)
    return buf.getvalue()


def _odf_builder(mime: str, cls: str, body: str):
    """Return a zero-arg callable producing this ODF template's bytes (for the plan)."""
    return lambda: odf_bytes(mime, cls, body)


def template_names() -> list[str]:
    """The file names shipped into ~/Templates, in order (text first, then the ODF trio)."""
    return [TEXT_TEMPLATE_NAME] + [name for name, _m, _c, _b in _ODF_KINDS]


_CONF = 0o644


def emit_plan() -> list[dict]:
    """Return the emit plan for the templates + user-dirs.dirs. All HOME files (owner "home",
    skel-mirrored): the text template + user-dirs.dirs as normal text builders, the ODF trio as
    bytes_builder (binary) entries. compiler._emit_apps writes them (the Templates DIRECTORY is
    created separately by _emit_homedir from home_directory.TEMPLATES)."""
    plan: list[dict] = [
        {
            "builder": user_dirs_dirs,
            "dest": USER_DIRS_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {
            "builder": text_template,
            "dest": f"{TEMPLATES_DIR}/{TEXT_TEMPLATE_NAME}",
            "mode": _CONF,
            "owner": "home",
        },
    ]
    for name, mime, cls, body in _ODF_KINDS:
        plan.append({
            "builder": None,
            "bytes_builder": _odf_builder(mime, cls, body),
            "dest": f"{TEMPLATES_DIR}/{name}",
            "mode": _CONF,
            "owner": "home",
        })
    return plan
