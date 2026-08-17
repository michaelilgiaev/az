/* Az'arch bare-`azarch` terminal user interface (C) -- the screen TREE (data + accessors).
 *
 * Split out of model.c (which grew past the per-file size budget): model.c keeps the shared
 * infrastructure (az_capture, the probe cache, `have`, the network/theme/wallpaper/volume/
 * brightness/machine status probes, the Default Applications + Display probes, the filter and
 * the row-command/base helpers), and THIS file holds the whole navigable tree as static data --
 * the ROWS_* tables and the SCREENS[] array -- plus az_screens/az_screen_find/az_screen_count.
 *
 * The tree references the probe function pointers and the AzRow/AzScreen/AzActKind/AzPreviewKind
 * types by name; all of them are declared in terminal_user_interface.h, so this TU only needs
 * that header. Keeping the data here (and the logic in model.c) keeps both files well under the
 * size limit and makes the screen tree easy to read as one contiguous table.
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1

#include "terminal_user_interface.h"

#include <string.h>

/* AZ_WALLPAPERS_DIR / AZ_WALLPAPER_RES are used by the wallpaper rows' base commands below.
 * They are defined in model.c too (for az_wallpaper_image); kept in lock-step with wallpaper.py
 * (a test pins the strings). Redefined here for the row base-command string literals. */
#ifndef AZ_WALLPAPERS_DIR
#define AZ_WALLPAPERS_DIR "/usr/share/wallpapers"
#endif
#ifndef AZ_WALLPAPER_RES
#define AZ_WALLPAPER_RES  "1672x941"
#endif

/* --- the screen tree -------------------------------------------------------- */
/* Actions are shell command lines run through the installed `azarch` command line interface. main.c runs
 * them INSIDE the UI (output captured, shown in the results overlay), then shows a result. */

/* All rows use DESIGNATED initializers: any field not named is zero (NULL / AZ_PV_NONE /
 * needs_root==0 / show_output==0), so adding a field never forces touching every row and the
 * intent of each row is self-documenting. `.needs_root = 1` marks an apply that first secures a
 * sudo credential; `.show_output = 1` shows its captured output in the overlay. */

/* Network is FIRST (it is what a fresh machine needs first). The main rows keep their live
 * status -- it is a genuine at-a-glance summary of the sub-screen (e.g. "firewall active"),
 * NOT a redundant echo, and the main screen has no "Current:" line of its own. */
static const AzRow ROWS_MAIN[] = {
    {.label="Network",      .kind=AZ_ACT_SCREEN, .target="network",    .status=az_status_network},
    {.label="Theme",        .kind=AZ_ACT_SCREEN, .target="theme",      .status=az_status_theme},
    {.label="Wallpaper",    .kind=AZ_ACT_SCREEN, .target="wallpaper",  .status=az_status_wallpaper},
    {.label="Volume",       .kind=AZ_ACT_SCREEN, .target="volume",     .status=az_status_volume},
    {.label="Brightness",   .kind=AZ_ACT_SCREEN, .target="brightness", .status=az_status_brightness},
    {.label="Default Applications", .kind=AZ_ACT_SCREEN, .target="defaultapps"},
    {.label="Display",      .kind=AZ_ACT_SCREEN, .target="display",    .status=az_status_display},
    {.label="Machine Type", .kind=AZ_ACT_SCREEN, .target="machine",    .status=az_status_machine},
};

/* Theme / Wallpaper rows carry NO per-row status: the live state is shown ONCE as the
 * "Current:" line at the top of the screen (the screen's `current` probe), so echoing
 * "white"/"years" after each option would just be noise -- exactly what the spec calls out.
 * Applying a theme/wallpaper needs no sudo (it configures the user session), so needs_root
 * stays 0; the apply still runs inside the UI (captured), so no command line interface text flashes over it. */
static const AzRow ROWS_THEME[] = {
    {.label="Dark",  .kind=AZ_ACT_APPLY, .target="azarch theme --dark",
     .base="gsettings set org.gnome.desktop.interface color-scheme prefer-dark",
     .preview=AZ_PV_THEME, .preview_arg="dark"},
    {.label="White", .kind=AZ_ACT_APPLY, .target="azarch theme --white",
     .base="gsettings set org.gnome.desktop.interface color-scheme prefer-light",
     .preview=AZ_PV_THEME, .preview_arg="white"},
};

static const AzRow ROWS_WALLPAPER[] = {
    {.label="Years",   .kind=AZ_ACT_APPLY, .target="azarch wallpaper --years.png",
     .base="feh --no-fehbg --bg-fill " AZ_WALLPAPERS_DIR "/years/contents/images/" AZ_WALLPAPER_RES ".png",
     .preview=AZ_PV_WALLPAPER, .preview_arg="years"},
    {.label="Decades", .kind=AZ_ACT_APPLY, .target="azarch wallpaper --decades.png",
     .base="feh --no-fehbg --bg-fill " AZ_WALLPAPERS_DIR "/decades/contents/images/" AZ_WALLPAPER_RES ".png",
     .preview=AZ_PV_WALLPAPER, .preview_arg="decades"},
};

static const AzRow ROWS_NETWORK[] = {
    {.label="Wifi",          .kind=AZ_ACT_SCREEN, .target="network.wifi",      .status=az_status_wifi},
    {.label="Wired",         .kind=AZ_ACT_SCREEN, .target="network.wired",     .status=az_status_wired},
    {.label="Bluetooth",     .kind=AZ_ACT_SCREEN, .target="network.bluetooth", .status=az_status_bluetooth},
    {.label="Airplane mode", .kind=AZ_ACT_SCREEN, .target="network.airplane",  .status=az_status_airplane},
    {.label="Firewall",      .kind=AZ_ACT_SCREEN, .target="network.firewall",  .status=az_status_firewall},
};

/* The sub-screen action rows carry NO per-row .status -- the live state is shown ONCE as the
 * screen's "Current:" line (its .current probe), exactly like Theme/Wallpaper. This is the fix
 * for the repeated "radio enabled" spam: every row on a screen was echoing the same probe. */
/* Every network apply runs privileged tools (nmcli/rfkill/systemctl/ufw), so needs_root=1:
 * the UI secures a sudo credential (masked, in-UI, cached) before running it, and runs it
 * captured -- no black screen, no scrollback. The list/scan verbs set show_output=1 so their
 * table lands in the results overlay; the toggles just show a one-line result. */
static const AzRow ROWS_WIFI[] = {
    {.label="Turn wifi on",         .kind=AZ_ACT_APPLY, .target="azarch network wifi on",   .needs_root=1,
     .base="sudo nmcli radio wifi on"},
    {.label="Turn wifi off",        .kind=AZ_ACT_APPLY, .target="azarch network wifi off",  .needs_root=1,
     .base="sudo nmcli radio wifi off"},
    {.label="Scan / list networks", .kind=AZ_ACT_APPLY, .target="azarch network wifi list", .needs_root=1, .show_output=1,
     .base="nmcli -f IN-USE,SSID,SIGNAL,SECURITY device wifi list"},
    {.label="Disconnect",           .kind=AZ_ACT_APPLY, .target="azarch network wifi disconnect", .needs_root=1,
     .base="sudo nmcli device disconnect <iface>"},
};

static const AzRow ROWS_WIRED[] = {
    {.label="Turn wired on",  .kind=AZ_ACT_APPLY, .target="azarch network wired on",  .needs_root=1,
     .base="sudo nmcli device connect <iface>"},
    {.label="Turn wired off", .kind=AZ_ACT_APPLY, .target="azarch network wired off", .needs_root=1,
     .base="sudo nmcli device disconnect <iface>"},
};

static const AzRow ROWS_BLUETOOTH[] = {
    {.label="Turn bluetooth on",   .kind=AZ_ACT_APPLY, .target="azarch network bluetooth on",  .needs_root=1,
     .base="sudo systemctl enable --now bluetooth"},
    {.label="Turn bluetooth off",  .kind=AZ_ACT_APPLY, .target="azarch network bluetooth off", .needs_root=1,
     .base="sudo systemctl disable --now bluetooth"},
    {.label="Scan / list devices", .kind=AZ_ACT_APPLY, .target="azarch network bluetooth scan", .needs_root=1, .show_output=1,
     .base="bluetoothctl devices"},
};

static const AzRow ROWS_AIRPLANE[] = {
    {.label="Turn airplane mode on",  .kind=AZ_ACT_APPLY, .target="azarch network airplane on", .needs_root=1,
     .base="sudo nmcli networking off"},
    {.label="Turn airplane mode off", .kind=AZ_ACT_APPLY, .target="azarch network airplane off", .needs_root=1,
     .base="sudo nmcli networking on"},
};

/* Firewall: enable/disable, LIST the port rules right here in the overlay (show_output=1),
 * and open/close/delete a port by TYPING its number (AZ_ACT_PORT prompts, then appends the
 * port to the command). This is the in-UI firewall config the spec asks for -- no dropping
 * to a shell, no guessing the command line interface. */
static const AzRow ROWS_FIREWALL[] = {
    {.label="Enable firewall",   .kind=AZ_ACT_APPLY, .target="azarch network firewall enable",  .needs_root=1,
     .base="sudo ufw --force enable"},
    {.label="Disable firewall",  .kind=AZ_ACT_APPLY, .target="azarch network firewall disable", .needs_root=1,
     .base="sudo ufw disable"},
    {.label="List ports",        .kind=AZ_ACT_APPLY, .target="azarch network firewall port list", .needs_root=1, .show_output=1,
     .base="sudo ufw status numbered"},
    {.label="Open a port",       .kind=AZ_ACT_PORT,  .target="azarch network firewall port open",   .needs_root=1, .show_output=1,
     .base="sudo ufw allow"},
    {.label="Close a port",      .kind=AZ_ACT_PORT,  .target="azarch network firewall port close",  .needs_root=1, .show_output=1,
     .base="sudo ufw deny"},
    {.label="Delete a port rule", .kind=AZ_ACT_PORT, .target="azarch network firewall port delete", .needs_root=1, .show_output=1,
     .base="sudo ufw delete allow"},
};

/* Machine Type: show what Az'arch recognises (PC or Laptop) via the "Current:" line, and let
 * the user HARD-SWITCH it -- Force PC / Force Laptop / Autodetect. The switch decides whether
 * the brightness controls are offered (a PC has no backlight), so forcing "Laptop" turns them
 * on even on a desktop. These write the user's own config pointer (no sudo), so needs_root
 * stays 0; each runs captured inside the UI and shows its one-line result. */
static const AzRow ROWS_MACHINE[] = {
    /* Machine type is a pure config-pointer write (~/.config/azarch/machine-type) -- there is
     * no system tool behind it, so the "base command" is the equivalent file write / removal. */
    {.label="Force PC",   .kind=AZ_ACT_APPLY, .target="azarch machine --pc",
     .base="printf 'PC\\n' > ~/.config/azarch/machine-type"},
    {.label="Force Laptop", .kind=AZ_ACT_APPLY, .target="azarch machine --laptop",
     .base="printf 'Laptop\\n' > ~/.config/azarch/machine-type"},
    {.label="Autodetect", .kind=AZ_ACT_APPLY, .target="azarch machine --auto",
     .base="rm -f ~/.config/azarch/machine-type"},
};

/* Volume: the "Current:" line shows the live level (az_status_volume); the rows set a PRECISE
 * level via `azarch volume set <N>` (the same subcommand the OSD mouse-drag uses) plus the two
 * 7.5% steps and mute. Each pops the bottom-middle cyan OSD bar. No sudo (PipeWire/ALSA run in
 * the user session), so needs_root stays 0; each runs captured in the UI and shows its result. */
static const AzRow ROWS_VOLUME[] = {
    {.label="Mute / unmute",   .kind=AZ_ACT_APPLY, .target="azarch volume mute",
     .base="wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"},
    {.label="Louder (+7.5%)",  .kind=AZ_ACT_APPLY, .target="azarch volume up",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 7.5%+"},
    {.label="Quieter (-7.5%)", .kind=AZ_ACT_APPLY, .target="azarch volume down",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 7.5%-"},
    {.label="Set to 0%",       .kind=AZ_ACT_APPLY, .target="azarch volume set 0",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 0%"},
    {.label="Set to 25%",      .kind=AZ_ACT_APPLY, .target="azarch volume set 25",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 25%"},
    {.label="Set to 50%",      .kind=AZ_ACT_APPLY, .target="azarch volume set 50",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 50%"},
    {.label="Set to 75%",      .kind=AZ_ACT_APPLY, .target="azarch volume set 75",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 75%"},
    {.label="Set to 100%",     .kind=AZ_ACT_APPLY, .target="azarch volume set 100",
     .base="wpctl set-volume -l 1.0 @DEFAULT_AUDIO_SINK@ 100%"},
};

/* Brightness: LAPTOP-ONLY (a PC has no backlight). The "Current:" line reads "not on a PC" on a
 * desktop; the set/step rows still run `azarch brightness ...`, which SELF-GATES (it refuses and
 * says so on a PC), so selecting one on a desktop is harmless and explains itself. Force the type
 * on the Machine Type screen to light this up on a desktop. No sudo needed for the UI wrapper. */
/* Brightness has NO brightnessctl on this build: azarch scales percent -> the raw kernel value
 * (percent/100 * max_brightness) and writes it to the backlight device's brightness file under
 * /sys/class/backlight via sudo tee. The base commands mirror that exactly, scaling inline so
 * they are copy-pasteable on any laptop (the glob picks the single backlight device, e.g.
 * intel_backlight). */
static const AzRow ROWS_BRIGHTNESS[] = {
    {.label="Brighter (+7.5%)", .kind=AZ_ACT_APPLY, .target="azarch brightness up",
     .base="sudo sh -c 'b=/sys/class/backlight/*; echo $(( $(cat $b/brightness) + 8*$(cat $b/max_brightness)/100 )) > $b/brightness'"},
    {.label="Dimmer (-7.5%)",   .kind=AZ_ACT_APPLY, .target="azarch brightness down",
     .base="sudo sh -c 'b=/sys/class/backlight/*; echo $(( $(cat $b/brightness) - 8*$(cat $b/max_brightness)/100 )) > $b/brightness'"},
    {.label="Set to 25%",       .kind=AZ_ACT_APPLY, .target="azarch brightness set 25",
     .base="sudo sh -c 'b=/sys/class/backlight/*; echo $(( 25*$(cat $b/max_brightness)/100 )) > $b/brightness'"},
    {.label="Set to 50%",       .kind=AZ_ACT_APPLY, .target="azarch brightness set 50",
     .base="sudo sh -c 'b=/sys/class/backlight/*; echo $(( 50*$(cat $b/max_brightness)/100 )) > $b/brightness'"},
    {.label="Set to 75%",       .kind=AZ_ACT_APPLY, .target="azarch brightness set 75",
     .base="sudo sh -c 'b=/sys/class/backlight/*; echo $(( 75*$(cat $b/max_brightness)/100 )) > $b/brightness'"},
    {.label="Set to 100%",      .kind=AZ_ACT_APPLY, .target="azarch brightness set 100",
     .base="sudo sh -c 'b=/sys/class/backlight/*; cat $b/max_brightness > $b/brightness'"},
};

/* --- Default Applications screens -------------------------------------------
 * A "Default Applications" entry on ROWS_MAIN opens the `defaultapps` screen, which lists the
 * 14 categories (Web/HTML/Music/.../Terminal). Each category row's status shows the handler it
 * currently resolves to, and descends into a per-category screen whose rows CHANGE the default
 * by running `azarch default-applications set <key> <id>` (the same apply-and-capture flow the
 * other screens use). The category set, keys, labels, candidate handlers and the base commands
 * are all pinned to packages/azarch/default_applications.py by a test, so C and Python cannot
 * drift. Applying a default writes the user's own mimeapps.list / exo helper -- no sudo. */

/* Per-category candidate rows. Each "Set to <app>" runs `azarch default-applications set
 * <key> <id.desktop>`; base= is the underlying `xdg-mime default ...` line (or the exo helper
 * write for the terminal) the wrapper ultimately runs, for the teaching line + `x` copy. */
static const AzRow ROWS_DA_WEB[] = {
    {.label="Set to LibreWolf", .kind=AZ_ACT_APPLY, .target="azarch default-applications set web librewolf.desktop",
     .base="xdg-mime default librewolf.desktop x-scheme-handler/http x-scheme-handler/https"},
    {.label="Set to Firefox",   .kind=AZ_ACT_APPLY, .target="azarch default-applications set web firefox.desktop",
     .base="xdg-mime default firefox.desktop x-scheme-handler/http x-scheme-handler/https"},
};
static const AzRow ROWS_DA_HTML[] = {
    {.label="Set to LibreWolf", .kind=AZ_ACT_APPLY, .target="azarch default-applications set html librewolf.desktop",
     .base="xdg-mime default librewolf.desktop text/html application/xhtml+xml"},
    {.label="Set to Firefox",   .kind=AZ_ACT_APPLY, .target="azarch default-applications set html firefox.desktop",
     .base="xdg-mime default firefox.desktop text/html application/xhtml+xml"},
    {.label="Set to gedit",     .kind=AZ_ACT_APPLY, .target="azarch default-applications set html org.gnome.gedit.desktop",
     .base="xdg-mime default org.gnome.gedit.desktop text/html application/xhtml+xml"},
};
static const AzRow ROWS_DA_MUSIC[] = {
    {.label="Set to VLC", .kind=AZ_ACT_APPLY, .target="azarch default-applications set music vlc.desktop",
     .base="xdg-mime default vlc.desktop audio/mpeg audio/flac audio/ogg ..."},
};
static const AzRow ROWS_DA_VIDEO[] = {
    {.label="Set to VLC", .kind=AZ_ACT_APPLY, .target="azarch default-applications set video vlc.desktop",
     .base="xdg-mime default vlc.desktop video/mp4 video/x-matroska video/webm ..."},
};
static const AzRow ROWS_DA_PHOTOS[] = {
    {.label="Set to xviewer", .kind=AZ_ACT_APPLY, .target="azarch default-applications set photos xviewer.desktop",
     .base="xdg-mime default xviewer.desktop image/jpeg image/png image/gif ..."},
    {.label="Set to GIMP",    .kind=AZ_ACT_APPLY, .target="azarch default-applications set photos gimp.desktop",
     .base="xdg-mime default gimp.desktop image/jpeg image/png image/gif ..."},
    {.label="Set to feh",     .kind=AZ_ACT_APPLY, .target="azarch default-applications set photos feh.desktop",
     .base="xdg-mime default feh.desktop image/jpeg image/png image/gif ..."},
};
static const AzRow ROWS_DA_WORD[] = {
    {.label="Set to LibreOffice Writer", .kind=AZ_ACT_APPLY, .target="azarch default-applications set word libreoffice-writer.desktop",
     .base="xdg-mime default libreoffice-writer.desktop application/vnd.oasis.opendocument.text ..."},
};
static const AzRow ROWS_DA_SPREADSHEET[] = {
    {.label="Set to LibreOffice Calc", .kind=AZ_ACT_APPLY, .target="azarch default-applications set spreadsheet libreoffice-calc.desktop",
     .base="xdg-mime default libreoffice-calc.desktop application/vnd.oasis.opendocument.spreadsheet ..."},
};
static const AzRow ROWS_DA_PDF[] = {
    {.label="Set to LibreWolf", .kind=AZ_ACT_APPLY, .target="azarch default-applications set pdf librewolf.desktop",
     .base="xdg-mime default librewolf.desktop application/pdf"},
    {.label="Set to Firefox",   .kind=AZ_ACT_APPLY, .target="azarch default-applications set pdf firefox.desktop",
     .base="xdg-mime default firefox.desktop application/pdf"},
};
static const AzRow ROWS_DA_SOURCE_CODE[] = {
    {.label="Set to gedit", .kind=AZ_ACT_APPLY, .target="azarch default-applications set source-code org.gnome.gedit.desktop",
     .base="xdg-mime default org.gnome.gedit.desktop text/x-csrc text/x-python ..."},
    {.label="Set to Vim",   .kind=AZ_ACT_APPLY, .target="azarch default-applications set source-code vim.desktop",
     .base="xdg-mime default vim.desktop text/x-csrc text/x-python ..."},
};
static const AzRow ROWS_DA_FILE_MANAGER[] = {
    {.label="Set to Thunar", .kind=AZ_ACT_APPLY, .target="azarch default-applications set file-manager thunar.desktop",
     .base="xdg-mime default thunar.desktop inode/directory"},
};
static const AzRow ROWS_DA_PLAIN_TEXT[] = {
    {.label="Set to gedit", .kind=AZ_ACT_APPLY, .target="azarch default-applications set plain-text org.gnome.gedit.desktop",
     .base="xdg-mime default org.gnome.gedit.desktop text/plain"},
    {.label="Set to Vim",   .kind=AZ_ACT_APPLY, .target="azarch default-applications set plain-text vim.desktop",
     .base="xdg-mime default vim.desktop text/plain"},
};
static const AzRow ROWS_DA_CALCULATOR[] = {
    {.label="Set to Qalculate", .kind=AZ_ACT_APPLY, .target="azarch default-applications set calculator qalculate-gtk.desktop",
     .base="(no MIME default -- qalculate-gtk is the recorded calculator)"},
};
static const AzRow ROWS_DA_TERMINAL[] = {
    {.label="Set to kitty", .kind=AZ_ACT_APPLY, .target="azarch default-applications set terminal kitty.desktop",
     .base="printf 'TerminalEmulator=kitty\\n' >> ~/.config/xfce4/helpers.rc"},
};

/* The category list (the `defaultapps` screen). Each row shows the live handler and descends
 * into its per-category screen. This is exactly the category set the PROMPT lists for the TUI
 * (Web, HTML, Music, Video, Photos, Word, Spreadsheet, PDF, Source Code, File Manager, Plain
 * Text, Calculator, Terminal) -- "Mail" is deliberately absent (no mail client is shipped, so
 * default_applications leaves it empty and the TUI does not surface it). */
static const AzRow ROWS_DEFAULTAPPS[] = {
    {.label="Web",          .kind=AZ_ACT_SCREEN, .target="defaultapps.web",          .status=az_status_da_web},
    {.label="HTML",         .kind=AZ_ACT_SCREEN, .target="defaultapps.html",         .status=az_status_da_html},
    {.label="Music",        .kind=AZ_ACT_SCREEN, .target="defaultapps.music",        .status=az_status_da_music},
    {.label="Video",        .kind=AZ_ACT_SCREEN, .target="defaultapps.video",        .status=az_status_da_video},
    {.label="Photos",       .kind=AZ_ACT_SCREEN, .target="defaultapps.photos",       .status=az_status_da_photos},
    {.label="Word",         .kind=AZ_ACT_SCREEN, .target="defaultapps.word",         .status=az_status_da_word},
    {.label="Spreadsheet",  .kind=AZ_ACT_SCREEN, .target="defaultapps.spreadsheet",  .status=az_status_da_spreadsheet},
    {.label="PDF",          .kind=AZ_ACT_SCREEN, .target="defaultapps.pdf",          .status=az_status_da_pdf},
    {.label="Source Code",  .kind=AZ_ACT_SCREEN, .target="defaultapps.source-code",  .status=az_status_da_source_code},
    {.label="File Manager", .kind=AZ_ACT_SCREEN, .target="defaultapps.file-manager", .status=az_status_da_file_manager},
    {.label="Plain Text",   .kind=AZ_ACT_SCREEN, .target="defaultapps.plain-text",   .status=az_status_da_plain_text},
    {.label="Calculator",   .kind=AZ_ACT_SCREEN, .target="defaultapps.calculator",   .status=az_status_da_calculator},
    {.label="Terminal",     .kind=AZ_ACT_SCREEN, .target="defaultapps.terminal",     .status=az_status_da_terminal},
};

/* --- Display screens --------------------------------------------------------
 * A "Display" entry on ROWS_MAIN opens the `display` screen: cinnamon-settings-display parity
 * for this X11/OpenBox setup (resolution/refresh/orientation/primary/on-off/mirror via xrandr)
 * PLUS the GLOBAL SCALE chooser (the single source of truth for UI scaling). Each row runs an
 * `azarch display ...` apply; the screens' Current: lines read live state. The scale chooser is
 * the firm requirement; the xrandr rows reflect/act on the real output (defaulting to the
 * primary on a single-head VM). No sudo -- xrandr + the X resource DB are per-session. */

/* GLOBAL SCALE chooser: one row per SCALE_OPTIONS value (modifications/scale, pinned by a test).
 * Each runs `azarch display scale <factor>` -- rewrites ~/.Xresources' Xft.dpi and re-applies
 * live so the change propagates (new windows immediately; a re-login everywhere). */
static const AzRow ROWS_DISPLAY_SCALE[] = {
    {.label="100% (1.00)",  .kind=AZ_ACT_APPLY, .target="azarch display scale 1.00",
     .base="printf 'Xft.dpi: 96\\n'  > ~/.Xresources && xrdb -merge ~/.Xresources"},
    {.label="125% (1.25)",  .kind=AZ_ACT_APPLY, .target="azarch display scale 1.25",
     .base="printf 'Xft.dpi: 120\\n' > ~/.Xresources && xrdb -merge ~/.Xresources"},
    {.label="135% (1.35)",  .kind=AZ_ACT_APPLY, .target="azarch display scale 1.35",
     .base="printf 'Xft.dpi: 130\\n' > ~/.Xresources && xrdb -merge ~/.Xresources"},
    {.label="150% (1.50)",  .kind=AZ_ACT_APPLY, .target="azarch display scale 1.50",
     .base="printf 'Xft.dpi: 144\\n' > ~/.Xresources && xrdb -merge ~/.Xresources"},
    {.label="175% (1.75)",  .kind=AZ_ACT_APPLY, .target="azarch display scale 1.75",
     .base="printf 'Xft.dpi: 168\\n' > ~/.Xresources && xrdb -merge ~/.Xresources"},
    {.label="200% (2.00)",  .kind=AZ_ACT_APPLY, .target="azarch display scale 2.00",
     .base="printf 'Xft.dpi: 192\\n' > ~/.Xresources && xrdb -merge ~/.Xresources"},
};

/* Resolution: show the available modes (a captured `xrandr` list) + a couple of common presets.
 * The presets no-op with an xrandr error if the output lacks that mode, which the overlay shows. */
static const AzRow ROWS_DISPLAY_RESOLUTION[] = {
    {.label="List available modes", .kind=AZ_ACT_APPLY, .target="azarch display info", .show_output=1,
     .base="xrandr --query"},
    {.label="Set 1920x1080", .kind=AZ_ACT_APPLY, .target="azarch display resolution 1920x1080", .show_output=1,
     .base="xrandr --output <primary> --mode 1920x1080"},
    {.label="Set 1680x1050", .kind=AZ_ACT_APPLY, .target="azarch display resolution 1680x1050", .show_output=1,
     .base="xrandr --output <primary> --mode 1680x1050"},
    {.label="Set 1280x720",  .kind=AZ_ACT_APPLY, .target="azarch display resolution 1280x720", .show_output=1,
     .base="xrandr --output <primary> --mode 1280x720"},
};

/* Refresh rate: list the modes (rates are shown per resolution in the xrandr table) + presets. */
static const AzRow ROWS_DISPLAY_REFRESH[] = {
    {.label="List modes / rates", .kind=AZ_ACT_APPLY, .target="azarch display info", .show_output=1,
     .base="xrandr --query"},
    {.label="Set 60 Hz", .kind=AZ_ACT_APPLY, .target="azarch display refresh 60", .show_output=1,
     .base="xrandr --output <primary> --rate 60"},
    {.label="Set 75 Hz", .kind=AZ_ACT_APPLY, .target="azarch display refresh 75", .show_output=1,
     .base="xrandr --output <primary> --rate 75"},
};

/* Orientation / rotation. */
static const AzRow ROWS_DISPLAY_ORIENTATION[] = {
    {.label="Normal",   .kind=AZ_ACT_APPLY, .target="azarch display rotate normal", .show_output=1,
     .base="xrandr --output <primary> --rotate normal"},
    {.label="Left (90 CCW)",  .kind=AZ_ACT_APPLY, .target="azarch display rotate left", .show_output=1,
     .base="xrandr --output <primary> --rotate left"},
    {.label="Right (90 CW)",  .kind=AZ_ACT_APPLY, .target="azarch display rotate right", .show_output=1,
     .base="xrandr --output <primary> --rotate right"},
    {.label="Inverted (180)", .kind=AZ_ACT_APPLY, .target="azarch display rotate inverted", .show_output=1,
     .base="xrandr --output <primary> --rotate inverted"},
};

/* Monitors: primary select, enable/disable, mirror vs extend. The list/info is here too. */
static const AzRow ROWS_DISPLAY_MONITORS[] = {
    {.label="Show monitors (xrandr)", .kind=AZ_ACT_APPLY, .target="azarch display info", .show_output=1,
     .base="xrandr --query"},
    {.label="Mirror displays",  .kind=AZ_ACT_APPLY, .target="azarch display mirror on", .show_output=1,
     .base="xrandr --output <o> --same-as <primary>"},
    {.label="Extend displays",  .kind=AZ_ACT_APPLY, .target="azarch display mirror off", .show_output=1,
     .base="xrandr --output <o> --right-of <primary>"},
};

/* The Display screen: the scale chooser + the xrandr feature screens. Every row shows its OWN
 * current value inline (.status) -- the user asked for the standalone top "Current: scale 1.35x"
 * line to be removed and the current value put on each line instead, so the display screen has
 * NO .current (see SCREENS[]) and each row carries an inline probe. */
static const AzRow ROWS_DISPLAY[] = {
    {.label="Global Scale", .kind=AZ_ACT_SCREEN, .target="display.scale",       .status=az_status_display_scale},
    {.label="Resolution",   .kind=AZ_ACT_SCREEN, .target="display.resolution",  .status=az_status_display_resolution},
    {.label="Refresh Rate", .kind=AZ_ACT_SCREEN, .target="display.refresh",     .status=az_status_display_refresh},
    {.label="Orientation",  .kind=AZ_ACT_SCREEN, .target="display.orientation", .status=az_status_display_orientation},
    {.label="Monitors",     .kind=AZ_ACT_SCREEN, .target="display.monitors",    .status=az_status_display_monitors},
};

#define AZN(a) (int)(sizeof(a) / sizeof((a)[0]))

/* Only Theme and Wallpaper set `.current` (the top "Current:" line); every other screen
 * leaves it NULL. The main screen's subtitle is empty (the spec removed the "Move with the
 * arrow keys..." line -- the nav hints at the bottom already say how to move). Designated
 * initializers throughout, so the NULL terminator is simply an empty pair of braces. */
static const AzScreen SCREENS[] = {
    {.id="main",      .title="Az'arch Settings", .subtitle="",
     .rows=ROWS_MAIN, .nrows=AZN(ROWS_MAIN)},
    /* Subtitles now say WHAT tool each screen drives and WHAT it does (the spec: the top label
     * should explain the wrapped commands), not a bare tagline. The Theme one keeps the pinned
     * "Kitty does not follow the system theme" phrase. */
    {.id="theme",     .title="Theme",
     .subtitle="Wraps gsettings color-scheme (prefer-dark/prefer-light) to switch dark/white. "
               "Kitty does not follow the system theme.",
     .current=az_status_theme,     .rows=ROWS_THEME,     .nrows=AZN(ROWS_THEME)},
    /* Wallpaper subtitle is the DIRECTORY PATH -- coloured cyan (subtitle_accent) and placed
     * tight above the "Current:" line, per the spec. It keeps the /usr/share/wallpapers path. */
    {.id="wallpaper", .title="Wallpaper",
     .subtitle="Wallpapers directory: " AZ_WALLPAPERS_DIR "/", .subtitle_accent=1,
     .current=az_status_wallpaper, .rows=ROWS_WALLPAPER, .nrows=AZN(ROWS_WALLPAPER)},
    {.id="network",   .title="Network",
     .subtitle="A front-end over nmcli, rfkill, bluetoothctl and ufw -- wifi, wired, "
               "bluetooth, airplane and the firewall.",
     .rows=ROWS_NETWORK, .nrows=AZN(ROWS_NETWORK)},
    /* Each network sub-screen shows its live state ONCE via .current (the "Current:" line at
     * the top), so the rows below stay label-only -- no repeated status echo. */
    {.id="network.wifi",      .title="Wifi",
     .subtitle="Wraps nmcli radio wifi (on/off) and nmcli device wifi (list/disconnect).",
     .current=az_status_wifi,      .rows=ROWS_WIFI,      .nrows=AZN(ROWS_WIFI)},
    {.id="network.wired",     .title="Wired",
     .subtitle="Wraps nmcli device connect/disconnect on the ethernet interface.",
     .current=az_status_wired,     .rows=ROWS_WIRED,     .nrows=AZN(ROWS_WIRED)},
    {.id="network.bluetooth", .title="Bluetooth",
     .subtitle="Wraps systemctl (enable/disable bluetooth) + rfkill; bluetoothctl to scan. "
               "Off by default.",
     .current=az_status_bluetooth, .rows=ROWS_BLUETOOTH, .nrows=AZN(ROWS_BLUETOOTH)},
    {.id="network.airplane",  .title="Airplane mode",
     .subtitle="Wraps nmcli networking off/on (plus rfkill) -- one switch that really drops "
               "the internet.",
     .current=az_status_airplane,  .rows=ROWS_AIRPLANE,  .nrows=AZN(ROWS_AIRPLANE)},
    {.id="network.firewall",  .title="Firewall",
     .subtitle="Wraps ufw: enable/disable, status numbered, and allow/deny/delete a port.",
     .current=az_status_firewall,  .rows=ROWS_FIREWALL,  .nrows=AZN(ROWS_FIREWALL)},
    /* Volume: the "Current:" line shows the live level; the rows set a precise level (or step /
     * mute), each popping the bottom-middle cyan OSD bar. */
    {.id="volume",    .title="Volume",
     .subtitle="Wraps wpctl set-volume / set-mute on @DEFAULT_AUDIO_SINK@ (PipeWire). "
               "Drag the on-screen bar for any value.",
     .current=az_status_volume,    .rows=ROWS_VOLUME,    .nrows=AZN(ROWS_VOLUME)},
    /* Brightness: LAPTOP-ONLY. The "Current:" line reads the level on a laptop, or "not on a PC"
     * on a desktop (where the rows self-gate). Force Laptop on Machine Type to enable it. */
    {.id="brightness", .title="Brightness",
     .subtitle="Writes the scaled value to /sys/class/backlight/*/brightness (sudo tee). "
               "Laptops only -- a PC has no backlight.",
     .current=az_status_brightness, .rows=ROWS_BRIGHTNESS, .nrows=AZN(ROWS_BRIGHTNESS)},
    /* Machine Type: the "Current:" line shows what Az'arch recognises (PC / Laptop); the rows
     * hard-switch it. Brightness is a laptop-only control, so this is where a desktop can be
     * forced to "Laptop" to light the brightness UI up (or a laptop forced to "PC"). */
    {.id="machine",   .title="Machine Type",
     .subtitle="Writes ~/.config/azarch/machine-type (PC/Laptop) or removes it to autodetect. "
               "Laptops get screen-brightness control; PCs do not.",
     .current=az_status_machine,   .rows=ROWS_MACHINE,   .nrows=AZN(ROWS_MACHINE)},
    /* Default Applications: the category list + one screen per category. Each category screen's
     * "Current:" line shows the handler it resolves to now; its rows change the default via
     * `azarch default-applications set ...`. Derived from default_applications.py (pinned). */
    {.id="defaultapps", .title="Default Applications",
     .subtitle="Which app opens which file type (the XDG mimeapps defaults). Pick a category to "
               "change its handler. To set ANY installed app (or find where .desktop files live): "
               "azarch default-applications desktops [category].",
     .rows=ROWS_DEFAULTAPPS, .nrows=AZN(ROWS_DEFAULTAPPS)},
    {.id="defaultapps.web",          .title="Web",
     .subtitle="The browser for http/https links (wraps xdg-mime default).",
     .current=az_status_da_web,          .rows=ROWS_DA_WEB,          .nrows=AZN(ROWS_DA_WEB)},
    {.id="defaultapps.html",         .title="HTML",
     .subtitle="The handler for .html / xhtml files (wraps xdg-mime default).",
     .current=az_status_da_html,         .rows=ROWS_DA_HTML,         .nrows=AZN(ROWS_DA_HTML)},
    {.id="defaultapps.music",        .title="Music",
     .subtitle="The player for audio files (wraps xdg-mime default).",
     .current=az_status_da_music,        .rows=ROWS_DA_MUSIC,        .nrows=AZN(ROWS_DA_MUSIC)},
    {.id="defaultapps.video",        .title="Video",
     .subtitle="The player for video files (wraps xdg-mime default).",
     .current=az_status_da_video,        .rows=ROWS_DA_VIDEO,        .nrows=AZN(ROWS_DA_VIDEO)},
    {.id="defaultapps.photos",       .title="Photos",
     .subtitle="The viewer for image files (wraps xdg-mime default).",
     .current=az_status_da_photos,       .rows=ROWS_DA_PHOTOS,       .nrows=AZN(ROWS_DA_PHOTOS)},
    {.id="defaultapps.word",         .title="Word",
     .subtitle="The handler for word-processor documents (wraps xdg-mime default).",
     .current=az_status_da_word,         .rows=ROWS_DA_WORD,         .nrows=AZN(ROWS_DA_WORD)},
    {.id="defaultapps.spreadsheet",  .title="Spreadsheet",
     .subtitle="The handler for spreadsheet documents (wraps xdg-mime default).",
     .current=az_status_da_spreadsheet,  .rows=ROWS_DA_SPREADSHEET,  .nrows=AZN(ROWS_DA_SPREADSHEET)},
    {.id="defaultapps.pdf",          .title="PDF",
     .subtitle="The handler for PDF files (wraps xdg-mime default).",
     .current=az_status_da_pdf,          .rows=ROWS_DA_PDF,          .nrows=AZN(ROWS_DA_PDF)},
    {.id="defaultapps.source-code",  .title="Source Code",
     .subtitle="The editor for source files (wraps xdg-mime default).",
     .current=az_status_da_source_code,  .rows=ROWS_DA_SOURCE_CODE,  .nrows=AZN(ROWS_DA_SOURCE_CODE)},
    {.id="defaultapps.file-manager", .title="File Manager",
     .subtitle="The handler for directories / inode/directory (wraps xdg-mime default).",
     .current=az_status_da_file_manager, .rows=ROWS_DA_FILE_MANAGER, .nrows=AZN(ROWS_DA_FILE_MANAGER)},
    {.id="defaultapps.plain-text",   .title="Plain Text",
     .subtitle="The editor for text/plain files (wraps xdg-mime default).",
     .current=az_status_da_plain_text,   .rows=ROWS_DA_PLAIN_TEXT,   .nrows=AZN(ROWS_DA_PLAIN_TEXT)},
    {.id="defaultapps.calculator",   .title="Calculator",
     .subtitle="The recorded calculator app (no MIME type of its own).",
     .current=az_status_da_calculator,   .rows=ROWS_DA_CALCULATOR,   .nrows=AZN(ROWS_DA_CALCULATOR)},
    {.id="defaultapps.terminal",     .title="Terminal",
     .subtitle="The terminal Thunar's 'Open Terminal Here' opens (exo TerminalEmulator helper).",
     .current=az_status_da_terminal,     .rows=ROWS_DA_TERMINAL,     .nrows=AZN(ROWS_DA_TERMINAL)},
    /* Display: cinnamon-settings-display parity (xrandr) + the GLOBAL SCALE chooser. NO
     * .current here -- the top "Current: scale 1.35x" line was removed at the user's request;
     * each ROWS_DISPLAY row shows its own current value inline via .status instead. */
    {.id="display",   .title="Display",
     .subtitle="Resolution, refresh, orientation, monitors (xrandr) and the global UI scale.",
     .rows=ROWS_DISPLAY,   .nrows=AZN(ROWS_DISPLAY)},
    {.id="display.scale", .title="Global Scale",
     .subtitle="The ONE UI scale every app obeys (Xft.dpi + Xcursor.size, re-applied live via "
               "xrdb). Thunar and DPI-aware apps rescale at once; others on next launch.",
     .current=az_status_display_scale, .rows=ROWS_DISPLAY_SCALE, .nrows=AZN(ROWS_DISPLAY_SCALE)},
    {.id="display.resolution", .title="Resolution",
     .subtitle="Wraps xrandr --output --mode. List the modes, then pick one (or type "
               "`azarch display resolution <WxH>`).",
     .rows=ROWS_DISPLAY_RESOLUTION, .nrows=AZN(ROWS_DISPLAY_RESOLUTION)},
    {.id="display.refresh", .title="Refresh Rate",
     .subtitle="Wraps xrandr --output --rate. The rates per resolution are in the mode list.",
     .rows=ROWS_DISPLAY_REFRESH, .nrows=AZN(ROWS_DISPLAY_REFRESH)},
    {.id="display.orientation", .title="Orientation",
     .subtitle="Wraps xrandr --output --rotate (normal / left / right / inverted).",
     .rows=ROWS_DISPLAY_ORIENTATION, .nrows=AZN(ROWS_DISPLAY_ORIENTATION)},
    {.id="display.monitors", .title="Monitors",
     .subtitle="Wraps xrandr: show outputs, mirror (same-as) or extend (right-of). Primary / "
               "on / off per output are `azarch display primary|on|off <output>`.",
     .rows=ROWS_DISPLAY_MONITORS, .nrows=AZN(ROWS_DISPLAY_MONITORS)},
    { 0 },
};

const AzScreen *az_screens(void) { return SCREENS; }

int az_screen_count(void)
{
    int c = 0;
    while (SCREENS[c].id) c++;
    return c;
}

const AzScreen *az_screen_find(const char *id)
{
    for (int i = 0; SCREENS[i].id; i++)
        if (strcmp(SCREENS[i].id, id) == 0) return &SCREENS[i];
    return NULL;
}
