/* Az'arch bare-`azarch` TERMINAL UI (C port) -- shared palette, geometry, model.
 *
 * WHY C. The Python/curses terminal user interface felt laggy; every keystroke redrew through the
 * interpreter and every action paid a fresh Python cold-start. This is a from-scratch
 * C rewrite driving the terminal with RAW ANSI + termios (no ncurses), so a keystroke
 * is a syscall and a diff, not an interpreter round-trip -- it feels instant.
 *
 * The three things a fresh machine needs tuned -- the colour Theme, the desktop
 * Wallpaper, and the Network -- are reachable by arrow keys (or WASD / HJKL), with the
 * current status shown right there and EVERYTHING centred on the screen. There is NO
 * Az'arch branding: it gets out of the way.
 *
 * COLOUR. The Az'arch accent is the logo cyan (#06B8FD). It marks the current screen,
 * the selection, the navigation keys, and the "Current" line -- everything the eye
 * should land on -- while the rest stays muted, so the screen is easy to read.
 *
 * ACTIONS shell back to the SAME `azarch` subcommands the command line interface exposes (azarch theme
 * --dark, azarch wallpaper --years.png, azarch network firewall enable, ...): the C UI
 * adds navigation + previews, not new system behaviour. Status is likewise read by
 * asking the underlying tools (nmcli/ufw/gsettings) or the pointer files.
 *
 * PREVIEWS use kitty's `kitten icat --place` graphics: the Wallpaper screen previews the
 * hovered wallpaper image; the Theme screen previews LibreWolf (the timedate home page)
 * and Dolphin rendered light/dark. kitty is deliberately exempt from the system theme,
 * which the Theme screen discloses.
 */
#ifndef AZ_TERMINAL_USER_INTERFACE_H
#define AZ_TERMINAL_USER_INTERFACE_H

#include <stddef.h>

/* --- The accent (Az'arch logo cyan #06B8FD) and the rest of the palette ------
 * Truecolor SGR strings. Terminals in the Az'arch build are kitty, which is truecolor;
 * we still keep the palette small and legible on a 256-colour fallback (the values are
 * close to xterm cyan). These are the ESCAPE BODIES (after "\033["), so they compose:
 *   printf("\033[%sm...\033[0m", AZ_SGR_ACCENT). */
#define AZ_SGR_RESET       "0"
#define AZ_SGR_ACCENT      "38;2;6;184;253"    /* #06B8FD -- the logo cyan (foreground) */
#define AZ_SGR_ACCENT_BG   "48;2;6;184;253"    /* the logo cyan as a background          */
#define AZ_SGR_ON_ACCENT   "38;2;8;15;20"      /* near-black text drawn ON the accent bg  */
#define AZ_SGR_DIM         "38;2;120;130;140"  /* muted grey -- secondary text            */
#define AZ_SGR_TEXT        "38;2;222;228;234"  /* primary text                            */
#define AZ_SGR_KEYCAP      "38;2;6;184;253"    /* nav key letters (coloured, per the spec)*/
#define AZ_SGR_OK          "38;2;120;220;150"  /* a healthy/on status (green)             */
#define AZ_SGR_WARN        "38;2;240;180;90"   /* an attention status (amber)             */
#define AZ_SGR_BOLD        "1"
#define AZ_SGR_DIM_ATTR    "2"

/* --- Model ------------------------------------------------------------------
 * The whole navigable tree is static data: a set of SCREENS, each a list of ROWS. A row
 * is a label + an optional live STATUS (probed at draw time) + an ACTION. The action is
 * either "descend into screen id S" or "run shell command C" (an apply). Kept as plain
 * C so it needs no terminal to reason about (and the tests read it directly). */

typedef enum {
    AZ_ACT_SCREEN = 0,   /* action.target names a child screen id to descend into      */
    AZ_ACT_APPLY,        /* action.target is a shell command line to run (an apply)     */
    AZ_ACT_PORT,         /* like APPLY, but PROMPT for a port first and append it to    */
                         /* action.target, e.g. "azarch network firewall port open"    */
} AzActionKind;

/* How a row should render its PREVIEW while hovered (right/lower pane). */
typedef enum {
    AZ_PV_NONE = 0,
    AZ_PV_WALLPAPER,     /* kitty-icat the wallpaper image for row->preview_arg (an id)  */
    AZ_PV_THEME,         /* kitty-icat the LibreWolf + Dolphin screenshots (dark/white)  */
} AzPreviewKind;

typedef struct {
    const char *label;          /* the row text (left, centred block)                 */
    AzActionKind kind;
    const char *target;         /* screen id (SCREEN) or shell command (APPLY)        */
    /* status: a function returning a short live string for this row, or NULL. It
     * writes into `buf` (size n) and returns buf; kept as a fn ptr so it is evaluated
     * fresh every draw and always reflects reality. */
    const char *(*status)(char *buf, size_t n);
    AzPreviewKind preview;
    const char *preview_arg;    /* wallpaper id / theme name for the preview           */
    /* base: the UNDERLYING tool command this row's `azarch` wrapper ultimately runs (the
     * gsettings/feh/wpctl/nmcli/ufw/... line a user would type WITHOUT azarch). The renderer
     * shows it as the "Base Command: $ ..." line above the "Azarch Wrapper: $ ..." line, and
     * `x` copies it to the clipboard. NULL for a SCREEN row (nothing to teach). For a PORT row
     * it carries the same "<port>" placeholder shape the wrapper does. */
    const char *base;
    /* EVERY apply now runs INSIDE the UI: its output is captured and shown in a centred
     * results overlay on the alt screen, so raw command line interface text never flashes over the UI and the
     * terminal is never "blacked out" or polluted (the fix for "selecting a setting turns the
     * screen black" and "Q leaves the terminal full of previous commands"). These two flags
     * describe an apply's needs; there is no more "drop to the real terminal" path.
     *
     *  needs_root -- the command runs privileged tools (ufw/nmcli/rfkill/systemctl). Before
     *      running it the UI ensures a sudo credential (an in-UI masked password prompt,
     *      cached for the session), so the apply never blocks on an invisible sudo prompt.
     *  show_output -- show the command's captured output in the results overlay (firewall
     *      "list ports" wants its table shown; a plain toggle just needs a one-line result). */
    int needs_root;
    int show_output;
} AzRow;

typedef struct {
    const char *id;             /* screen id ("main", "network.firewall", ...)         */
    const char *title;          /* shown in the breadcrumb                             */
    const char *subtitle;       /* context line (e.g. the wallpaper directory path)    */
    /* current: a probe for the "Current: X" line the renderer draws at the TOP of the
     * screen (Theme/Wallpaper want the live state shown once, up top). NULL == no line.
     * This is SEPARATE from the per-row status so the rows themselves can stay label-only
     * (no "white"/"years" echo trailing each option) while "Current:" still shows it. */
    const char *(*current)(char *buf, size_t n);
    /* subtitle_accent: draw the subtitle in the accent (cyan) and TIGHT against the line below
     * it (no blank spacer), instead of the default dim + spaced. Set for the Wallpaper screen,
     * whose subtitle is a directory PATH the spec wants coloured and placed right above the
     * "Current:" line. 0 keeps the muted, spaced prose look every other screen uses. */
    int subtitle_accent;
    const AzRow *rows;
    int nrows;
} AzScreen;

/* The screen table (model.c). Terminated by a screen whose id is NULL. */
const AzScreen *az_screens(void);
int az_screen_count(void);
/* Find a screen by id, or NULL. */
const AzScreen *az_screen_find(const char *id);

/* filter_items: does row `r` match the search query `q` (case-insensitive substring of
 * the label or its live status)? Empty/NULL q matches everything. Pure -- unit-tested. */
int az_row_matches(const AzRow *r, const char *q);

/* The one-line bash command a row teaches the user (shown under the list so they can run it
 * WITHOUT the UI). For an APPLY it is the command itself; for a PORT prompt it is the command
 * with a "<port>" placeholder; for a SCREEN it is NULL (nothing to teach). Pure. This is the
 * "Azarch Wrapper: $ ..." line, and `c` copies it. */
const char *az_row_command(const AzRow *r);

/* The UNDERLYING base command a row's wrapper runs (the gsettings/feh/wpctl/nmcli/ufw/... line
 * a user would type without azarch), for the "Base Command: $ ..." line that `x` copies. Returns
 * r->base verbatim for APPLY; for a PORT row it appends the same "<port>" placeholder the wrapper
 * shows; NULL for a SCREEN row or a row with no base. Pure. */
const char *az_row_base(const AzRow *r);

/* --- Status probes (model.c) ------------------------------------------------
 * Each writes a short human string into buf and returns it. They shell out to the same
 * tools the command line interface uses (or read the pointer files), and NEVER leave buf empty on error --
 * they degrade to a readable word so a probe can't blank a cell. */
const char *az_status_theme(char *buf, size_t n);
const char *az_status_wallpaper(char *buf, size_t n);
const char *az_status_wifi(char *buf, size_t n);
const char *az_status_wired(char *buf, size_t n);
const char *az_status_bluetooth(char *buf, size_t n);
const char *az_status_airplane(char *buf, size_t n);
const char *az_status_firewall(char *buf, size_t n);
const char *az_status_network(char *buf, size_t n);
const char *az_status_machine(char *buf, size_t n);
const char *az_status_volume(char *buf, size_t n);
const char *az_status_brightness(char *buf, size_t n);

/* Small shared helper (model.c): run `argv` (NULL-terminated), capture the first line of
 * stdout into buf (size n). Returns 0 on a clean exit, non-zero otherwise. Never blocks
 * on stdin. Used by the status probes. */
int az_capture(const char *const argv[], char *buf, size_t n);

/* --- probe cache (model.c) --------------------------------------------------
 * Run a status probe THROUGH a short-TTL memo keyed by the function pointer, so a redraw that
 * is not a real state change never re-forks the probe's tool. This is what keeps navigation
 * instant. The renderer calls every `.status`/`.current` probe via this, not directly.
 * az_status_invalidate() drops all cached values -- call it right after an apply so a toggle's
 * new state shows on the very next frame instead of after the TTL. */
const char *az_status_cached(const char *(*fn)(char *, size_t), char *buf, size_t n);
void az_status_invalidate(void);
/* Absolute path to the inner PNG for a wallpaper id (what the preview shows / what feh
 * paints). Mirrors wallpaper.py _wallpaper_image. Writes into buf, returns buf. */
const char *az_wallpaper_image(const char *id, char *buf, size_t n);

#endif /* AZ_TERMINAL_USER_INTERFACE_H */
