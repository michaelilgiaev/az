"""Existing UPSTREAM software that is NOT ours -- we merely modify/configure/patch it
to fit the Az'arch distribution. Each subpackage is one upstream thing we tailor:

  calamares         the azarch-installer (Calamares): its configuration tree, the
                    region/keyboard shellprocess wiring, AND locale.py (the static
                    install-time locale block Calamares/setup-locale.sh consume)
  ckbcomp           vendored Python 3 port of the upstream (Debian/Manjaro) Perl
                    ckbcomp; payload copied to /usr/bin (no __init__.py -- not imported)
  fastfetch         fastfetch config + the "Az'" ASCII logo
  openbox           OpenBox live-session config (xinitrc, rc.xml, autostart, ...) and
                    the guest `azarch` CLI wiring (was desktop.py)

Anything WE author outright is NOT here -- it is either a compiler module (flat in
libraries/: pacman.py, profile.py, installer.py, system.py, compiler.py, ...) or one
of our own packages (libraries/packages/: pkgbuild/, application_menu/, azarch/).

Imported as `from patches.<pkg> import <module>` (PYTHONPATH points at libraries/).
"""
