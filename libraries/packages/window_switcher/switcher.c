/* Az'arch window switcher -- the resident daemon (alt-tab overlay). See the package
 * README/design. Structure ported from application_menu/menu.c: build the overlay once at
 * login, warm it off-screen, and show by MOVING on-screen / hide by moving off (never a
 * re-map) so the first Alt+Tab is instant. Control by signal, state in a pidfile.
 *
 * Signal contract (driven by launcher.py):
 *   SIGUSR1 = advance forward + show   (A-Tab)
 *   SIGUSR2 = advance backward + show   (A-S-Tab)
 *   SIGTERM/SIGINT = quit
 *
 * While shown the daemon grabs the seat, so it sees the Alt release itself: releasing Alt
 * commits (raise + activate the selected window); Tab/Shift+Tab move the selection;
 * Escape cancels. A timer re-captures thumbnails so tiles stream live. */
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <gdk/gdkkeysyms.h>
#include <glib/gstdio.h>          /* g_unlink */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <signal.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>

#include "layout.h"
#include "windows.h"
#include "ordering.h"
#include "theme.h"

#define OFFSCREEN_MARGIN 4000
/* Two refresh cadences while shown (see the two timers below):
 *   THUMB_MS -- stream fresh thumbnail frames into the EXISTING tiles, in place. Cheap (just
 *               XComposite captures, no widget rebuild), so it runs fast enough that the live
 *               content reads as smooth motion instead of a 5fps slideshow.
 *   LIST_MS  -- re-enumerate the window list (which forks `xprop` per window -- EXPENSIVE), only
 *               to notice a window that opened or closed. That is a rare event, so it runs slowly
 *               and stays off the smooth-streaming hot path. */
#define THUMB_MS          50      /* ~20fps live-thumbnail streaming (in place, no rebuild) */
#define LIST_MS          500      /* window-set (open/close) re-scan cadence (forks xprop) */

typedef struct {
    GtkWidget *win;
    AzStrip   *strip;
    gboolean   shown;
    guint      thumb_id;          /* fast in-place thumbnail timer, 0 when hidden */
    guint      list_id;           /* slow window-list re-scan timer, 0 when hidden */
} AzSwitcher;

static AzSwitcher g_sw;

static void commit_switcher(AzSwitcher *s);   /* fwd: used by the anti-pin Alt-state check */

/* ---- live-window refresh ------------------------------------------------ */
/* Re-enumerate the managed windows (forks xprop) and hand them to the strip. az_strip_set_windows
 * rebuilds ONLY if the set changed; an unchanged set just streams new frames in place. */
static void reload_windows(AzSwitcher *s) {
    GPtrArray *wins = az_windows_list();
    az_strip_set_windows(s->strip, wins);
    az_windows_free(wins);
}

/* Fast tick: stream fresh thumbnail frames into the existing tiles (smooth, no rebuild). */
static gboolean on_thumb_tick(gpointer user) {
    AzSwitcher *s = user;
    if (!s->shown) { s->thumb_id = 0; return G_SOURCE_REMOVE; }
    az_strip_refresh_thumbnails(s->strip);
    return G_SOURCE_CONTINUE;
}

/* Slow tick: re-scan the window LIST so a window opened/closed while the overlay is up appears/
 * disappears. Kept slow because it forks xprop per window; the fast path never does. */
static gboolean on_list_tick(gpointer user) {
    AzSwitcher *s = user;
    if (!s->shown) { s->list_id = 0; return G_SOURCE_REMOVE; }
    reload_windows(s);
    return G_SOURCE_CONTINUE;
}

/* ---- show / hide (by move, like the menu) ------------------------------- */
static void move_window(AzSwitcher *s, int x, int y) {
    gtk_window_move(GTK_WINDOW(s->win), x, y);
}

static void center_on_primary(AzSwitcher *s, int *out_x, int *out_y) {
    GdkDisplay *dpy = gtk_widget_get_display(s->win);
    GdkMonitor *mon = gdk_display_get_primary_monitor(dpy);
    if (!mon) mon = gdk_display_get_monitor(dpy, 0);
    GdkRectangle geo = { 0, 0, gdk_screen_width(), gdk_screen_height() };
    if (mon) gdk_monitor_get_geometry(mon, &geo);
    GtkRequisition req;
    gtk_widget_get_preferred_size(s->win, NULL, &req);
    int w = req.width  > 0 ? req.width  : 400;
    int h = req.height > 0 ? req.height : 200;
    *out_x = geo.x + (geo.width  - w) / 2;
    *out_y = geo.y + (geo.height - h) / 2;
}

static void grab_seat(AzSwitcher *s) {
    GdkWindow *gw = gtk_widget_get_window(s->win);
    if (!gw) return;
    GdkDisplay *dpy = gtk_widget_get_display(s->win);
    GdkSeat *seat = gdk_display_get_default_seat(dpy);
    gdk_seat_grab(seat, gw, GDK_SEAT_CAPABILITY_ALL, TRUE,
                  NULL, NULL, NULL, NULL);
    gtk_window_present(GTK_WINDOW(s->win));
}

static void ungrab_seat(AzSwitcher *s) {
    GdkDisplay *dpy = gtk_widget_get_display(s->win);
    GdkSeat *seat = gdk_display_get_default_seat(dpy);
    gdk_seat_ungrab(seat);
}

/* Is a physical Alt (Mod1) currently held down? Queries the REAL X modifier state instead of
 * trusting that we saw the key-release event.
 *
 * WHY THIS EXISTS -- the "it pinned itself" bug: the switcher is shown by SIGNAL (the A-Tab
 * launcher), and only AFTER show_switcher() grabs the seat does the daemon start receiving key
 * events. Alt was already held when OpenBox fired the A-Tab binding, and OpenBox owned the
 * keyboard grab up to that instant. If the user releases Alt during the brief handoff (before OUR
 * grab is fully in place), that release is delivered to OpenBox / dropped, NOT to us -- so
 * on_key_release() never fires and the overlay stays up ("pinned") until a click or Escape. The
 * gesture contract is "hold Alt to keep it, let Alt go to dismiss", so the moment our grab is
 * live we ask the server directly whether Alt is still down; if it is NOT, the release already
 * happened and we commit immediately. This makes releasing Alt ALWAYS dismiss, with no pin. */
static gboolean alt_is_down(AzSwitcher *s) {
    GdkDisplay *gdpy = gtk_widget_get_display(s->win);
    Display *dpy = GDK_DISPLAY_XDISPLAY(gdpy);
    Window root = DefaultRootWindow(dpy);
    Window r, c; int rx, ry, wx, wy; unsigned int mask = 0;
    if (!XQueryPointer(dpy, root, &r, &c, &rx, &ry, &wx, &wy, &mask))
        return FALSE;               /* query failed -> treat as released (safer: no pin) */
    return (mask & Mod1Mask) != 0;  /* Mod1 == Alt on the standard X modifier map */
}

/* Idle check run once, right after the overlay is shown + grabbed: if Alt is no longer held the
 * release slipped past our grab, so commit now (the anti-pin guard -- see alt_is_down). */
static gboolean on_check_alt_still_held(gpointer user) {
    AzSwitcher *s = user;
    if (s->shown && !alt_is_down(s))
        commit_switcher(s);
    return G_SOURCE_REMOVE;
}

/* Raise + activate a window with a proper _NET_ACTIVE_WINDOW client message so the WM
 * (OpenBox) focuses and unminimizes it -- the same path a taskbar click uses. */
static void activate_window(AzSwitcher *s, unsigned long xid) {
    if (xid == 0) return;
    GdkDisplay *gdpy = gtk_widget_get_display(s->win);
    Display *dpy = GDK_DISPLAY_XDISPLAY(gdpy);
    Window root = DefaultRootWindow(dpy);
    XEvent ev; memset(&ev, 0, sizeof(ev));
    ev.xclient.type = ClientMessage;
    ev.xclient.window = (Window)xid;
    ev.xclient.message_type = XInternAtom(dpy, "_NET_ACTIVE_WINDOW", False);
    ev.xclient.format = 32;
    ev.xclient.data.l[0] = 2;            /* source: pager/direct user action */
    ev.xclient.data.l[1] = CurrentTime;
    XSendEvent(dpy, root, False,
               SubstructureRedirectMask | SubstructureNotifyMask, &ev);
    XRaiseWindow(dpy, (Window)xid);
    XFlush(dpy);
}

static void hide_switcher(AzSwitcher *s) {
    if (!s->shown) return;
    s->shown = FALSE;
    if (s->thumb_id) { g_source_remove(s->thumb_id); s->thumb_id = 0; }
    if (s->list_id)  { g_source_remove(s->list_id);  s->list_id  = 0; }
    ungrab_seat(s);
    move_window(s, gdk_screen_width() + OFFSCREEN_MARGIN,
                   gdk_screen_height() + OFFSCREEN_MARGIN);
    gdk_display_flush(gtk_widget_get_display(s->win));
}

/* Commit: activate the selected window, then hide. */
static void commit_switcher(AzSwitcher *s) {
    unsigned long xid = az_strip_selected_xid(s->strip);
    hide_switcher(s);
    activate_window(s, xid);
}

/* Show (or, if already shown, just advance). dir: +1 forward, -1 backward.
 * On a fresh open, Windows pre-selects the PREVIOUS window: forward lands on index 1,
 * backward on the last, so one tap of Alt+Tab flips to the last-used window. */
static void show_switcher(AzSwitcher *s, int dir) {
    if (s->shown) {
        az_strip_select(s->strip, az_strip_selected(s->strip) + dir);
        return;
    }
    reload_windows(s);
    int n = az_strip_count(s->strip);
    if (n <= 0) return;                  /* nothing to switch to */
    int start = (dir >= 0) ? (n > 1 ? 1 : 0) : (n - 1);
    az_strip_select(s->strip, start);

    int x, y;
    center_on_primary(s, &x, &y);
    move_window(s, x, y);
    gdk_window_raise(gtk_widget_get_window(s->win));
    s->shown = TRUE;
    grab_seat(s);
    gdk_display_sync(gtk_widget_get_display(s->win));
    /* Two timers: fast in-place thumbnail streaming + a slow window-list re-scan (see the tick
     * functions). Fast one gives smooth live content; slow one catches opened/closed windows. */
    if (!s->thumb_id) s->thumb_id = g_timeout_add(THUMB_MS, on_thumb_tick, s);
    if (!s->list_id)  s->list_id  = g_timeout_add(LIST_MS,  on_list_tick,  s);
    /* Anti-pin guard: now that our grab is live, verify Alt is still physically held. If the
     * release slipped past during the OpenBox->daemon grab handoff, dismiss immediately so the
     * overlay never stays pinned (see alt_is_down / on_check_alt_still_held). Deferred to an idle
     * so the grab + first paint settle before we query. */
    g_idle_add(on_check_alt_still_held, s);
}

/* Map a number-key event to a 1-based tile SLOT, or 0 if the key is not a digit. 1..9 are
 * slots 1..9 and 0 is slot 10 -- so the ten leftmost tiles are directly reachable. Both the
 * number ROW (GDK_KEY_1..0) and the keypad (GDK_KEY_KP_1..0) are accepted. The strip is ordered
 * librewolf, kitty, hypervisor, thunar, then the rest (ordering.c), so slot 1 == librewolf and
 * slot 2 == kitty exactly as the user expects ("librewolf=1, kitty=2 ... press 1 -> librewolf"):
 * the slot is the on-screen 1-based POSITION, which for the ranked apps equals their rank. */
static int digit_slot(guint keyval) {
    switch (keyval) {
        case GDK_KEY_1: case GDK_KEY_KP_1: return 1;
        case GDK_KEY_2: case GDK_KEY_KP_2: return 2;
        case GDK_KEY_3: case GDK_KEY_KP_3: return 3;
        case GDK_KEY_4: case GDK_KEY_KP_4: return 4;
        case GDK_KEY_5: case GDK_KEY_KP_5: return 5;
        case GDK_KEY_6: case GDK_KEY_KP_6: return 6;
        case GDK_KEY_7: case GDK_KEY_KP_7: return 7;
        case GDK_KEY_8: case GDK_KEY_KP_8: return 8;
        case GDK_KEY_9: case GDK_KEY_KP_9: return 9;
        case GDK_KEY_0: case GDK_KEY_KP_0: return 10;  /* 0 is the tenth slot */
        default:                           return 0;
    }
}

/* ---- key handling while shown ------------------------------------------- */
static gboolean on_key_press(GtkWidget *w, GdkEventKey *ev, gpointer user) {
    (void)w;
    AzSwitcher *s = user;
    if (!s->shown) return FALSE;

    /* Number keys 1..9,0 jump straight to that tile (by 1-based on-screen position) and
     * activate it -- press 1 for librewolf, 2 for kitty, etc. Ignored when the slot is past the
     * last tile (fewer windows than the digit), so a stray high number is a harmless no-op
     * rather than a wrong/!last-tile activation. */
    int slot = digit_slot(ev->keyval);
    if (slot > 0) {
        if (slot <= az_strip_count(s->strip)) {
            az_strip_select(s->strip, slot - 1);   /* 1-based slot -> 0-based index */
            commit_switcher(s);
        }
        return TRUE;                                /* swallow digits either way while shown */
    }

    switch (ev->keyval) {
        case GDK_KEY_Tab:
        case GDK_KEY_KP_Tab:
            if (ev->state & GDK_SHIFT_MASK)
                az_strip_select(s->strip, az_strip_selected(s->strip) - 1);
            else
                az_strip_select(s->strip, az_strip_selected(s->strip) + 1);
            return TRUE;
        case GDK_KEY_ISO_Left_Tab:       /* Shift+Tab on X */
            az_strip_select(s->strip, az_strip_selected(s->strip) - 1);
            return TRUE;
        case GDK_KEY_Right:
            az_strip_select(s->strip, az_strip_selected(s->strip) + 1);
            return TRUE;
        case GDK_KEY_Left:
            az_strip_select(s->strip, az_strip_selected(s->strip) - 1);
            return TRUE;
        case GDK_KEY_Escape:
            hide_switcher(s);            /* cancel: no focus change */
            return TRUE;
        case GDK_KEY_Return:
        case GDK_KEY_KP_Enter:
            commit_switcher(s);
            return TRUE;
        default:
            return FALSE;
    }
}

/* Releasing Alt commits the selection (the Windows alt-tab gesture). */
static gboolean on_key_release(GtkWidget *w, GdkEventKey *ev, gpointer user) {
    (void)w;
    AzSwitcher *s = user;
    if (!s->shown) return FALSE;
    if (ev->keyval == GDK_KEY_Alt_L || ev->keyval == GDK_KEY_Alt_R ||
        ev->keyval == GDK_KEY_Meta_L || ev->keyval == GDK_KEY_Meta_R) {
        commit_switcher(s);
        return TRUE;
    }
    return FALSE;
}

/* ---- window assembly + warmup ------------------------------------------- */
static void build_window(AzSwitcher *s) {
    s->win = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_decorated(GTK_WINDOW(s->win), FALSE);
    gtk_window_set_skip_taskbar_hint(GTK_WINDOW(s->win), TRUE);
    gtk_window_set_skip_pager_hint(GTK_WINDOW(s->win), TRUE);
    gtk_window_set_type_hint(GTK_WINDOW(s->win), GDK_WINDOW_TYPE_HINT_UTILITY);
    gtk_window_set_position(GTK_WINDOW(s->win), GTK_WIN_POS_NONE);
    gtk_window_set_resizable(GTK_WINDOW(s->win), FALSE);
    gtk_widget_set_app_paintable(s->win, TRUE);

    /* RGBA visual so the rounded panel's corners are transparent, not black. */
    GdkScreen *screen = gtk_widget_get_screen(s->win);
    GdkVisual *rgba = gdk_screen_get_rgba_visual(screen);
    if (rgba) gtk_widget_set_visual(s->win, rgba);

    s->strip = az_strip_new(s->win);

    g_signal_connect(s->win, "key-press-event", G_CALLBACK(on_key_press), s);
    g_signal_connect(s->win, "key-release-event", G_CALLBACK(on_key_release), s);

    gtk_widget_realize(s->win);
    GdkWindow *gw = gtk_widget_get_window(s->win);
    gdk_window_set_override_redirect(gw, TRUE);
}

static void warmup(AzSwitcher *s) {
    move_window(s, gdk_screen_width() + OFFSCREEN_MARGIN,
                   gdk_screen_height() + OFFSCREEN_MARGIN);
    gtk_widget_show_all(s->win);          /* the one real map, off-screen */
    while (gtk_events_pending())
        gtk_main_iteration_do(FALSE);
    gdk_display_flush(gtk_widget_get_display(s->win));
    s->shown = FALSE;
}

/* ---- daemon: pidfile + signal loop -------------------------------------- */
static char *pid_path(void) {
    const char *rt = g_getenv("XDG_RUNTIME_DIR");
    if (!rt || !rt[0]) rt = "/tmp";
    return g_build_filename(rt, "azarch-window-switcher.pid", NULL);
}

static int sig_pipe[2];

static void sig_handler(int signum) {
    char b = (char)signum;
    ssize_t r = write(sig_pipe[1], &b, 1);
    (void)r;
}

static gboolean on_sig_pipe(GIOChannel *src, GIOCondition cond, gpointer user) {
    (void)cond;
    AzSwitcher *s = user;
    char buf[64];
    gsize n = 0;
    g_io_channel_read_chars(src, buf, sizeof(buf), &n, NULL);
    char last = 0;
    for (gsize i = 0; i < n; i++) {
        if (buf[i] == SIGTERM || buf[i] == SIGINT) { gtk_main_quit(); return TRUE; }
        last = buf[i];
    }
    if (last == SIGUSR1) show_switcher(s, +1);
    else if (last == SIGUSR2) show_switcher(s, -1);
    return TRUE;
}

static gboolean claim_pidfile(const char *path) {
    for (int attempt = 0; attempt < 3; attempt++) {
        int fd = open(path, O_CREAT | O_EXCL | O_WRONLY, 0644);
        if (fd >= 0) {
            char pidbuf[32];
            int len = g_snprintf(pidbuf, sizeof(pidbuf), "%d", (int)getpid());
            ssize_t w = write(fd, pidbuf, len);
            (void)w;
            close(fd);
            return TRUE;
        }
        if (errno != EEXIST) return TRUE;
        char *txt = NULL;
        int other = -1;
        if (g_file_get_contents(path, &txt, NULL, NULL) && txt)
            other = atoi(g_strstrip(txt));
        g_free(txt);
        if (other > 0 && kill(other, 0) == 0) return FALSE;
        g_unlink(path);
    }
    return TRUE;
}

static void remove_pidfile(const char *path) {
    char *txt = NULL;
    if (g_file_get_contents(path, &txt, NULL, NULL) && txt) {
        char *s = g_strstrip(txt);
        char *mine = g_strdup_printf("%d", (int)getpid());
        if (strcmp(s, mine) == 0) g_unlink(path);
        g_free(mine);
    }
    g_free(txt);
}

int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    az_theme_init();

    char *pidfile = pid_path();
    if (!claim_pidfile(pidfile)) {
        g_free(pidfile);
        return 0;                        /* another daemon already runs */
    }

    AzSwitcher *s = &g_sw;
    build_window(s);
    warmup(s);

    if (pipe(sig_pipe) == 0) {
        GIOChannel *ch = g_io_channel_unix_new(sig_pipe[0]);
        g_io_channel_set_encoding(ch, NULL, NULL);
        g_io_channel_set_buffered(ch, FALSE);
        g_io_add_watch(ch, G_IO_IN, on_sig_pipe, s);
        g_io_channel_unref(ch);
        struct sigaction sa; memset(&sa, 0, sizeof(sa));
        sa.sa_handler = sig_handler;
        sigaction(SIGUSR1, &sa, NULL);
        sigaction(SIGUSR2, &sa, NULL);
        sigaction(SIGTERM, &sa, NULL);
        sigaction(SIGINT, &sa, NULL);
    }

    gtk_main();

    az_strip_free(s->strip);
    remove_pidfile(pidfile);
    g_free(pidfile);
    return 0;
}
