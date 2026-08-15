"""modifications.templates -- the ~/Templates "Create Document" set for Thunar (PROMPT batch 8).

Why these tests matter: Thunar populates its Create Document submenu from ~/Templates, and the
LibreOffice templates must be VALID ODF packages (mimetype stored first + a manifest) or
LibreOffice refuses to open the copy. These pin: the template SET, the XDG_TEMPLATES_DIR
pointer, that the ODF files are real ZIP/ODF packages, and the emit-plan wiring (HOME,
skel-mirrored, ODF as binary).
"""

from __future__ import annotations

import io
import zipfile

from modifications import templates
from modifications import home_directory


def test_templates_dir_is_created_by_home_layout():
    # ~/Templates is an EXTRA (non-sidebar) home directory so it is created + skel-mirrored,
    # but does NOT appear in the sidebar shortcut set.
    assert "Templates" in home_directory.EXTRA_DIRECTORIES
    assert "Templates" not in home_directory.DIRECTORIES  # not a sidebar shortcut
    assert templates.TEMPLATES_DIR == "/home/main/Templates"


def test_template_set_covers_text_and_libreoffice_trio():
    # PROMPT: at minimum a plain TEXT document + a LibreOffice document (Writer; plus Calc,
    # Impress here).
    names = templates.template_names()
    assert "Text Document.txt" in names
    assert "LibreOffice Writer.odt" in names
    assert "LibreOffice Calc.ods" in names
    assert "LibreOffice Impress.odp" in names


def test_user_dirs_points_templates_at_templates_dir():
    # PROMPT batch item 8: XDG_TEMPLATES_DIR must be ~/Templates (else Thunar scans all of
    # $HOME, the stock xdg-user-dirs default) so the Create Document submenu finds our set.
    u = templates.user_dirs_dirs()
    assert 'XDG_TEMPLATES_DIR="$HOME/Templates"' in u
    assert 'XDG_TEMPLATES_DIR="$HOME/"' not in u  # not the whole-home stock default
    assert templates.USER_DIRS_PATH == "/home/main/.config/user-dirs.dirs"


def test_text_template_is_empty_plain_file():
    assert templates.text_template() == ""


def test_odf_templates_are_valid_odf_packages():
    # Each ODF template must be a real ZIP whose FIRST member is `mimetype`, STORED
    # (uncompressed), containing the correct document mimetype -- the ODF validity rule that
    # lets LibreOffice open the copy.
    for name, mime, cls, body in templates._ODF_KINDS:
        data = templates.odf_bytes(mime, cls, body)
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
        # mimetype is first and stored uncompressed.
        assert infos[0].filename == "mimetype", name
        assert infos[0].compress_type == zipfile.ZIP_STORED, name
        assert zf.read("mimetype").decode() == mime, name
        # the manifest + content parts are present and well-formed enough to parse.
        assert "META-INF/manifest.xml" in zf.namelist(), name
        assert "content.xml" in zf.namelist(), name
        from xml.dom import minidom
        minidom.parseString(zf.read("content.xml"))   # raises if malformed
        minidom.parseString(zf.read("META-INF/manifest.xml"))
        # the class-specific root element is in content.xml (e.g. office:text/spreadsheet).
        assert f"office:{cls}".encode() in zf.read("content.xml"), name


def test_emit_plan_ships_home_files_skel_mirrored():
    plan = templates.emit_plan()
    by_dest = {e["dest"]: e for e in plan}
    # user-dirs.dirs + text template are text builders (HOME).
    assert by_dest[templates.USER_DIRS_PATH]["owner"] == "home"
    txt = by_dest[f"{templates.TEMPLATES_DIR}/Text Document.txt"]
    assert txt["owner"] == "home"
    assert callable(txt["builder"])
    # the ODF trio ride the bytes_builder (binary) kind, HOME-owned.
    for name, _m, _c, _b in templates._ODF_KINDS:
        e = by_dest[f"{templates.TEMPLATES_DIR}/{name}"]
        assert e["owner"] == "home"
        assert callable(e["bytes_builder"])
        assert isinstance(e["bytes_builder"](), (bytes, bytearray))


def test_odf_bytes_are_deterministic():
    # Fixed member order + fixed ZipInfo dates -> byte-identical across runs (so a build is
    # reproducible and this can be pinned).
    for name, mime, cls, body in templates._ODF_KINDS:
        assert templates.odf_bytes(mime, cls, body) == templates.odf_bytes(mime, cls, body)
