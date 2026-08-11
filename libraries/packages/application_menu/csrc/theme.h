/* Az'arch application menu (C/GTK3 port) -- shared palette + geometry constants.
 *
 * One-to-one port of theme.py: the Breeze-ish dark palette and the geometry
 * numbers, in ONE place so every module (window, app list, power row, search
 * box) reads the same values. No behaviour here -- just constants.
 *
 * The menu is a fixed-size borderless window CENTERED on the screen (OpenBox,
 * no panel); menu.c centers it via (screen - size) / 2.
 */
#ifndef AZ_THEME_H
#define AZ_THEME_H

/* --- Geometry (px) ------------------------------------------------------- */
#define AZ_DEFAULT_WIDTH   582   /* menu window width  (theme.py DEFAULT_WIDTH)  */
#define AZ_DEFAULT_HEIGHT  497   /* menu window height (theme.py DEFAULT_HEIGHT) */

/* How far OFF-screen the daemon parks the (still-mapped) window to hide it.
 * Instant-open key: a mapped window that is merely MOVED costs almost nothing to
 * bring on-screen (no re-expose), whereas a re-map re-exposes the whole tree.
 * See menu.py OFFSCREEN_MARGIN. */
#define AZ_OFFSCREEN_MARGIN 4000

/* --- Breeze-ish palette (hex strings, parsed via gdk_rgba_parse) --------- */
#define AZ_BG_COLOR         "#2a2e32"   /* window background */
#define AZ_SURFACE_COLOR    "#31363b"   /* lighter surface (search box, buttons) */
#define AZ_HOVER_COLOR      "#3b4045"   /* row hover background */
#define AZ_DIVIDER_COLOR    "#3a3f44"   /* subtle separators */
#define AZ_TEXT_COLOR       "#eff0f1"   /* near-white -- big app names */
#define AZ_SUBTEXT_COLOR    "#9aa0a6"   /* muted -- the type subtitle */
#define AZ_PLACEHOLDER_COLOR "#7f858a"  /* search placeholder text */

#define AZ_BORDER_COLOR     "#3daee9"   /* Breeze highlight blue */
#define AZ_SELECT_BORDER    "#3daee9"   /* outline of selected row / focused button */
#define AZ_SELECT_FILL      "#31383e"   /* subtle fill inside selected/hovered control */
#define AZ_SELECT_TEXT      "#ffffff"   /* text on a selected row */

/* Tk's DEFAULT Entry text-selection colours on the target (measured: an unstyled
 * tk.Entry reports selectbackground #c3c3c3, selectforeground #000000). menu.py never
 * overrides them, so the search box highlight must use these to look identical. */
#define AZ_TK_SEL_BG        "#c3c3c3"   /* search-box selection background (Tk default) */
#define AZ_TK_SEL_FG        "#000000"   /* search-box selection text       (Tk default) */

/* --- Scrollbar (arrow-less rounded pill, Kickoff style) ------------------ */
#define AZ_SCROLL_THUMB_WIDTH  6
#define AZ_SCROLL_TRACK_WIDTH  12
#define AZ_SCROLL_THUMB_COLOR  "#5c6166"
#define AZ_SCROLL_THUMB_HOVER  "#93989c"
#define AZ_SCROLL_GROOVE_COLOR "#33383d"
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
