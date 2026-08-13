/* Az'arch bare-`azarch` TUI (C) -- the renderer (centred, coloured ANSI drawing).
 *
 * Pure terminal drawing over RAW ANSI (no ncurses): everything is CENTRED, the accent is
 * the logo cyan, the navigation keys are UPPERCASED and coloured. The renderer owns a
 * back buffer it fills each frame and flushes in one write(), so redraws don't flicker
 * and a keystroke repaints instantly.
 *
 * It draws TEXT only. The kitty image previews are placed separately (preview.c) into a
 * rectangle the renderer reserves and reports via az_render_preview_rect(), so the two
 * never fight over the same cells.
 */
#ifndef AZ_RENDER_H
#define AZ_RENDER_H

#include "tui.h"

/* The interactive UI state the renderer draws (owned by main.c). */
typedef struct {
    const char *stack[16];  /* screen-id breadcrumb; stack[0]=="main" */
    int depth;              /* number of ids on the stack (>=1)       */
    int sel;                /* selected VISIBLE row index             */
    char query[128];        /* search box contents                    */
    int searching;          /* is the search box focused              */
    char message[256];      /* last action result (shown briefly)     */
    int rows, cols;         /* terminal size                          */
} AzUI;

/* A rectangle in terminal cells (1-based row/col, like ANSI). */
typedef struct { int row, col, w, h; int valid; } AzRect;

/* The visible rows on the current screen after the search filter. Fills `out` (capacity
 * cap) with pointers into the model and returns the count. */
int az_visible_rows(const AzUI *ui, const AzRow **out, int cap);

/* The current screen (top of the stack). */
const AzScreen *az_ui_screen(const AzUI *ui);

/* Draw the whole frame for `ui` into an internal buffer and flush it to stdout. If
 * `preview_out` is non-NULL it receives the rectangle reserved for the hovered row's
 * preview (valid==0 when the row has none), so the caller can place the kitty image. */
void az_render(const AzUI *ui, AzRect *preview_out);

/* The bottom navigation line, as a plain (uncoloured) string -- used by tests to assert
 * the keys are advertised. Writes into buf (size n), returns buf. */
const char *az_nav_plain(char *buf, size_t n);

#endif /* AZ_RENDER_H */
