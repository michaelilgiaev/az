"""Config-as-Python: every hand-authored artifact baked into the ISO, held as a
Python variable (string) or produced by a small builder function.

Modules:
  pacman     - the pacman.conf variants (download / pacstrap / build profile)
  system     - users, sudoers, OS branding, boot entries, systemd units
  locale     - country->locale/keyboard map + setup-locale.sh
  installer  - the disk installer, chroot-setup, first-boot, setup-pkgs scripts
  profile    - profiledef.sh (archiso profile definition + file_permissions)
  pkgbuild   - Az'arch's own package recipes (calamares, librewolf) as PKGBUILDs
  desktop    - KDE Plasma live-session files (xinitrc, appletsrc, autostart, ...)
  calamares  - Calamares installer config (Btrfs default + LUKS encryption)
"""
