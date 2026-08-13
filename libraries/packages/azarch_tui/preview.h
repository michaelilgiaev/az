/* Az'arch bare-`azarch` TUI (C) -- the hovered-row PREVIEW pane.
 *
 * Two kinds of preview, placed into the rectangle the renderer reserves:
 *
 *   WALLPAPER -- the actual wallpaper image, shown with kitty's `kitten icat --place`
 *                graphics (this is kitty; it can do it). The current wallpaper is named at
 *                the top of the screen by the renderer; hovering a choice previews IT.
 *
 *   THEME     -- ANSI mock-ups of the two apps that DO follow the system theme: LibreWolf
 *                (drawn as the timedate home page it lands on) and Dolphin (the file
 *                manager). They are redrawn light or dark to match the hovered choice, so
 *                the user sees the theme before applying it. (Kitty is exempt -- the
 *                Theme screen's subtitle says so.)
 */
#ifndef AZ_PREVIEW_H
#define AZ_PREVIEW_H

#include "render.h"

/* Place the preview for the hovered row of `ui` into `rect` (as returned by az_render).
 * Safe to call with rect->valid==0 (does nothing). Wallpaper previews shell out to
 * `kitten icat`; theme previews draw ANSI directly. Returns 1 if it drew a KITTY image
 * (so the caller knows the graphics need clearing on the next frame), else 0. */
int az_preview_draw(const AzUI *ui, const AzRect *rect);

/* Clear any kitty graphics currently on screen (called before a frame that had an image).
 * No-op-safe. */
void az_preview_clear(void);

#endif /* AZ_PREVIEW_H */
