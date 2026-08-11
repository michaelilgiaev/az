"""The `azarch` guest-side CLI package (baked into the live/installed system).

This is Az'arch's OWN command -- a package under libraries/packages/, ALL Python
(no shell scripts). It ships to /usr/local/bin/azarch and provides:

    azarch --sshd-hypervisor
    azarch --resolve-region
    azarch --resolve-date-time
    azarch --resolve-language

See cli.py for the implementation. The compiler (patches/openbox openbox.azarch_cli)
installs cli.py to /usr/local/bin/azarch and injects the country -> locale/layout
table from patches/calamares/locale (the single source of truth) into it.
"""
