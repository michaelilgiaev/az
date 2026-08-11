/* Az'arch application menu (C port) -- Kickoff-style scrollbar.
 *
 * A pixel-faithful re-creation of Plasma Kickoff's scrollbar (widgets.py
 * KickoffScrollBar), because both the classic Tk scrollbar AND the default GTK
 * scrollbar look nothing like it. It is:
 *   * ARROW-LESS -- just a slider, no stepper buttons.
 *   * a single ROUNDED (pill) thumb, translucent light grey, ~6px wide.
 *   * NO visible track at rest; on hover the thumb brightens and a faint groove
 *     fades in behind it.
 *   * HIDDEN entirely when everything fits (nothing to scroll).
 *
 * It is a GtkDrawingArea that reads/drives a GtkAdjustment (the scrolled window's
 * vertical adjustment), so it composes with a GtkScrolledWindow whose vertical
 * policy is GTK_POLICY_EXTERNAL (scrolls, draws no GTK bar). Draw it in an overlay
 * pinned to the right edge, full height.
 */
#ifndef AZ_KSCROLL_H
#define AZ_KSCROLL_H

#include <gtk/gtk.h>

typedef struct AzKScroll AzKScroll;

/* Create a scrollbar driving `vadj`. The returned GtkWidget (via az_kscroll_widget)
 * is a fixed-width drawing area to overlay on the right edge. */
AzKScroll *az_kscroll_new(GtkAdjustment *vadj);
GtkWidget *az_kscroll_widget(AzKScroll *s);
void       az_kscroll_free(AzKScroll *s);

#endif /* AZ_KSCROLL_H */
