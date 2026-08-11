/* Az'arch application menu (C port) -- bottom power/session button.
 *
 * Port of widgets.py PowerButton: a Breeze icon beside a label, drawn on a
 * GtkDrawingArea, that highlights on hover and can render a blue keyboard-focus
 * OUTLINE (the menu's TAB navigation drives it). The four buttons are gridded into
 * four EQUAL columns by the caller; each button centres its icon+label group within
 * its own cell.
 *
 * The returned widget carries two pieces of object data the menu reads directly:
 *   "focused" (gboolean via GINT) -- set by the menu to drive the focus outline;
 *   "action"  (AzPowerAction)     -- the session action, fired by Enter on focus.
 */
#ifndef AZ_POWER_H
#define AZ_POWER_H

#include <gtk/gtk.h>
#include "icons.h"

typedef void (*AzPowerAction)(void);          /* az_suspend / az_lock_session / ... */
typedef void (*AzPowerBeforeFn)(gpointer);    /* run before the action (hide the menu) */
/* Fired the moment the pointer settles on a button: `btn` is that button, `user` is the
 * value handed to az_power_row_set_hover_cb. The menu uses it to MOVE the keyboard focus
 * onto the hovered button, so when the pointer later leaves, the highlight stays put
 * instead of snapping back to wherever TAB focus was. */
typedef void (*AzPowerHoverFn)(gpointer user, GtkWidget *btn);

/* Build one power button. `before(before_user)` runs first on click (to hide the
 * menu), then `action()`. `icons` resolves the Breeze icon at POWER_ICON_SIZE. */
GtkWidget *az_power_button_new(AzIcons *icons, const char *icon_name,
                               const char *label, AzPowerAction action,
                               AzPowerBeforeFn before, gpointer before_user);

/* Force-clear the hover state (repaints at rest). The menu calls this on hide so a
 * button the pointer was over when the menu closed does not re-open still lit -- the
 * off-screen hide never delivers the leave-notify that would normally clear it. */
void az_power_button_clear_hover(GtkWidget *btn);

/* Give every button a reference to the whole row (borrowed array of `n` widgets) so
 * hover can (a) stay exclusive to one button and (b) take over the TAB-focus highlight
 * while the mouse is over the row. On leave the highlight STAYS on the last-hovered
 * button (the menu, via the hover callback below, moves focus there). Call once after all
 * buttons are created and gridded. */
void az_power_row_set_siblings(GtkWidget **btns, int n);

/* Register the callback fired when the pointer settles on a button (see AzPowerHoverFn).
 * Call once after the row is built. Passing cb=NULL disables promotion (hover then simply
 * reverts to the TAB-focused button on leave, the old behaviour). */
void az_power_row_set_hover_cb(GtkWidget **btns, int n, AzPowerHoverFn cb, gpointer user);

#endif /* AZ_POWER_H */
