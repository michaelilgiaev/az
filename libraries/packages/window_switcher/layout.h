/* Az'arch window switcher -- the horizontal tile strip (Windows-like overlay body).
 *
 * A centered dark rounded panel holding one tile per window, left to right in the order
 * ordering.c produced. Each tile is a live thumbnail (icon fallback) with the app icon
 * badged in the corner and the window title underneath; the selected tile carries a
 * Breeze-blue highlight border. Owns nothing about X input -- switcher.c drives selection.
 */
#ifndef AZ_LAYOUT_H
#define AZ_LAYOUT_H

#include <gtk/gtk.h>
#include <glib.h>

typedef struct AzStrip AzStrip;

/* Build the strip (a horizontal GtkBox) packed into `parent`. */
AzStrip *az_strip_new(GtkWidget *parent);

/* Rebuild tiles from GPtrArray<AzWinIdent*> (thumbnails captured now). Keeps the
 * selection index in range. The array is borrowed for the duration of the call. */
void     az_strip_set_windows(AzStrip *s, GPtrArray *windows);

/* Move the highlight to index i (wrapped into [0,count)). No-op when empty. */
void     az_strip_select(AzStrip *s, int i);
int      az_strip_selected(AzStrip *s);
int      az_strip_count(AzStrip *s);

/* XID of the selected tile's window, or 0 when empty. */
unsigned long az_strip_selected_xid(AzStrip *s);

void     az_strip_free(AzStrip *s);

#endif /* AZ_LAYOUT_H */
