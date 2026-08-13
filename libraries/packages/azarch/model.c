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
 * system behaviour. `azarch` is on PATH on the guest; the command runs INSIDE the UI with its
 * output captured (see main.c / action.c), never dropping to the real terminal. `.needs_root`
 * marks the applies that first take a sudo credential; `.show_output` shows their output.
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

/* Like az_capture but keeps the WHOLE output (up to n-1 bytes), newlines and all, so a
 * multi-line report can be scanned with strstr. Same fork/exec/no-shell contract. Needed by
 * the rfkill/bluetooth probes, whose telltale "... blocked: yes" lines are NOT on line 1. */
static int az_capture_all(const char *const argv[], char *buf, size_t n)
{
    if (n == 0) return -1;
    buf[0] = '\0';
    int pipefd[2];
    if (pipe(pipefd) != 0) return -1;
    pid_t pid = fork();
    if (pid < 0) { close(pipefd[0]); close(pipefd[1]); return -1; }
    if (pid == 0) {
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
    ssize_t r;
    while (off < n - 1 && (r = read(pipefd[0], buf + off, n - 1 - off)) > 0)
        off += (size_t)r;
    buf[off] = '\0';
    char drain[256];
    while (read(pipefd[0], drain, sizeof drain) > 0) { }   /* keep child unblocked */
    close(pipefd[0]);
    int status = 0;
    waitpid(pid, &status, 0);
    if (!WIFEXITED(status)) return -1;
    return WEXITSTATUS(status);
}

/* --- probe cache (this is what makes navigation feel INSTANT) ---------------
 * Every status probe forks a tool (nmcli/ufw/systemctl/rfkill/gsettings). Called straight
 * from the draw loop, that means several forks PER KEYSTROKE -- the source of the lag. So all
 * probe calls go through az_status_cached(): it memoises each probe's last result by function
 * pointer for a short TTL, so holding a key, typing in the search box, or any redraw that is
 * not a genuine state change re-forks NOTHING. The first draw after the TTL refreshes it.
 *
 * The clock is CLOCK_MONOTONIC (immune to wall-clock jumps). The TTL is deliberately short so
 * the shown status still tracks reality within ~1.5s; an apply also busts the cache outright
 * (az_status_invalidate) so a toggle's effect shows immediately, not after the TTL. */
#include <time.h>

#define AZ_CACHE_TTL_MS 1500
#define AZ_CACHE_SLOTS  16

typedef const char *(*AzProbe)(char *, size_t);
typedef struct { AzProbe fn; long stamp_ms; char val[128]; } AzCacheSlot;
static AzCacheSlot g_cache[AZ_CACHE_SLOTS];

static long az_now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

const char *az_status_cached(const char *(*fn)(char *, size_t), char *buf, size_t n)
{
    if (!fn) { if (n) buf[0] = '\0'; return buf; }
    long now = az_now_ms();
    AzCacheSlot *slot = NULL, *free_slot = NULL;
    for (int i = 0; i < AZ_CACHE_SLOTS; i++) {
        if (g_cache[i].fn == fn) { slot = &g_cache[i]; break; }
        if (!free_slot && g_cache[i].fn == NULL) free_slot = &g_cache[i];
    }
    if (slot && (now - slot->stamp_ms) < AZ_CACHE_TTL_MS) {
        snprintf(buf, n, "%s", slot->val);       /* fresh enough -> no fork */
        return buf;
    }
    /* Miss (or stale): run the probe for real, then remember it. */
    char tmp[128];
    const char *r = fn(tmp, sizeof tmp);
    if (!r) r = "";
    if (!slot) slot = free_slot ? free_slot : &g_cache[0];  /* evict slot 0 if the table is full */
    slot->fn = fn;
    slot->stamp_ms = now;
    snprintf(slot->val, sizeof slot->val, "%s", r);
    snprintf(buf, n, "%s", slot->val);
    return buf;
}

void az_status_invalidate(void)
{
    for (int i = 0; i < AZ_CACHE_SLOTS; i++) { g_cache[i].fn = NULL; g_cache[i].stamp_ms = 0; }
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
    /* gsettings get org.gnome.desktop.interface color-scheme -> 'prefer-dark' | ...
     * Reported with a Capitalised first letter ("Dark"/"White") -- the spec wants the
     * "Current:" line and the row status to read "Dark", not "dark". */
    const char *argv[] = {"gsettings", "get", "org.gnome.desktop.interface",
                          "color-scheme", NULL};
    char raw[128] = {0};
    if (have("gsettings") && az_capture(argv, raw, sizeof raw) == 0) {
        if (strstr(raw, "prefer-dark")) { snprintf(buf, n, "Dark"); return buf; }
        if (strstr(raw, "prefer-light")) { snprintf(buf, n, "White"); return buf; }
    }
    snprintf(buf, n, "Dark");   /* Az'arch default */
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
    /* Report WITH the ".png" file type ("years.png"), per the spec -- not a bare "years". */
    const char *ids[] = {"years", "decades"};
    char img[512];
    for (size_t i = 0; i < sizeof ids / sizeof ids[0]; i++) {
        az_wallpaper_image(ids[i], img, sizeof img);
        if (cur[0] && strcmp(cur, img) == 0) { snprintf(buf, n, "%s.png", ids[i]); return buf; }
    }
    snprintf(buf, n, "%s", cur[0] ? "custom" : "years.png");
    return buf;
}

/* Wifi and Wired are ONE-OR-THE-OTHER, never both "on"/"connected" at once (the spec:
 * "if wired is connected then wifi is off, if wifi is connected then wired is disconnected").
 * Both probes read the SAME device table once and decide from a single source of truth: the
 * connected ethernet device wins. So we scan devices for (a) is any ethernet connected and
 * (b) is any wifi connected, then each probe reports its own line in light of the other. */
struct AzNet { int eth_present, eth_conn, wifi_present, wifi_conn; };

static struct AzNet az_net_scan(void)
{
    struct AzNet s = {0};
    const char *argv[] = {"nmcli", "-t", "-f", "TYPE,STATE", "device", NULL};
    char raw[1024] = {0};
    if (az_capture_all(argv, raw, sizeof raw) != 0 || !raw[0]) return s;
    for (char *line = strtok(raw, "\n"); line; line = strtok(NULL, "\n")) {
        if (strncmp(line, "ethernet:", 9) == 0) {
            s.eth_present = 1;
            if (strstr(line, ":connected")) s.eth_conn = 1;
        } else if (strncmp(line, "wifi:", 5) == 0) {
            s.wifi_present = 1;
            if (strstr(line, ":connected")) s.wifi_conn = 1;
        }
    }
    return s;
}

/* Wifi, as the Wifi screen's one "Current:" line. "connected" only when wifi is the ACTIVE
 * link; "off" whenever wired is connected (one-or-the-other) or there is no wifi hardware;
 * otherwise the radio state ("on"/"off"). */
const char *az_status_wifi(char *buf, size_t n)
{
    if (!have("nmcli")) { snprintf(buf, n, "unavailable"); return buf; }
    struct AzNet s = az_net_scan();
    if (s.eth_conn) { snprintf(buf, n, "off"); return buf; }   /* wired wins -> wifi off */
    if (s.wifi_conn) { snprintf(buf, n, "connected"); return buf; }
    if (!s.wifi_present) { snprintf(buf, n, "off"); return buf; }
    /* wifi present but not the active link: report the radio switch. */
    const char *argv[] = {"nmcli", "radio", "wifi", NULL};
    char raw[64] = {0};
    if (az_capture(argv, raw, sizeof raw) == 0 && raw[0])
        snprintf(buf, n, "%s", strcmp(raw, "enabled") == 0 ? "on" : "off");
    else
        snprintf(buf, n, "off");
    return buf;
}

/* Wired (ethernet), as the Wired screen's one "Current:" line. "connected" when ethernet is
 * the active link; "disconnected" when wifi is the active link (one-or-the-other) or the
 * device is simply down; "no device" when there is no ethernet at all. */
const char *az_status_wired(char *buf, size_t n)
{
    if (!have("nmcli")) { snprintf(buf, n, "unavailable"); return buf; }
    struct AzNet s = az_net_scan();
    if (!s.eth_present) { snprintf(buf, n, "no device"); return buf; }
    snprintf(buf, n, s.eth_conn ? "connected" : "disconnected");
    return buf;
}

const char *az_status_bluetooth(char *buf, size_t n)
{
    /* A plain ON or OFF -- never "present" (present is not a state a user can act on). The
     * default is OFF (the ISO ships bluetooth disabled). Mirrors network.py _bt_state: it is
     * ON only when the service is active AND rfkill has not blocked the radio; anything else
     * (blocked, inactive, or unreadable) reads as OFF. */
    int active = 0;
    if (have("systemctl")) {
        const char *argv[] = {"systemctl", "is-active", "bluetooth", NULL};
        char raw[32] = {0};
        az_capture(argv, raw, sizeof raw);        /* "active" only when running */
        active = strcmp(raw, "active") == 0;
    }
    if (have("rfkill")) {
        const char *argv[] = {"rfkill", "list", "bluetooth", NULL};
        char raw[512] = {0};
        if (az_capture_all(argv, raw, sizeof raw) == 0 &&
            (strstr(raw, "Soft blocked: yes") || strstr(raw, "Hard blocked: yes"))) {
            snprintf(buf, n, "off");              /* radio blocked -> off regardless */
            return buf;
        }
    }
    snprintf(buf, n, active ? "on" : "off");
    return buf;
}

const char *az_status_airplane(char *buf, size_t n)
{
    /* A plain ON or OFF. Airplane REALLY means "no networking" -- the internet actually drops
     * -- so it is driven by NetworkManager's master switch, not just the radios (a wired VM
     * has no radio to kill). `nmcli networking` prints "enabled"/"disabled"; airplane is ON
     * when it is "disabled". Mirrors network.py _airplane_is_on. rfkill is the fallback. */
    if (have("nmcli")) {
        const char *argv[] = {"nmcli", "networking", NULL};
        char raw[64] = {0};
        if (az_capture(argv, raw, sizeof raw) == 0 && raw[0]) {
            snprintf(buf, n, strcmp(raw, "disabled") == 0 ? "on" : "off");
            return buf;
        }
    }
    if (have("rfkill")) {
        const char *argv[] = {"rfkill", "list", NULL};
        char raw[2048] = {0};
        if (az_capture_all(argv, raw, sizeof raw) == 0 && strstr(raw, "blocked")) {
            /* on only if at least one radio is listed and none is left unblocked ("no"). */
            snprintf(buf, n, strstr(raw, "blocked: no") ? "off" : "on");
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
    /* The top-level Network row says, in plain words, whether the machine can reach the
     * internet -- NOT a pile of radio/firewall jargon. "Online - Connected to Internet" when
     * NetworkManager reports full connectivity, "Offline - No Internet" otherwise. This is the
     * one thing a developer actually cares about at a glance. */
    if (have("nmcli")) {
        const char *argv[] = {"nmcli", "networking", "connectivity", NULL};
        char raw[32] = {0};
        if (az_capture(argv, raw, sizeof raw) == 0 && strcmp(raw, "full") == 0) {
            snprintf(buf, n, "Online - Connected to Internet");
            return buf;
        }
    }
    snprintf(buf, n, "Offline - No Internet");
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
        const char *s = az_status_cached(r->status, sb, sizeof sb);
        if (s && ci_contains(s, q)) return 1;
    }
    return 0;
}

/* The bash command a row teaches. APPLY -> the command verbatim; PORT -> the command with a
 * "<port>" placeholder (that is exactly what the user would type); SCREEN -> NULL. Returned
 * from a small static buffer for the PORT case (there is one hovered row at a time). */
const char *az_row_command(const AzRow *r)
{
    if (!r) return NULL;
    if (r->kind == AZ_ACT_APPLY) return r->target;
    if (r->kind == AZ_ACT_PORT) {
        static char buf[160];
        snprintf(buf, sizeof buf, "%s <port>", r->target ? r->target : "");
        return buf;
    }
    return NULL;
}

/* --- the screen tree -------------------------------------------------------- */
/* Actions are shell command lines run through the installed `azarch` CLI. main.c runs
 * them INSIDE the UI (output captured, shown in the results overlay), then shows a result. */

/* All rows use DESIGNATED initializers: any field not named is zero (NULL / AZ_PV_NONE /
 * needs_root==0 / show_output==0), so adding a field never forces touching every row and the
 * intent of each row is self-documenting. `.needs_root = 1` marks an apply that first secures a
 * sudo credential; `.show_output = 1` shows its captured output in the overlay. */

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
 * Applying a theme/wallpaper needs no sudo (it configures the user session), so needs_root
 * stays 0; the apply still runs inside the UI (captured), so no CLI text flashes over it. */
static const AzRow ROWS_THEME[] = {
    {.label="Dark",  .kind=AZ_ACT_APPLY, .target="azarch theme --dark",
     .preview=AZ_PV_THEME, .preview_arg="dark",
     .hint="The default. Everything follows it (kitty is exempt)."},
    {.label="White", .kind=AZ_ACT_APPLY, .target="azarch theme --white",
     .preview=AZ_PV_THEME, .preview_arg="white",
     .hint="Kitty keeps its own look regardless of the system theme."},
};

static const AzRow ROWS_WALLPAPER[] = {
    {.label="Years",   .kind=AZ_ACT_APPLY, .target="azarch wallpaper --years.png",
     .preview=AZ_PV_WALLPAPER, .preview_arg="years"},
    {.label="Decades", .kind=AZ_ACT_APPLY, .target="azarch wallpaper --decades.png",
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
    {.label="Turn wifi on",         .kind=AZ_ACT_APPLY, .target="azarch network wifi on",   .needs_root=1},
    {.label="Turn wifi off",        .kind=AZ_ACT_APPLY, .target="azarch network wifi off",  .needs_root=1},
    {.label="Scan / list networks", .kind=AZ_ACT_APPLY, .target="azarch network wifi list", .needs_root=1, .show_output=1},
    {.label="Disconnect",           .kind=AZ_ACT_APPLY, .target="azarch network wifi disconnect", .needs_root=1,
     .hint="To connect: azarch network wifi connect <name> <password>"},
};

static const AzRow ROWS_WIRED[] = {
    {.label="Turn wired on",  .kind=AZ_ACT_APPLY, .target="azarch network wired on",  .needs_root=1},
    {.label="Turn wired off", .kind=AZ_ACT_APPLY, .target="azarch network wired off", .needs_root=1},
};

static const AzRow ROWS_BLUETOOTH[] = {
    {.label="Turn bluetooth on",   .kind=AZ_ACT_APPLY, .target="azarch network bluetooth on",  .needs_root=1},
    {.label="Turn bluetooth off",  .kind=AZ_ACT_APPLY, .target="azarch network bluetooth off", .needs_root=1},
    {.label="Scan / list devices", .kind=AZ_ACT_APPLY, .target="azarch network bluetooth scan", .needs_root=1, .show_output=1,
     .hint="Pair a device with: azarch network bluetooth pair <mac>"},
};

static const AzRow ROWS_AIRPLANE[] = {
    {.label="Turn airplane mode on",  .kind=AZ_ACT_APPLY, .target="azarch network airplane on", .needs_root=1,
     .hint="Turns networking off -- the internet actually drops."},
    {.label="Turn airplane mode off", .kind=AZ_ACT_APPLY, .target="azarch network airplane off", .needs_root=1},
};

/* Firewall: enable/disable, LIST the port rules right here in the overlay (show_output=1),
 * and open/close/delete a port by TYPING its number (AZ_ACT_PORT prompts, then appends the
 * port to the command). This is the in-UI firewall config the spec asks for -- no dropping
 * to a shell, no guessing the CLI. */
static const AzRow ROWS_FIREWALL[] = {
    {.label="Enable firewall",   .kind=AZ_ACT_APPLY, .target="azarch network firewall enable",  .needs_root=1},
    {.label="Disable firewall",  .kind=AZ_ACT_APPLY, .target="azarch network firewall disable", .needs_root=1},
    {.label="List ports",        .kind=AZ_ACT_APPLY, .target="azarch network firewall port list", .needs_root=1, .show_output=1},
    {.label="Open a port",       .kind=AZ_ACT_PORT,  .target="azarch network firewall port open",   .needs_root=1, .show_output=1,
     .hint="Allow a port through (you will type the number)."},
    {.label="Close a port",      .kind=AZ_ACT_PORT,  .target="azarch network firewall port close",  .needs_root=1, .show_output=1,
     .hint="Deny a port -- the rule stays in the list."},
    {.label="Delete a port rule", .kind=AZ_ACT_PORT, .target="azarch network firewall port delete", .needs_root=1, .show_output=1,
     .hint="Remove the rule entirely, back to the default policy."},
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
    /* Each network sub-screen shows its live state ONCE via .current (the "Current:" line at
     * the top), so the rows below stay label-only -- no repeated status echo. */
    {.id="network.wifi",      .title="Wifi",      .subtitle="Wireless.",
     .current=az_status_wifi,      .rows=ROWS_WIFI,      .nrows=AZN(ROWS_WIFI)},
    {.id="network.wired",     .title="Wired",     .subtitle="Ethernet.",
     .current=az_status_wired,     .rows=ROWS_WIRED,     .nrows=AZN(ROWS_WIRED)},
    {.id="network.bluetooth", .title="Bluetooth", .subtitle="Off by default.",
     .current=az_status_bluetooth, .rows=ROWS_BLUETOOTH, .nrows=AZN(ROWS_BLUETOOTH)},
    {.id="network.airplane",  .title="Airplane mode", .subtitle="One switch for all radios.",
     .current=az_status_airplane,  .rows=ROWS_AIRPLANE,  .nrows=AZN(ROWS_AIRPLANE)},
    {.id="network.firewall",  .title="Firewall",  .subtitle="ufw front-end.",
     .current=az_status_firewall,  .rows=ROWS_FIREWALL,  .nrows=AZN(ROWS_FIREWALL)},
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
