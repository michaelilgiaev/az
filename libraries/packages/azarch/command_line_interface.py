#!/usr/bin/env python3
"""azarch guest command line interface -- top-level dispatch (usage + main).

This is the LAST module bundled into /usr/local/bin/azarch. It ties the pieces together:
the `theme` positional subcommand (theme.cmd_theme), the `--resolve-*` geolocators
(resolver.*), and `--sshd-hypervisor` (sshd.sshd_hypervisor). See common.py for the bundle
mechanism; every name referenced below is defined in an earlier bundled module.
"""

from __future__ import annotations

# BUNDLE_START


def usage() -> None:
    print(
        "Usage: azarch [command]\n"
        "\n"
        "With no command, azarch opens a simple full-screen UI to configure the\n"
        "Theme, Wallpaper, and Network (arrow keys to move, Enter to select, / to\n"
        "search, Esc to go back).\n"
        "\n"
        "Commands:\n"
        "  theme [--dark|--white]  Set the system colour theme (dark is the default);\n"
        "                          no option prints the current theme. See "
        "`azarch theme --help`\n"
        "  wallpaper [--years.png|--decades.png]  Set the desktop wallpaper; no option\n"
        "                          prints the current one. See `azarch wallpaper --help`\n"
        "  network <wifi|wired|bluetooth|airplane|firewall|ip|status>  Everything\n"
        "                          network related; no option prints an overview. See "
        "`azarch network --help`\n"
        "  volume <up|down|mute|get>  Change the volume in 7.5% steps (centered cyan bar).\n"
        "                          See `azarch volume --help`\n"
        "  brightness <up|down|get>  Change screen brightness in 7.5% steps (laptops only).\n"
        "                          See `azarch brightness --help`\n"
        "  machine [--pc|--laptop|--auto]  Show / hard-set the machine type (PC or Laptop);\n"
        "                          no option prints it. See `azarch machine --help`\n"
        "  default-applications <list|get|set|...>  List / change the XDG default apps (which\n"
        "                          app opens which file type). See "
        "`azarch default-applications --help`\n"
        "  display <info|scale|resolution|...>  Configure the display (xrandr) and the global\n"
        "                          UI scale. See `azarch display --help`\n"
        "  backup-setup [--status|--disable]  Opt in to the `backup` command's optional USB /\n"
        "                          Google Drive targets (off by default). See "
        "`azarch backup-setup --help`\n"
        "  --sshd-hypervisor    Install host pubkey from ~/shared/authorized_keys "
        "and start sshd\n"
        "  --resolve-region     Geolocate by IP (pick a server) and set BOTH "
        "timezone and language\n"
        "  --resolve-date-time  Geolocate by IP (pick a server) and set the timezone\n"
        "  --resolve-language   Geolocate by IP (pick a server) and set English + "
        "the region language"
    )


def usage_err() -> None:
    """Same as usage() but on stderr (for the unknown-command path)."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        usage()
    sys.stderr.write(buf.getvalue())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""

    if cmd == "theme":
        return cmd_theme(argv[1:])
    if cmd == "wallpaper":
        return cmd_wallpaper(argv[1:])
    if cmd == "network":
        return cmd_network(argv[1:])
    if cmd == "volume":
        return cmd_volume(argv[1:])
    if cmd == "brightness":
        return cmd_brightness(argv[1:])
    if cmd == "media-init":
        return cmd_media_init(argv[1:])
    if cmd == "machine":
        return cmd_machine(argv[1:])
    if cmd == "default-applications":
        return cmd_default_applications(argv[1:])
    if cmd == "display":
        return cmd_display(argv[1:])
    if cmd == "backup-setup":
        return cmd_backup_setup(argv[1:])
    if cmd == "--sshd-hypervisor":
        return sshd_hypervisor()
    if cmd == "--resolve-date-time":
        result = resolve_via_server()
        if result is None:
            return 1
        country, tz = result
        print(f"Resolved: country={country} timezone={tz}")
        return apply_timezone(tz)
    if cmd == "--resolve-language":
        result = resolve_via_server()
        if result is None:
            return 1
        country, _tz = result
        print(f"Resolved: country={country}")
        return apply_language(country)
    if cmd == "--resolve-region":
        result = resolve_via_server()
        if result is None:
            return 1
        country, tz = result
        print(f"Resolved: country={country} timezone={tz}")
        # FAIL-FAST like the old shell (`set -e`): if the timezone can't be applied
        # (e.g. unknown zone), bail WITHOUT touching the keyboard/locale, so a bad
        # geolocation result never half-applies the region.
        rc = apply_timezone(tz)
        if rc != 0:
            return rc
        return apply_language(country)
    if cmd in ("-h", "--help", "help"):
        usage()
        return 0
    if cmd == "":
        # Bare `azarch` (no arguments) opens the full-screen terminal user interface (Theme / Wallpaper /
        # Network). run_terminal_user_interface degrades to a pointer message when there is no terminal, so this
        # is safe even when stdin/stdout are not a tty.
        return run_terminal_user_interface(argv)
    _err(f"azarch: unknown command: {cmd}")
    usage_err()
    return 2


if __name__ == "__main__":
    sys.exit(main())
