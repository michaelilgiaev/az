/* Az'arch application menu (C/GTK3) -- shared palette + geometry constants.
 *
 * The geometry numbers and font sizes are compile-time constants. The COLOURS are
 * RUNTIME-selected so the menu follows the system theme (dark by default, light when the
 * user runs `azarch theme --white`): every colour is an az_color(role) accessor that
 * returns the dark or light hex string depending on the system color-scheme, read ONCE at
 * startup by az_theme_init(). The AZ_*_COLOR names below are kept as macros that expand to
 * that accessor, so every existing call site (widget_bg(w, AZ_BG_COLOR),
 * gdk_rgba_parse(&c, AZ_TEXT_COLOR), the CSS g_strdup_printf, ...) keeps working unchanged
 * -- it still receives a const char* hex string, just the theme-correct one.
 *
 * The menu is a fixed-size borderless window CENTERED on the screen (OpenBox, no panel);
 * menu.c centers it via (screen - size) / 2.
 */
#ifndef AZ_THEME_H
#define AZ_THEME_H

/* --- Geometry (px) ------------------------------------------------------- */
#define AZ_DEFAULT_WIDTH   582   /* menu window width  */
#define AZ_DEFAULT_HEIGHT  497   /* menu window height */

/* How far OFF-screen the daemon parks the (still-mapped) window to hide it.
 * Instant-open key: a mapped window that is merely MOVED costs almost nothing to
 * bring on-screen (no re-expose), whereas a re-map re-exposes the whole tree.
 * menu.c reads this in hide_menu/warmup. */
#define AZ_OFFSCREEN_MARGIN 4000

/* --- Runtime theme colours ----------------------------------------------- */
/* Colour ROLES. az_color(role) returns the dark or light hex string for the role,
 * selected by the system theme az_theme_init() reads at startup. Keep in sync with the
 * palette tables in theme.c (AZ_PALETTE_DARK / AZ_PALETTE_LIGHT). */
typedef enum {
    AZ_C_BG = 0,        /* window background */
    AZ_C_SURFACE,       /* lighter surface (search box, buttons) */
    AZ_C_HOVER,         /* row hover background */
    AZ_C_DIVIDER,       /* subtle separators */
    AZ_C_TEXT,          /* big app names */
    AZ_C_SUBTEXT,       /* muted -- the type subtitle */
    AZ_C_PLACEHOLDER,   /* search placeholder text */
    AZ_C_BORDER,        /* Breeze highlight blue (focus border) */
    AZ_C_SELECT_BORDER, /* outline of selected row / focused button */
    AZ_C_SELECT_FILL,   /* subtle fill inside selected/hovered control */
    AZ_C_SELECT_TEXT,   /* text on a selected row */
    AZ_C_SEL_BG,        /* search-box selection background */
    AZ_C_SEL_FG,        /* search-box selection text */
    AZ_C_SCROLL_THUMB,  /* scrollbar thumb */
    AZ_C_SCROLL_THUMB_HOVER,
    AZ_C_SCROLL_GROOVE,
    AZ_C_COUNT
} AzColorRole;

/* Read the system color-scheme (freedesktop gsettings / GTK settings) and latch whether
 * the menu should render dark. Call ONCE early in main() before any widget is styled.
 * Returns 1 if dark, 0 if light. */
int az_theme_init(void);
/* 1 if the latched theme is dark, else 0 (valid after az_theme_init()). */
int az_theme_is_dark(void);
/* The hex colour string for a role under the latched theme (never NULL). */
const char *az_color(AzColorRole role);

/* The AZ_*_COLOR names as they were, now resolving to the runtime accessor so every
 * existing call site is unchanged. */
#define AZ_BG_COLOR          az_color(AZ_C_BG)
#define AZ_SURFACE_COLOR     az_color(AZ_C_SURFACE)
#define AZ_HOVER_COLOR       az_color(AZ_C_HOVER)
#define AZ_DIVIDER_COLOR     az_color(AZ_C_DIVIDER)
#define AZ_TEXT_COLOR        az_color(AZ_C_TEXT)
#define AZ_SUBTEXT_COLOR     az_color(AZ_C_SUBTEXT)
#define AZ_PLACEHOLDER_COLOR az_color(AZ_C_PLACEHOLDER)
#define AZ_BORDER_COLOR      az_color(AZ_C_BORDER)
#define AZ_SELECT_BORDER     az_color(AZ_C_SELECT_BORDER)
#define AZ_SELECT_FILL       az_color(AZ_C_SELECT_FILL)
#define AZ_SELECT_TEXT       az_color(AZ_C_SELECT_TEXT)
#define AZ_SEL_BG            az_color(AZ_C_SEL_BG)
#define AZ_SEL_FG            az_color(AZ_C_SEL_FG)
#define AZ_SCROLL_THUMB_COLOR  az_color(AZ_C_SCROLL_THUMB)
#define AZ_SCROLL_THUMB_HOVER  az_color(AZ_C_SCROLL_THUMB_HOVER)
#define AZ_SCROLL_GROOVE_COLOR az_color(AZ_C_SCROLL_GROOVE)

/* --- Scrollbar geometry (arrow-less rounded pill, Kickoff style) --------- */
#define AZ_SCROLL_THUMB_WIDTH  6
#define AZ_SCROLL_TRACK_WIDTH  12
#define AZ_SCROLL_THUMB_MIN    32

/* --- Fonts --------------------------------------------------------------- */
#define AZ_FONT_FAMILY   "Noto Sans"
#define AZ_FONT_APP_NAME 13   /* app-row NAME (big line)         */
#define AZ_FONT_APP_TYPE 10   /* app-row TYPE subtitle (muted)   */
#define AZ_FONT_SEARCH   13   /* search box entry + placeholder  */
#define AZ_FONT_POWER    12   /* bottom power-row button labels  */

/* Icon sizes (px). */
#define AZ_ICON_SIZE       44  /* app-row icon edge          */
#define AZ_POWER_ICON_SIZE 24  /* bottom power-button icon   */

/* Row metrics (applist), from applist.py CanvasAppList. */
#define AZ_ROW_H   56
#define AZ_ROW_PAD_X 8
#define AZ_ICON_X  26
#define AZ_TEXT_X  78
#define AZ_NAME_DY 18
#define AZ_SUB_DY  38

#endif /* AZ_THEME_H */
