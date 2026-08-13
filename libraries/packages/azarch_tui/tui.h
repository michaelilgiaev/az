/* Az'arch bare-`azarch` TERMINAL UI (C port) -- shared palette, geometry, model.
 *
 * WHY C. The Python/curses TUI felt laggy; every keystroke redrew through the
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
 * ACTIONS shell back to the SAME `azarch` subcommands the CLI exposes (azarch theme
 * --dark, azarch wallpaper --years.png, azarch network firewall enable, ...): the C UI
 * adds navigation + previews, not new system behaviour. Status is likewise read by
 * asking the underlying tools (nmcli/ufw/gsettings) or the pointer files.
 *
 * PREVIEWS use kitty's `kitten icat --place` graphics: the Wallpaper screen previews the
 * hovered wallpaper image; the Theme screen previews LibreWolf (the timedate home page)
 * and Dolphin rendered light/dark. kitty is deliberately exempt from the system theme,
 * which the Theme screen discloses.
 */
#ifndef AZ_TUI_H
#define AZ_TUI_H

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
    AZ_ACT_SCREEN = 0,   /* action.target names a child screen id to descend into  */
    AZ_ACT_APPLY,        /* action.target is a shell command line to run (an apply) */
} AzActionKind;

/* How a row should render its PREVIEW while hovered (right/lower pane). */
typedef enum {
    AZ_PV_NONE = 0,
    AZ_PV_WALLPAPER,     /* kitty-icat the wallpaper image for row->preview_arg (an id) */
    AZ_PV_THEME,         /* ANSI mock-ups of LibreWolf + Dolphin for row->preview_arg    */
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
    const char *hint;           /* optional one-line help shown under the list         */
} AzRow;

typedef struct {
    const char *id;             /* screen id ("main", "network.firewall", ...)         */
    const char *title;          /* shown in the breadcrumb                             */
    const char *subtitle;       /* context line (e.g. the wallpaper directory path)    */
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

/* --- Status probes (model.c) ------------------------------------------------
 * Each writes a short human string into buf and returns it. They shell out to the same
 * tools the CLI uses (or read the pointer files), and NEVER leave buf empty on error --
 * they degrade to a readable word so a probe can't blank a cell. */
const char *az_status_theme(char *buf, size_t n);
const char *az_status_wallpaper(char *buf, size_t n);
const char *az_status_wifi(char *buf, size_t n);
const char *az_status_wired(char *buf, size_t n);
const char *az_status_bluetooth(char *buf, size_t n);
const char *az_status_airplane(char *buf, size_t n);
const char *az_status_firewall(char *buf, size_t n);
const char *az_status_network(char *buf, size_t n);

/* Small shared helper (model.c): run `argv` (NULL-terminated), capture the first line of
 * stdout into buf (size n). Returns 0 on a clean exit, non-zero otherwise. Never blocks
 * on stdin. Used by the status probes. */
int az_capture(const char *const argv[], char *buf, size_t n);
/* Absolute path to the inner PNG for a wallpaper id (what the preview shows / what feh
 * paints). Mirrors wallpaper.py _wallpaper_image. Writes into buf, returns buf. */
const char *az_wallpaper_image(const char *id, char *buf, size_t n);

#endif /* AZ_TUI_H */
