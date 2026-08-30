"""Identity collection for the scripted (CLI / SSH) installer.

The Calamares GUI collects, on its Location / Keyboard / Users pages, the things that make
an installed system PERSONAL and SECURE: a hostname, a real user account with a chosen
password, a root password, and a timezone. The old `azarch-install --cli` skipped all of
that -- it copied the LIVE `main` account and the LIVE (passwordless) root verbatim and
hard-set Asia/Jerusalem, so a headless SSH install produced a box with NO root password and
a fixed timezone: NOT "the same result" Calamares gives.

This module supplies the three bash fragments installer.installer_sh() splices in so the
scripted path reaches parity on those user-facing choices (see data/PROMPT.md: "give me the
entire process through the command line ... the same result"):

  identity_collect_sh()  -- runs BEFORE the destructive wipe: prompt (or read from env for
                            an unattended SSH install) for hostname / username / password /
                            timezone, validate, and stash them in shell variables. Root
                            reuses the user password (one password for the whole system);
                            there is no full-name field. Prompting first means a mistyped
                            answer costs nothing -- no disk has been touched yet.
  identity_write_sh()    -- runs AFTER the target root is mounted at /mnt: persist the
                            collected answers under /mnt/etc/install_info/ so the chroot can
                            read them (the same install_info channel disk/is_uefi already use).
  identity_chroot_sh()   -- runs INSIDE arch-chroot: create/rename the user, set both
                            passwords (chpasswd), write the hostname, and point /etc/localtime
                            at the chosen zone (overriding the static default), then hwclock.

Language and console keyboard stay ENGLISH-ONLY ("us") on purpose: that is the distribution's
deliberate locale policy (see packages/calamares/locale.py), the same policy the GUI enforces
outside its optional second-layout nicety. Filesystem/LUKS/swap stay as the scripted path's
ext4 default (the partition editor is the one Calamares page not reimplemented in a TTY).

Everything here is a pure string producer -- no network, no subprocess, no filesystem writes
-- so it is unit-testable exactly like installer.py. The env pre-seed names are the
AZ_INSTALL_* family, extending the AZ_INSTALL_CHOICE / AZ_INSTALL_DISK pair the disk step
already honours, so a fully unattended `azarch-install --cli` stays scriptable.
"""

from __future__ import annotations

# Defaults mirror the live session identity + the distribution's fixed timezone, so a user
# who just presses Enter through every prompt lands on the familiar azarch/main/Asia-Jerusalem
# system (only now with real, chosen passwords instead of the live passwordless root).
DEFAULT_HOSTNAME = "azarch"
DEFAULT_USERNAME = "main"
DEFAULT_TIMEZONE = "Asia/Jerusalem"

# The install_info files the answers are persisted to (read back in the chroot). Kept beside
# the existing disk / is_uefi markers installer_sh already writes under /mnt/etc/install_info.
INFO_DIR = "/mnt/etc/install_info"


def identity_collect_sh() -> str:
    """Bash that gathers the account/hostname/timezone answers into exported shell variables,
    BEFORE the disk is wiped. Each answer is taken from its AZ_INSTALL_* env var when set
    (unattended SSH install) or read interactively otherwise; passwords are read with `read
    -s` (no echo) and confirmed. Timezone and username are validated; a bad answer re-prompts
    interactively, or aborts a pre-seeded run rather than silently install something wrong."""
    return r"""
# --- Identity (hostname / user / passwords / timezone) ----------------------
# Collected BEFORE the wipe so a typo is free. Every field honours an AZ_INSTALL_* env var
# for unattended SSH installs; unset fields are prompted for interactively.
echo
echo -e "${LIGHT_BLUE}System configuration${RESET} (press Enter to accept the [default])"

# Hostname.
if [ -n "$AZ_INSTALL_HOSTNAME" ]; then
    az_hostname="$AZ_INSTALL_HOSTNAME"
    echo "Hostname: $az_hostname (pre-seeded)"
else
    read -rp "Hostname [azarch]: " az_hostname
    az_hostname="${az_hostname:-azarch}"
fi

# Login user name. Must match a POSIX-ish account name; re-prompt (or abort a seeded run).
while :; do
    if [ -n "$AZ_INSTALL_USERNAME" ]; then
        az_username="$AZ_INSTALL_USERNAME"
        echo "Username: $az_username (pre-seeded)"
    else
        read -rp "Username [main]: " az_username
        az_username="${az_username:-main}"
    fi
    if ! echo "$az_username" | grep -Eq '^[a-z_][a-z0-9_-]*$'; then
        echo "Invalid username '$az_username' (lower-case letters, digits, - and _; must not start with a digit)."
        if [ -n "$AZ_INSTALL_USERNAME" ]; then echo "Aborting (pre-seeded username is invalid)."; exit 1; fi
        continue
    fi
    # RESERVED / EXISTING-ACCOUNT guard. The chroot renames the live `main` account to the
    # chosen name ONLY when that name is free; a name that already exists on the cloned
    # target (root, bin, daemon, nobody, http, ...) would silently SKIP the rename yet still
    # re-point tty1 autologin at that account -- which has no startx bootstrap, so the desktop
    # never comes up (a bare root/nologin tty1). `main` itself is allowed: it is the live user
    # we rename FROM, so "keep main" is a valid choice, not a collision. `root` is always
    # rejected (autologin-as-root is explicitly unsupported). Any other already-present account
    # is rejected so the install cannot land in the broken-autologin state.
    if [ "$az_username" = "root" ]; then
        echo "Username 'root' is not allowed (the desktop cannot autologin as root)."
        if [ -n "$AZ_INSTALL_USERNAME" ]; then echo "Aborting (pre-seeded username is reserved)."; exit 1; fi
        continue
    fi
    if [ "$az_username" != "main" ] && id "$az_username" >/dev/null 2>&1; then
        echo "Username '$az_username' already exists as a system account; choose another."
        if [ -n "$AZ_INSTALL_USERNAME" ]; then echo "Aborting (pre-seeded username collides with a system account)."; exit 1; fi
        continue
    fi
    break
done

# INSTANT password short-circuits (both TTY-less, set by installer.instant_install_sh):
#   AZ_INSTALL_LOCK=1          -- non-ssh instant: create the account with NO password
#                                (locked `!*`, Ubuntu-style); the chroot step locks it.
#   AZ_INSTALL_KEEP_PASSWORD=1 -- ssh instant: KEEP the password already cloned from the live
#                                medium (the --ssh hash baked into `main`'s shadow); neither
#                                prompt nor change it.
# Either way there is nothing to collect, so skip BOTH password prompts/pre-seeds -- this is
# what stops the installer from blocking on an interactive `read` under the instant service.
if [ "$AZ_INSTALL_LOCK" = "1" ]; then
    az_lock_account=1
    az_password=""
    az_root_password=""
    echo "User + root passwords: LOCKED (instant, no password login)"
elif [ "$AZ_INSTALL_KEEP_PASSWORD" = "1" ]; then
    az_keep_password=1
    az_password=""
    az_root_password=""
    echo "User password: kept from the live medium (ssh instant)"
fi

# User password (confirmed, hidden). AZ_INSTALL_PASSWORD pre-seeds it for unattended installs.
if [ "$az_lock_account" = "1" ] || [ "$az_keep_password" = "1" ]; then
    :   # locked or kept-from-clone -- no password to collect (handled above)
elif [ -n "$AZ_INSTALL_PASSWORD" ]; then
    az_password="$AZ_INSTALL_PASSWORD"
    echo "User password: (pre-seeded)"
else
    while :; do
        read -rsp "Password for $az_username: " az_password; echo
        if [ -z "$az_password" ]; then echo "Password cannot be empty."; continue; fi
        read -rsp "Repeat password: " az_password2; echo
        [ "$az_password" = "$az_password2" ] && break
        echo "Passwords did not match, try again."
    done
fi

# Root password ALWAYS equals the user password -- ONE password for the whole system (user,
# root, and the btrfs LUKS passphrase). There is no separate root prompt or pre-seed. The
# instant short-circuits above already set az_root_password="" alongside a lock/keep marker;
# for a normal install root simply mirrors the collected user password.
if [ "$az_lock_account" = "1" ]; then
    :   # locked instant install -- root stays locked too (no root password set)
elif [ "$az_keep_password" = "1" ]; then
    :   # ssh instant -- keep root as cloned from the live medium (locked there)
else
    az_root_password="$az_password"
    echo "Root password: same as the user password"
fi

# Timezone. Validated against the live /usr/share/zoneinfo tree (the same DB the target has).
while :; do
    if [ -n "$AZ_INSTALL_TIMEZONE" ]; then
        az_timezone="$AZ_INSTALL_TIMEZONE"
        echo "Timezone: $az_timezone (pre-seeded)"
    else
        read -rp "Timezone [Asia/Jerusalem]: " az_timezone
        az_timezone="${az_timezone:-Asia/Jerusalem}"
    fi
    if [ -f "/usr/share/zoneinfo/$az_timezone" ]; then
        break
    fi
    echo "Unknown timezone '$az_timezone' (e.g. Europe/London, America/New_York; see /usr/share/zoneinfo)."
    if [ -n "$AZ_INSTALL_TIMEZONE" ]; then echo "Aborting (pre-seeded timezone is invalid)."; exit 1; fi
done

export az_hostname az_username az_password az_root_password az_timezone
export az_lock_account az_keep_password
"""


def identity_write_sh() -> str:
    """Bash that persists the collected answers under /mnt/etc/install_info so the chroot can
    read them. Passwords are written to root-only (0600) files that the chroot step deletes
    after use, so a plaintext password never lingers on the installed system. The non-secret
    fields (hostname/user/timezone) go to plain marker files like disk/is_uefi."""
    return f"""
# Persist the identity answers for the chroot step (same install_info channel as disk/is_uefi).
mkdir -p {INFO_DIR}
printf '%s' "$az_hostname" > {INFO_DIR}/hostname
printf '%s' "$az_username" > {INFO_DIR}/username
printf '%s' "$az_timezone" > {INFO_DIR}/timezone
# Encryption marker (set by the instant --encrypt path via AZ_INSTALL_ENCRYPT). The disk step
# already wrote the crypt UUID marker; this records the intent so the chroot's crypttab/GRUB
# blocks fire even if only the env flag is present. Absent -> a plain, unencrypted install.
if [ "$AZ_INSTALL_ENCRYPT" = "1" ]; then printf '1' > {INFO_DIR}/encrypt; fi
# Password persistence, three instant-aware cases:
#   lock  -> write a lock_account marker; the chroot LOCKS `!` both accounts, no secret files.
#   keep  -> write NOTHING (ssh instant): no password files and no marker, so the chroot leaves
#            the password the rootfs clone already carried (the --ssh hash) untouched.
#   normal-> write the collected user + root passwords to root-only (0600) files the chroot
#            consumes and shreds.
if [ "$az_lock_account" = "1" ]; then
    printf '1' > {INFO_DIR}/lock_account
elif [ "$az_keep_password" = "1" ]; then
    :   # ssh instant -- keep the cloned password; persist no password files or markers
else
    ( umask 077; printf '%s' "$az_password" > {INFO_DIR}/password )
    ( umask 077; printf '%s' "$az_root_password" > {INFO_DIR}/root_password )
fi
"""


def identity_chroot_sh() -> str:
    """Bash (runs INSIDE arch-chroot) that applies the collected identity to the target:

      * hostname  -> /etc/hostname
      * account   -> create the chosen user (or rename the copied-in `main` to it), put it in
                     the standard groups, set its shell, and set both its and root's password
                     via chpasswd. The live /etc/{{passwd,shadow,...}} were copied in by the
                     installer, so `main` already exists; we RENAME rather than re-create to
                     preserve its uid/gid (1000/998) and its /home/main tree.
      * timezone  -> re-point /etc/localtime at the chosen zone (overriding the static
                     Asia/Jerusalem the shared locale block set) and re-sync the hwclock.

    Password files are removed immediately after use so no plaintext survives on the target."""
    return f"""
# --- Apply the collected identity (hostname / user / passwords / timezone) ---
if [ -d /etc/install_info ]; then
    az_hostname="$(cat /etc/install_info/hostname 2>/dev/null)"
    az_username="$(cat /etc/install_info/username 2>/dev/null)"
    az_timezone="$(cat /etc/install_info/timezone 2>/dev/null)"

    # Hostname.
    if [ -n "$az_hostname" ]; then
        echo "$az_hostname" > /etc/hostname
    fi

    # Account: rename the copied-in live user ({DEFAULT_USERNAME}) to the chosen name so its
    # uid/gid and /home tree are preserved; only rename when the name actually differs and the
    # target name is free. Then refresh group membership and shell.
    if [ -n "$az_username" ] && id {DEFAULT_USERNAME} >/dev/null 2>&1 \\
       && [ "$az_username" != "{DEFAULT_USERNAME}" ] && ! id "$az_username" >/dev/null 2>&1; then
        usermod -l "$az_username" {DEFAULT_USERNAME}
        # Move the home directory to match the new login name and re-point the account at it.
        if [ -d /home/{DEFAULT_USERNAME} ] && [ ! -e "/home/$az_username" ]; then
            mv /home/{DEFAULT_USERNAME} "/home/$az_username"
            usermod -d "/home/$az_username" "$az_username"
        fi
        groupmod -n "$az_username" {DEFAULT_USERNAME} 2>/dev/null || true
    fi
    az_login="${{az_username:-{DEFAULT_USERNAME}}}"
    # Ensure the account exists even if the copied passwd somehow lacked it (defensive).
    if ! id "$az_login" >/dev/null 2>&1; then
        useradd -m -G wheel -s /bin/bash "$az_login"
    fi
    usermod -aG wheel "$az_login" 2>/dev/null || true
    usermod -s /bin/bash "$az_login" 2>/dev/null || true

    # Passwords. Either LOCK both accounts (instant, no password login -- the `!*`
    # Ubuntu default) or set the collected user + root passwords via chpasswd, then
    # shred the plaintext files. `passwd -l` writes the locked `!` marker into shadow,
    # exactly what system.LOCKED_PASSWORD ships on the live medium -- so a locked
    # instant install matches the base ISO's no-password-login posture.
    if [ "$(cat /etc/install_info/lock_account 2>/dev/null)" = "1" ]; then
        passwd -l "$az_login" >/dev/null 2>&1 || true
        passwd -l root >/dev/null 2>&1 || true
    else
        if [ -f /etc/install_info/password ]; then
            printf '%s:%s' "$az_login" "$(cat /etc/install_info/password)" | chpasswd
        fi
        if [ -f /etc/install_info/root_password ]; then
            printf 'root:%s' "$(cat /etc/install_info/root_password)" | chpasswd
        fi
        rm -f /etc/install_info/password /etc/install_info/root_password
    fi

    # SUDO GRANT for the chosen login. The only sudo rule copied onto the target is
    # /etc/sudoers.d/00-main (`main ALL=(ALL) NOPASSWD: ALL`); after a rename to e.g. "alice"
    # that rule names a non-existent user, leaving the installed account with NO sudo. So
    # OVERWRITE that same drop-in (install to the identical /etc/sudoers.d/00-main path -- the
    # stale line is replaced in place, no separate rm needed) with the grant for the ACTUAL
    # login -- the CLI equivalent of the wheel/sudo grant Calamares gives its created user. The
    # candidate file is validated with `visudo -c` before it replaces the live one (a malformed
    # sudoers file would lock everyone out) and written 0440. The login can only be a name the
    # collect step's `^[a-z_][a-z0-9_-]*$` regex allowed, so it never contains a sudoers
    # metacharacter and visudo always accepts it; the check is defence-in-depth.
    az_sudo_tmp="$(mktemp)"
    printf '%s ALL=(ALL) NOPASSWD: ALL\\n' "$az_login" > "$az_sudo_tmp"
    if visudo -c -f "$az_sudo_tmp" >/dev/null 2>&1; then
        install -m 0440 "$az_sudo_tmp" /etc/sudoers.d/00-main
    fi
    rm -f "$az_sudo_tmp"

    # Timezone: override the static default set by the shared locale block, then re-sync RTC.
    if [ -n "$az_timezone" ] && [ -f "/usr/share/zoneinfo/$az_timezone" ]; then
        ln -sf "/usr/share/zoneinfo/$az_timezone" /etc/localtime
        hwclock --systohc 2>/dev/null || true
    fi

    # FIRST-BOOT UNIT re-point. first-boot-setup.service hardcodes
    # ExecStart=/home/{DEFAULT_USERNAME}/.config/first-boot/first-boot-setup.sh, and the
    # first-boot-setup.sh it runs hardcodes its CONFIG_FILE under the same dir. After `mv
    # /home/{DEFAULT_USERNAME} /home/$user` both paths dangle and the enabled oneshot fails
    # (or no-ops) at first boot. When the home actually moved (login != {DEFAULT_USERNAME}),
    # rewrite BOTH the unit's ExecStart and the moved script's internal path to the new home so
    # the first-boot NTP step still runs. No-op on the default install -- nothing moved.
    if [ "$az_login" != "{DEFAULT_USERNAME}" ]; then
        az_fb_old="/home/{DEFAULT_USERNAME}/.config/first-boot"
        az_fb_new="/home/$az_login/.config/first-boot"
        [ -f /etc/systemd/system/first-boot-setup.service ] \\
            && sed -i "s#$az_fb_old#$az_fb_new#g" /etc/systemd/system/first-boot-setup.service
        [ -f "$az_fb_new/first-boot-setup.sh" ] \\
            && sed -i "s#$az_fb_old#$az_fb_new#g" "$az_fb_new/first-boot-setup.sh"

        # GETTY AUTOLOGIN re-point. The scripted installer copies the live
        # getty@tty1.service.d/autologin.conf drop-in onto the target, and it HARDCODES
        # `--autologin {DEFAULT_USERNAME}` (see system.GETTY_TTY1_AUTOLOGIN). After the rename
        # {DEFAULT_USERNAME} no longer exists, so agetty's `login -f {DEFAULT_USERNAME}` fails
        # and tty1 respawns forever -- the installed system never autologins and drops to a bare
        # login prompt (the exact "greeted with tty1" bug). Rewrite the drop-in to autologin the
        # ACTUAL login so the desktop (getty -> ~/.bash_profile -> exec startx) comes up. No-op on
        # the default install ({DEFAULT_USERNAME}) -- the copied drop-in is already correct.
        az_getty=/etc/systemd/system/getty@tty1.service.d/autologin.conf
        [ -f "$az_getty" ] \\
            && sed -i "s/--autologin {DEFAULT_USERNAME}/--autologin $az_login/g" "$az_getty"
    fi
fi
"""
