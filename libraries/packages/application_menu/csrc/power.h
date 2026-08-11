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

/* Build one power button. `before(before_user)` runs first on click (to hide the
 * menu), then `action()`. `icons` resolves the Breeze icon at POWER_ICON_SIZE. */
GtkWidget *az_power_button_new(AzIcons *icons, const char *icon_name,
                               const char *label, AzPowerAction action,
                               AzPowerBeforeFn before, gpointer before_user);

#endif /* AZ_POWER_H */
