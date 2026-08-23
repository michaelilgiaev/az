/* Az'arch window switcher -- live thumbnail capture via XComposite. See thumbnail.h.
 *
 * picom (started from the OpenBox autostart) redirects every window to an off-screen
 * pixmap; here we name that pixmap, wrap it in a cairo Xlib surface, pull it into a
 * GdkPixbuf, and scale it into the tile. Every X round-trip is wrapped in a trapped
 * error handler because a window can unmap/close between enumeration and capture -- that
 * must yield NULL (icon fallback), never an Xlib abort. */
#include "thumbnail.h"

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/Xcomposite.h>
#include <cairo.h>
#include <cairo-xlib.h>
#include <gdk/gdk.h>

/* ---- trapped X errors --------------------------------------------------- */
static volatile int x_err = 0;
static int trap_handler(Display *d, XErrorEvent *e) { (void)d; (void)e; x_err = 1; return 0; }

/* Shared display + a one-time XComposite presence check. NULL display -> no capture. */
static Display *display(gboolean *has_composite) {
    static Display *dpy = NULL;
    static gboolean checked = FALSE;
    static gboolean composite = FALSE;
    if (!checked) {
        checked = TRUE;
        dpy = XOpenDisplay(NULL);
        if (dpy) {
            int ev = 0, er = 0;
            composite = XCompositeQueryExtension(dpy, &ev, &er) ? TRUE : FALSE;
        }
    }
    if (has_composite) *has_composite = composite;
    return dpy;
}

/* Scale `src` to fit inside (max_w,max_h), preserving aspect. Never upscales past the
 * source (a tiny window stays small, centered by the caller). Returns a new ref. */
static GdkPixbuf *scale_fit(GdkPixbuf *src, int max_w, int max_h) {
    int w = gdk_pixbuf_get_width(src), h = gdk_pixbuf_get_height(src);
    if (w <= 0 || h <= 0) return NULL;
    double s = (double)max_w / w;
    double sh = (double)max_h / h;
    if (sh < s) s = sh;
    if (s > 1.0) s = 1.0;                 /* don't blow up small windows */
    int nw = (int)(w * s + 0.5), nh = (int)(h * s + 0.5);
    if (nw < 1) nw = 1;
    if (nh < 1) nh = 1;
    return gdk_pixbuf_scale_simple(src, nw, nh, GDK_INTERP_BILINEAR);
}

GdkPixbuf *az_thumbnail_capture(unsigned long xid, int max_w, int max_h) {
    gboolean have_composite = FALSE;
    Display *dpy = display(&have_composite);
    if (!dpy || !have_composite || xid == 0 || max_w <= 0 || max_h <= 0)
        return NULL;

    Window win = (Window)xid;
    GdkPixbuf *result = NULL;
    Pixmap pixmap = 0;
    cairo_surface_t *surf = NULL;
    GdkPixbuf *shot = NULL;

    XErrorHandler prev = XSetErrorHandler(trap_handler);
    x_err = 0;

    XWindowAttributes attr;
    if (!XGetWindowAttributes(dpy, win, &attr) || x_err) goto out;
    if (attr.map_state != IsViewable && attr.map_state != IsUnmapped) goto out;
    if (attr.width <= 0 || attr.height <= 0) goto out;

    /* Name the window's backing pixmap (needs a redirecting compositor). */
    pixmap = XCompositeNameWindowPixmap(dpy, win);
    XSync(dpy, False);
    if (x_err || pixmap == 0) goto out;

    surf = cairo_xlib_surface_create(dpy, pixmap, attr.visual,
                                     attr.width, attr.height);
    if (!surf || cairo_surface_status(surf) != CAIRO_STATUS_SUCCESS) goto out;

    shot = gdk_pixbuf_get_from_surface(surf, 0, 0, attr.width, attr.height);
    if (!shot) goto out;

    result = scale_fit(shot, max_w, max_h);

out:
    if (shot)   g_object_unref(shot);
    if (surf)   cairo_surface_destroy(surf);
    if (pixmap) { XFreePixmap(dpy, pixmap); XSync(dpy, False); }
    XSetErrorHandler(prev);
    return result;
}
