/* Az'arch application menu -- runtime theme colour selection.
 *
 * Az'arch has a system-wide dark/light theme (dark by default). This menu follows it: it
 * reads the freedesktop color-scheme once at startup (az_theme_init) and az_color(role)
 * then returns the dark or light hex string for each colour role. See theme.h for the
 * roles and the AZ_*_COLOR macros that expand to az_color(role).
 *
 * HOW THE THEME IS DETECTED (in priority order, first hit wins):
 *   1. `gsettings get org.gnome.desktop.interface color-scheme` -> 'prefer-dark' / else.
 *      This is the freedesktop appearance standard `azarch theme` writes.
 *   2. ~/.config/gtk-3.0/settings.ini gtk-application-prefer-dark-theme=1.
 *   3. Default: DARK (the Az'arch default).
 * All best-effort: any probe that fails falls through to the next, then to the dark default.
 */
#include "theme.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* The DARK palette (the Breeze-ish default) -- index by AzColorRole. */
static const char *AZ_PALETTE_DARK[AZ_C_COUNT] = {
    [AZ_C_BG]                 = "#2a2e32",
    [AZ_C_SURFACE]            = "#31363b",
    [AZ_C_HOVER]              = "#3b4045",
    [AZ_C_DIVIDER]            = "#3a3f44",
    [AZ_C_TEXT]               = "#eff0f1",
    [AZ_C_SUBTEXT]            = "#9aa0a6",
    [AZ_C_PLACEHOLDER]        = "#7f858a",
    [AZ_C_BORDER]             = "#3daee9",
    [AZ_C_SELECT_BORDER]      = "#3daee9",
    [AZ_C_SELECT_FILL]        = "#31383e",
    [AZ_C_SELECT_TEXT]        = "#ffffff",
    [AZ_C_SEL_BG]             = "#c3c3c3",
    [AZ_C_SEL_FG]             = "#000000",
    [AZ_C_SCROLL_THUMB]       = "#5c6166",
    [AZ_C_SCROLL_THUMB_HOVER] = "#93989c",
    [AZ_C_SCROLL_GROOVE]      = "#33383d",
};

/* The LIGHT palette -- an Adwaita-light-ish set matching the light OpenBox theme:
 * near-white surfaces, dark text, the same Breeze highlight blue for selection so the two
 * themes feel like one family. */
static const char *AZ_PALETTE_LIGHT[AZ_C_COUNT] = {
    [AZ_C_BG]                 = "#fafafa",
    [AZ_C_SURFACE]            = "#ffffff",
    [AZ_C_HOVER]              = "#ededed",
    [AZ_C_DIVIDER]            = "#d3d3d3",
    [AZ_C_TEXT]               = "#1b2430",
    [AZ_C_SUBTEXT]            = "#5a6b7b",
    [AZ_C_PLACEHOLDER]        = "#8a9099",
    [AZ_C_BORDER]             = "#3daee9",
    [AZ_C_SELECT_BORDER]      = "#3daee9",
    [AZ_C_SELECT_FILL]        = "#e3f1fb",
    [AZ_C_SELECT_TEXT]        = "#ffffff",
    [AZ_C_SEL_BG]             = "#c3c3c3",
    [AZ_C_SEL_FG]             = "#000000",
    [AZ_C_SCROLL_THUMB]       = "#b0b3b6",
    [AZ_C_SCROLL_THUMB_HOVER] = "#8a8e92",
    [AZ_C_SCROLL_GROOVE]      = "#e6e6e6",
};

static int az_dark = 1;      /* latched theme; dark is the Az'arch default */
static int az_inited = 0;

/* Read the whole of a file into buf (NUL-terminated); returns 1 on success. */
static int read_file(const char *path, char *buf, size_t bufsz) {
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    size_t n = fread(buf, 1, bufsz - 1, f);
    fclose(f);
    buf[n] = '\0';
    return 1;
}

/* gsettings color-scheme: 1 = dark, 0 = light, -1 = unknown/unavailable. */
static int probe_gsettings(void) {
    FILE *p = popen("gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null", "r");
    if (!p) return -1;
    char out[128] = {0};
    size_t n = fread(out, 1, sizeof(out) - 1, p);
    int rc = pclose(p);
    if (rc != 0 || n == 0) return -1;
    out[n] = '\0';
    if (strstr(out, "prefer-dark")) return 1;
    if (strstr(out, "prefer-light") || strstr(out, "default")) return 0;
    return -1;
}

/* ~/.config/gtk-3.0/settings.ini prefer-dark flag: 1 dark, 0 light, -1 unknown. */
static int probe_gtk_ini(void) {
    const char *home = getenv("HOME");
    if (!home || !*home) return -1;
    char path[1024];
    snprintf(path, sizeof(path), "%s/.config/gtk-3.0/settings.ini", home);
    char buf[4096];
    if (!read_file(path, buf, sizeof(buf))) return -1;
    const char *k = strstr(buf, "gtk-application-prefer-dark-theme");
    if (!k) return -1;
    const char *eq = strchr(k, '=');
    if (!eq) return -1;
    /* skip spaces after '=' */
    for (const char *c = eq + 1; *c && *c != '\n'; ++c) {
        if (*c == '1') return 1;
        if (*c == '0') return 0;
        if (*c != ' ' && *c != '\t') break;
    }
    return -1;
}

int az_theme_init(void) {
    int v = probe_gsettings();
    if (v < 0) v = probe_gtk_ini();
    az_dark = (v < 0) ? 1 : v;   /* default dark */
    az_inited = 1;
    return az_dark;
}

int az_theme_is_dark(void) {
    if (!az_inited) az_theme_init();
    return az_dark;
}

const char *az_color(AzColorRole role) {
    if (!az_inited) az_theme_init();
    if (role < 0 || role >= AZ_C_COUNT) return "#000000";
    const char *c = (az_dark ? AZ_PALETTE_DARK : AZ_PALETTE_LIGHT)[role];
    return c ? c : "#000000";
}
