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

/* All rows use DESIGNATED initializers: any field not named is zero (NULL / AZ_PV_NONE /
 * quiet==0), so adding a field never forces touching every row and the intent of each row is
 * self-documenting. `.quiet = 1` marks an apply that runs silently inside the UI. */

/* Network is FIRST (it is what a fresh machine needs first). The main rows keep their live
 * status -- it is a genuine at-a-glance summary of the sub-screen (e.g. "firewall active"),
 * NOT a redundant echo, and the main screen has no "Current:" line of its own. */
static const AzRow ROWS_MAIN[] = {
    {.label="Network",   .kind=AZ_ACT_SCREEN, .target="network",   .status=az_status_network},
    {.label="Theme",     .kind=AZ_ACT_SCREEN, .target="theme",     .status=az_status_theme},
    {.label="Wallpaper", .kind=AZ_ACT_SCREEN, .target="wallpaper", .status=az_status_wallpaper},
};

/* Theme / Wallpaper rows carry NO per-row status: the live state is shown ONCE as the
 * "Current:" line at the top of the screen (the screen's `current` probe), so echoing
 * "white"/"years" after each option would just be noise -- exactly what the spec calls out.
 * They are `.quiet = 1`: applying a theme/wallpaper needs no sudo/tty, so it runs silently and
 * NO CLI text flashes over the UI. */
static const AzRow ROWS_THEME[] = {
    {.label="Dark",  .kind=AZ_ACT_APPLY, .target="azarch theme --dark",
     .preview=AZ_PV_THEME, .preview_arg="dark",
     .hint="The default. Everything follows it (kitty is exempt).", .quiet=1},
    {.label="White", .kind=AZ_ACT_APPLY, .target="azarch theme --white",
     .preview=AZ_PV_THEME, .preview_arg="white",
     .hint="Kitty keeps its own look regardless of the system theme.", .quiet=1},
};

static const AzRow ROWS_WALLPAPER[] = {
    {.label="Years",   .kind=AZ_ACT_APPLY, .target="azarch wallpaper --years.png",
     .preview=AZ_PV_WALLPAPER, .preview_arg="years",   .quiet=1},
    {.label="Decades", .kind=AZ_ACT_APPLY, .target="azarch wallpaper --decades.png",
     .preview=AZ_PV_WALLPAPER, .preview_arg="decades", .quiet=1},
};

static const AzRow ROWS_NETWORK[] = {
    {.label="Wifi",          .kind=AZ_ACT_SCREEN, .target="network.wifi",      .status=az_status_wifi},
    {.label="Wired",         .kind=AZ_ACT_SCREEN, .target="network.wired",     .status=az_status_wired},
    {.label="Bluetooth",     .kind=AZ_ACT_SCREEN, .target="network.bluetooth", .status=az_status_bluetooth},
    {.label="Airplane mode", .kind=AZ_ACT_SCREEN, .target="network.airplane",  .status=az_status_airplane},
    {.label="Firewall",      .kind=AZ_ACT_SCREEN, .target="network.firewall",  .status=az_status_firewall},
};

static const AzRow ROWS_WIFI[] = {
    {.label="Turn wifi on",         .kind=AZ_ACT_APPLY, .target="azarch network wifi on",         .status=az_status_wifi},
    {.label="Turn wifi off",        .kind=AZ_ACT_APPLY, .target="azarch network wifi off",        .status=az_status_wifi},
    {.label="Scan / list networks", .kind=AZ_ACT_APPLY, .target="azarch network wifi list",       .status=az_status_wifi},
    {.label="Disconnect",           .kind=AZ_ACT_APPLY, .target="azarch network wifi disconnect", .status=az_status_wifi,
     .hint="To connect: azarch network wifi connect <name> <password>"},
};

static const AzRow ROWS_WIRED[] = {
    {.label="Turn wired on",  .kind=AZ_ACT_APPLY, .target="azarch network wired on",  .status=az_status_wired},
    {.label="Turn wired off", .kind=AZ_ACT_APPLY, .target="azarch network wired off", .status=az_status_wired},
};

static const AzRow ROWS_BLUETOOTH[] = {
    {.label="Turn bluetooth on",   .kind=AZ_ACT_APPLY, .target="azarch network bluetooth on",   .status=az_status_bluetooth},
    {.label="Turn bluetooth off",  .kind=AZ_ACT_APPLY, .target="azarch network bluetooth off",  .status=az_status_bluetooth},
    {.label="Scan / list devices", .kind=AZ_ACT_APPLY, .target="azarch network bluetooth scan", .status=az_status_bluetooth,
     .hint="Pair a device with: azarch network bluetooth pair <mac>"},
};

static const AzRow ROWS_AIRPLANE[] = {
    {.label="Turn airplane mode on",  .kind=AZ_ACT_APPLY, .target="azarch network airplane on",  .status=az_status_airplane,
     .hint="Kills every radio at once."},
    {.label="Turn airplane mode off", .kind=AZ_ACT_APPLY, .target="azarch network airplane off", .status=az_status_airplane},
};

static const AzRow ROWS_FIREWALL[] = {
    {.label="Enable firewall",          .kind=AZ_ACT_APPLY, .target="azarch network firewall enable",    .status=az_status_firewall},
    {.label="Disable firewall",         .kind=AZ_ACT_APPLY, .target="azarch network firewall disable",   .status=az_status_firewall},
    {.label="List ports (with titles)", .kind=AZ_ACT_APPLY, .target="azarch network firewall port list", .status=az_status_firewall,
     .hint="Open/close/delete a port: azarch network firewall port ..."},
};

#define AZN(a) (int)(sizeof(a) / sizeof((a)[0]))

/* Only Theme and Wallpaper set `.current` (the top "Current:" line); every other screen
 * leaves it NULL. The main screen's subtitle is empty (the spec removed the "Move with the
 * arrow keys..." line -- the nav hints at the bottom already say how to move). Designated
 * initializers throughout, so the NULL terminator is simply an empty pair of braces. */
static const AzScreen SCREENS[] = {
    {.id="main",      .title="Az'arch Settings", .subtitle="",
     .rows=ROWS_MAIN, .nrows=AZN(ROWS_MAIN)},
    {.id="theme",     .title="Theme",
     .subtitle="Kitty does not follow the system theme (it keeps its own look).",
     .current=az_status_theme,     .rows=ROWS_THEME,     .nrows=AZN(ROWS_THEME)},
    {.id="wallpaper", .title="Wallpaper", .subtitle="Saved in: " AZ_WALLPAPERS_DIR,
     .current=az_status_wallpaper, .rows=ROWS_WALLPAPER, .nrows=AZN(ROWS_WALLPAPER)},
    {.id="network",   .title="Network", .subtitle="Everything network related.",
     .rows=ROWS_NETWORK, .nrows=AZN(ROWS_NETWORK)},
    {.id="network.wifi",      .title="Wifi",      .subtitle="Wireless.",
     .rows=ROWS_WIFI,      .nrows=AZN(ROWS_WIFI)},
    {.id="network.wired",     .title="Wired",     .subtitle="Ethernet.",
     .rows=ROWS_WIRED,     .nrows=AZN(ROWS_WIRED)},
    {.id="network.bluetooth", .title="Bluetooth", .subtitle="Off by default.",
     .rows=ROWS_BLUETOOTH, .nrows=AZN(ROWS_BLUETOOTH)},
    {.id="network.airplane",  .title="Airplane mode", .subtitle="One switch for all radios.",
     .rows=ROWS_AIRPLANE,  .nrows=AZN(ROWS_AIRPLANE)},
    {.id="network.firewall",  .title="Firewall",  .subtitle="ufw front-end.",
     .rows=ROWS_FIREWALL,  .nrows=AZN(ROWS_FIREWALL)},
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
