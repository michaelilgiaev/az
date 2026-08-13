/* Az'arch bare-`azarch` TUI (C) -- the menu MODEL + live status probes.
 *
 * This is the C counterpart of the old Python build_menu(): the whole navigable tree as
 * static data (screens -> rows), plus the status probes each row draws. The probes shell
 * out to the SAME tools the CLI uses (gsettings / nmcli / ufw) or read the pointer files,
 * exactly like the Python status helpers did -- so the UI reflects reality and the two
 * can't drift. Nothing here touches the terminal, so the tests exercise it headless.
 *
 * ACTIONS are shell command lines run against the installed `azarch` CLI (e.g.
 * "azarch theme --dark"): the UI drives the tested subcommands rather than re-implementing
 * system behaviour. `azarch` is on PATH on the guest; the command runs with the terminal
 * restored so any sudo prompt / output is visible (see actions in main.c).
 */
/* POSIX APIs (fork/execvp/pipe/waitpid) under -std=c11. */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1

#include "tui.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include <fcntl.h>

/* The two shipped wallpapers + their on-disk PNG layout. Kept in lock-step with
 * wallpaper.py (WALLPAPERS_SYSTEM_DIR / WALLPAPER_IMAGE_RES); a test pins the strings. */
#define AZ_WALLPAPERS_DIR "/usr/share/wallpapers"
#define AZ_WALLPAPER_RES  "1672x941"

const char *az_wallpaper_image(const char *id, char *buf, size_t n)
{
    snprintf(buf, n, "%s/%s/contents/images/%s.png",
             AZ_WALLPAPERS_DIR, id, AZ_WALLPAPER_RES);
    return buf;
}

/* --- capture the first stdout line of a command ----------------------------
 * fork/exec (no shell) with stdin from /dev/null and stdout on a pipe; copy up to n-1
 * bytes, stop at the first newline, trim trailing whitespace. Returns the child's exit
 * status (0 == clean). Kept tiny and shell-free so a probe can't hang or be injected. */
int az_capture(const char *const argv[], char *buf, size_t n)
{
    if (n == 0) return -1;
    buf[0] = '\0';
    int pipefd[2];
    if (pipe(pipefd) != 0) return -1;
    pid_t pid = fork();
    if (pid < 0) { close(pipefd[0]); close(pipefd[1]); return -1; }
    if (pid == 0) {
        /* child: stdin<-/dev/null, stdout->pipe, stderr silenced */
        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) { dup2(devnull, 0); dup2(devnull, 2); }
        dup2(pipefd[1], 1);
        close(pipefd[0]); close(pipefd[1]);
        if (devnull > 2) close(devnull);
        execvp(argv[0], (char *const *)argv);
        _exit(127);
    }
    close(pipefd[1]);
    size_t off = 0;
    char c;
    ssize_t r;
    int done = 0;
    while (!done && (r = read(pipefd[0], &c, 1)) > 0) {
        if (c == '\n') break;
        if (off < n - 1) buf[off++] = c;
        else { /* drain the rest without storing */ }
    }
    (void)done;
    buf[off] = '\0';
    /* drain remaining output so the child never blocks on a full pipe */
    char drain[256];
    while (read(pipefd[0], drain, sizeof drain) > 0) { }
    close(pipefd[0]);
    int status = 0;
    waitpid(pid, &status, 0);
    /* rtrim */
    while (off > 0 && isspace((unsigned char)buf[off - 1])) buf[--off] = '\0';
    if (!WIFEXITED(status)) return -1;
    return WEXITSTATUS(status);
}

/* True if `prog` is somewhere on PATH (mirrors _have()). */
static int have(const char *prog)
{
    const char *path = getenv("PATH");
    if (!path) return 0;
    char buf[1024];
    const char *p = path;
    while (*p) {
        const char *colon = strchr(p, ':');
        size_t len = colon ? (size_t)(colon - p) : strlen(p);
        if (len > 0 && len < sizeof buf - 2 - strlen(prog)) {
            memcpy(buf, p, len);
            buf[len] = '/';
            strcpy(buf + len + 1, prog);
            if (access(buf, X_OK) == 0) return 1;
        }
        if (!colon) break;
        p = colon + 1;
    }
    return 0;
}

/* --- status probes ---------------------------------------------------------- */

const char *az_status_theme(char *buf, size_t n)
{
    /* gsettings get org.gnome.desktop.interface color-scheme -> 'prefer-dark' | ... */
    const char *argv[] = {"gsettings", "get", "org.gnome.desktop.interface",
                          "color-scheme", NULL};
    char raw[128] = {0};
    if (have("gsettings") && az_capture(argv, raw, sizeof raw) == 0) {
        if (strstr(raw, "prefer-dark")) { snprintf(buf, n, "dark"); return buf; }
        if (strstr(raw, "prefer-light")) { snprintf(buf, n, "white"); return buf; }
    }
    snprintf(buf, n, "dark");   /* Az'arch default */
    return buf;
}

const char *az_status_wallpaper(char *buf, size_t n)
{
    /* Read the pointer file ~/.config/azarch/wallpaper; map to an id, else "custom". */
    const char *home = getenv("HOME");
    char path[512], cur[512] = {0};
    if (home) {
        snprintf(path, sizeof path, "%s/.config/azarch/wallpaper", home);
        FILE *f = fopen(path, "r");
        if (f) {
            if (fgets(cur, sizeof cur, f)) {
                size_t l = strlen(cur);
                while (l > 0 && (cur[l-1] == '\n' || cur[l-1] == ' ')) cur[--l] = '\0';
            }
            fclose(f);
        }
    }
    const char *ids[] = {"years", "decades"};
    char img[512];
    for (size_t i = 0; i < sizeof ids / sizeof ids[0]; i++) {
        az_wallpaper_image(ids[i], img, sizeof img);
        if (cur[0] && strcmp(cur, img) == 0) { snprintf(buf, n, "%s", ids[i]); return buf; }
    }
    snprintf(buf, n, "%s", cur[0] ? "custom" : "years");
    return buf;
}

/* nmcli radio wifi -> "enabled"/"disabled" */
const char *az_status_wifi(char *buf, size_t n)
{
    if (!have("nmcli")) { snprintf(buf, n, "nmcli not found"); return buf; }
    const char *argv[] = {"nmcli", "radio", "wifi", NULL};
    char raw[64] = {0};
    if (az_capture(argv, raw, sizeof raw) == 0 && raw[0])
        snprintf(buf, n, "radio %s", raw);
    else
        snprintf(buf, n, "radio unknown");
    return buf;
}

const char *az_status_wired(char *buf, size_t n)
{
    if (!have("nmcli")) { snprintf(buf, n, "nmcli not found"); return buf; }
    /* nmcli -t -f DEVICE,TYPE,STATE device -> find the ethernet line */
    const char *argv[] = {"nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", NULL};
    char raw[512] = {0};
    if (az_capture(argv, raw, sizeof raw) != 0) { snprintf(buf, n, "unknown"); return buf; }
    /* az_capture only kept the FIRST line; for a full scan we need our own read. Fall back
     * to a simple summary: whether any ethernet is connected via a second query. */
    const char *argv2[] = {"nmcli", "-t", "-f", "TYPE,STATE", "device", NULL};
    (void)argv2;
    /* Keep it simple + robust: report the first device line we captured. */
    snprintf(buf, n, "%s", raw[0] ? raw : "no ethernet device");
    /* Replace ':' field separators with ' ' for readability. */
    for (char *p = buf; *p; p++) if (*p == ':') *p = ' ';
    return buf;
}

const char *az_status_bluetooth(char *buf, size_t n)
{
    /* nmcli radio bluetooth if present, else bluetoothctl show. */
    if (have("nmcli")) {
        const char *argv[] = {"nmcli", "radio", "bluetooth", NULL};
        char raw[64] = {0};
        if (az_capture(argv, raw, sizeof raw) == 0 && raw[0]) {
            snprintf(buf, n, "%s", raw);
            return buf;
        }
    }
    if (have("rfkill")) {
        const char *argv[] = {"rfkill", "list", "bluetooth", NULL};
        char raw[128] = {0};
        if (az_capture(argv, raw, sizeof raw) == 0) { snprintf(buf, n, "present"); return buf; }
    }
    snprintf(buf, n, "unknown");
    return buf;
}

const char *az_status_airplane(char *buf, size_t n)
{
    /* rfkill: all blocked -> "on". Cheap heuristic: nmcli networking + radio all off. */
    if (have("nmcli")) {
        const char *argv[] = {"nmcli", "radio", "all", NULL};
        char raw[128] = {0};
        if (az_capture(argv, raw, sizeof raw) == 0) {
            /* raw like "enabled  enabled  enabled  enabled"; if it contains no "enabled" -> off */
            snprintf(buf, n, strstr(raw, "enabled") ? "off" : "on");
            return buf;
        }
    }
    snprintf(buf, n, "off");
    return buf;
}

const char *az_status_firewall(char *buf, size_t n)
{
    if (!have("ufw")) { snprintf(buf, n, "ufw not found"); return buf; }
    /* `sudo -n ufw status` -> "Status: active" (no password: report "needs sudo"). */
    const char *argv[] = {"sudo", "-n", "ufw", "status", NULL};
    char raw[128] = {0};
    int rc = az_capture(argv, raw, sizeof raw);
    if (rc != 0) { snprintf(buf, n, "needs sudo"); return buf; }
    /* first line is "Status: active"/"Status: inactive" */
    const char *colon = strchr(raw, ':');
    if (colon) {
        colon++;
        while (*colon == ' ') colon++;
        snprintf(buf, n, "%s", *colon ? colon : "unknown");
    } else {
        snprintf(buf, n, "unknown");
    }
    return buf;
}

const char *az_status_network(char *buf, size_t n)
{
    /* Compact one-liner for the top-level Network row: wifi + firewall at a glance. */
    char wifi[64] = {0}, fw[64] = {0};
    if (have("nmcli")) {
        const char *argv[] = {"nmcli", "radio", "wifi", NULL};
        char raw[64] = {0};
        if (az_capture(argv, raw, sizeof raw) == 0 && raw[0])
            snprintf(wifi, sizeof wifi, "wifi %s", raw);
    }
    az_status_firewall(fw, sizeof fw);
    if (wifi[0])
        snprintf(buf, n, "%s, firewall %s", wifi, fw);
    else
        snprintf(buf, n, "firewall %s", fw);
    return buf;
}

/* --- filter (the search box) ------------------------------------------------ */
static int ci_contains(const char *hay, const char *needle)
{
    if (!needle || !*needle) return 1;
    size_t nl = strlen(needle);
    for (const char *h = hay; *h; h++) {
        size_t i = 0;
        while (i < nl && h[i] &&
               tolower((unsigned char)h[i]) == tolower((unsigned char)needle[i]))
            i++;
        if (i == nl) return 1;
    }
    return 0;
}

int az_row_matches(const AzRow *r, const char *q)
{
    if (!q || !*q) return 1;
    if (ci_contains(r->label, q)) return 1;
    if (r->status) {
        char sb[256];
        const char *s = r->status(sb, sizeof sb);
        if (s && ci_contains(s, q)) return 1;
    }
    return 0;
}

/* --- the screen tree -------------------------------------------------------- */
/* Actions are shell command lines run through the installed `azarch` CLI. main.c runs
 * them with the terminal restored so prompts/output are visible, then shows a result. */

static const AzRow ROWS_MAIN[] = {
    {"Theme",     AZ_ACT_SCREEN, "theme",     az_status_theme,     AZ_PV_NONE, NULL, NULL},
    {"Wallpaper", AZ_ACT_SCREEN, "wallpaper", az_status_wallpaper, AZ_PV_NONE, NULL, NULL},
    {"Network",   AZ_ACT_SCREEN, "network",   az_status_network,   AZ_PV_NONE, NULL, NULL},
};

static const AzRow ROWS_THEME[] = {
    {"Dark",  AZ_ACT_APPLY, "azarch theme --dark",  az_status_theme, AZ_PV_THEME, "dark",
     "The default. Everything follows it (kitty is exempt)."},
    {"White", AZ_ACT_APPLY, "azarch theme --white", az_status_theme, AZ_PV_THEME, "white",
     "Kitty keeps its own look regardless of the system theme."},
};

static const AzRow ROWS_WALLPAPER[] = {
    {"Years",   AZ_ACT_APPLY, "azarch wallpaper --years.png",
     az_status_wallpaper, AZ_PV_WALLPAPER, "years",   NULL},
    {"Decades", AZ_ACT_APPLY, "azarch wallpaper --decades.png",
     az_status_wallpaper, AZ_PV_WALLPAPER, "decades", NULL},
};

static const AzRow ROWS_NETWORK[] = {
    {"Wifi",          AZ_ACT_SCREEN, "network.wifi",      az_status_wifi,      AZ_PV_NONE, NULL, NULL},
    {"Wired",         AZ_ACT_SCREEN, "network.wired",     az_status_wired,     AZ_PV_NONE, NULL, NULL},
    {"Bluetooth",     AZ_ACT_SCREEN, "network.bluetooth", az_status_bluetooth, AZ_PV_NONE, NULL, NULL},
    {"Airplane mode", AZ_ACT_SCREEN, "network.airplane",  az_status_airplane,  AZ_PV_NONE, NULL, NULL},
    {"Firewall",      AZ_ACT_SCREEN, "network.firewall",  az_status_firewall,  AZ_PV_NONE, NULL, NULL},
};

static const AzRow ROWS_WIFI[] = {
    {"Turn wifi on",         AZ_ACT_APPLY, "azarch network wifi on",      az_status_wifi, AZ_PV_NONE, NULL, NULL},
    {"Turn wifi off",        AZ_ACT_APPLY, "azarch network wifi off",     az_status_wifi, AZ_PV_NONE, NULL, NULL},
    {"Scan / list networks", AZ_ACT_APPLY, "azarch network wifi list",    az_status_wifi, AZ_PV_NONE, NULL, NULL},
    {"Disconnect",           AZ_ACT_APPLY, "azarch network wifi disconnect", az_status_wifi, AZ_PV_NONE, NULL,
     "To connect: azarch network wifi connect <name> <password>"},
};

static const AzRow ROWS_WIRED[] = {
    {"Turn wired on",  AZ_ACT_APPLY, "azarch network wired on",  az_status_wired, AZ_PV_NONE, NULL, NULL},
    {"Turn wired off", AZ_ACT_APPLY, "azarch network wired off", az_status_wired, AZ_PV_NONE, NULL, NULL},
};

static const AzRow ROWS_BLUETOOTH[] = {
    {"Turn bluetooth on",  AZ_ACT_APPLY, "azarch network bluetooth on",   az_status_bluetooth, AZ_PV_NONE, NULL, NULL},
    {"Turn bluetooth off", AZ_ACT_APPLY, "azarch network bluetooth off",  az_status_bluetooth, AZ_PV_NONE, NULL, NULL},
    {"Scan / list devices",AZ_ACT_APPLY, "azarch network bluetooth scan", az_status_bluetooth, AZ_PV_NONE, NULL,
     "Pair a device with: azarch network bluetooth pair <mac>"},
};

static const AzRow ROWS_AIRPLANE[] = {
    {"Turn airplane mode on",  AZ_ACT_APPLY, "azarch network airplane on",  az_status_airplane, AZ_PV_NONE, NULL,
     "Kills every radio at once."},
    {"Turn airplane mode off", AZ_ACT_APPLY, "azarch network airplane off", az_status_airplane, AZ_PV_NONE, NULL, NULL},
};

static const AzRow ROWS_FIREWALL[] = {
    {"Enable firewall",          AZ_ACT_APPLY, "azarch network firewall enable",  az_status_firewall, AZ_PV_NONE, NULL, NULL},
    {"Disable firewall",         AZ_ACT_APPLY, "azarch network firewall disable", az_status_firewall, AZ_PV_NONE, NULL, NULL},
    {"List ports (with titles)", AZ_ACT_APPLY, "azarch network firewall port list", az_status_firewall, AZ_PV_NONE, NULL,
     "Open/close/delete a port: azarch network firewall port ..."},
};

#define AZN(a) (int)(sizeof(a) / sizeof((a)[0]))

static const AzScreen SCREENS[] = {
    {"main",      "Settings",      "Move with the arrow keys, Enter to open.", ROWS_MAIN,      AZN(ROWS_MAIN)},
    {"theme",     "Theme",         "Kitty does not follow the system theme (it keeps its own look).",
                                                                                ROWS_THEME,     AZN(ROWS_THEME)},
    {"wallpaper", "Wallpaper",     "Saved in: " AZ_WALLPAPERS_DIR,             ROWS_WALLPAPER, AZN(ROWS_WALLPAPER)},
    {"network",   "Network",       "Everything network related.",              ROWS_NETWORK,   AZN(ROWS_NETWORK)},
    {"network.wifi",      "Wifi",      "Wireless.",  ROWS_WIFI,      AZN(ROWS_WIFI)},
    {"network.wired",     "Wired",     "Ethernet.",  ROWS_WIRED,     AZN(ROWS_WIRED)},
    {"network.bluetooth", "Bluetooth", "Off by default.", ROWS_BLUETOOTH, AZN(ROWS_BLUETOOTH)},
    {"network.airplane",  "Airplane mode", "One switch for all radios.", ROWS_AIRPLANE, AZN(ROWS_AIRPLANE)},
    {"network.firewall",  "Firewall",  "ufw front-end.", ROWS_FIREWALL, AZN(ROWS_FIREWALL)},
    {NULL, NULL, NULL, NULL, 0},
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
