/* Az'arch application menu (C port) -- bottom power/session button.
 * One-to-one port of widgets.py PowerButton, drawn with Cairo/Pango. */
#include "power.h"
#include "theme.h"

#include <math.h>

typedef struct {
    GdkPixbuf      *icon;       /* borrowed from the resolver */
    char           *label;
    AzPowerAction   action;
    AzPowerBeforeFn before;     /* run before the action (hide the menu) */
    gpointer        before_user;
    gboolean        hover;
    GtkWidget     **row;        /* the whole button row (borrowed), for sibling clear */
    int             row_n;
    AzPowerHoverFn  hover_cb;   /* fired when this button becomes hovered (moves focus) */
    gpointer        hover_user;
} PowerBtn;

static PowerBtn *btn_of(GtkWidget *w) {
    return g_object_get_data(G_OBJECT(w), "pbtn");
}

/* Horizontal OPAQUE bounds of a pixbuf: first (*x0) and last (*x1) column that
 * contains any pixel with alpha above a small threshold. Breeze icons carry
 * transparent padding that is NOT symmetric, so the icon's visible ink sits off-
 * centre inside its pixbuf box; geometrically centring the box therefore pushes the
 * ink a few px left of true centre (the "3-7px left-heavier" the user measured).
 * Centring on THESE bounds instead lands the visible ink dead-centre.
 *
 * Returns FALSE (leaving the out-params untouched) when there is nothing to trim: no
 * pixbuf, no alpha channel (every pixel opaque, e.g. the flat placeholder), or a
 * fully-transparent image -- so the caller falls back to the full box, which is the
 * correct behaviour in every one of those cases. */
static gboolean icon_ink_hbounds(GdkPixbuf *p, int *x0, int *x1) {
    if (!p || !gdk_pixbuf_get_has_alpha(p)) return FALSE;
    int w = gdk_pixbuf_get_width(p);
    int h = gdk_pixbuf_get_height(p);
    int nch = gdk_pixbuf_get_n_channels(p);          /* 4 (RGBA) when has_alpha */
    int stride = gdk_pixbuf_get_rowstride(p);
    const guchar *base = gdk_pixbuf_read_pixels(p);
    if (w <= 0 || h <= 0 || nch < 4 || !base) return FALSE;

    const int ALPHA_MIN = 24;                        /* ignore near-transparent AA fringe */
    int lo = w, hi = -1;
    for (int y = 0; y < h; y++) {
        const guchar *row = base + (gsize)y * stride;
        for (int x = 0; x < w; x++) {
            if (row[x * nch + 3] > ALPHA_MIN) {      /* channel 3 is alpha */
                if (x < lo) lo = x;
                if (x > hi) hi = x;
            }
        }
    }
    if (hi < lo) return FALSE;                        /* fully transparent */
    *x0 = lo; *x1 = hi;
    return TRUE;
}

/* True if any button in the row is currently hovered. */
static gboolean row_any_hover(PowerBtn *pb) {
    if (!pb->row) return pb->hover;
    for (int i = 0; i < pb->row_n; i++) {
        PowerBtn *o = btn_of(pb->row[i]);
        if (o && o->hover) return TRUE;
    }
    return FALSE;
}

static gboolean power_draw(GtkWidget *w, cairo_t *cr, gpointer data) {
    PowerBtn *pb = data;
    GtkAllocation a; gtk_widget_get_allocation(w, &a);
    gboolean focused = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(w), "focused"));

    /* Hover and keyboard-focus share ONE highlight: the blue selection fill + a 1px
     * blue outline, identical to the app-list rows. The previous hover-only fill
     * (AZ_HOVER_COLOR on the window bg) differed by ~14 luma and read as "no highlight
     * at all" -- the user only ever saw the highlight on TAB, which drew the outline.
     * Giving hover the same fill+outline makes mouse hover as obvious as TAB focus.
     *
     * Hover TAKES OVER from TAB: while the mouse is over any button, only that button is
     * lit and any other lit button goes dark. And the highlight STAYS PUT after the pointer
     * leaves -- hovering a button moves the keyboard focus onto it (via hover_cb -> the
     * menu), so on leave `hover` clears but `focused` is now this same button and it stays
     * lit. No snap-back to a previous TAB position; a later TAB/arrow moves from here. */
    gboolean lit = pb->hover || (focused && !row_any_hover(pb));
    GdkRGBA c;
    gdk_rgba_parse(&c, lit ? AZ_SELECT_FILL : AZ_BG_COLOR);
    cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
    cairo_paint(cr);

    if (lit) {
        gdk_rgba_parse(&c, AZ_SELECT_BORDER);
        cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
        cairo_set_line_width(cr, 1);
        cairo_rectangle(cr, 0.5, 0.5, a.width - 1, a.height - 1);
        cairo_stroke(cr);
    }

    /* Center each button's OWN [icon][gap][label] block in its (equal-width) cell, using
     * THIS button's real icon and label widths -- not a shared column width. Sharing one
     * label column across the row (the previous approach) left the short labels ("Lock",
     * "Sleep") ink-heavy on the left of their cells while "Shut Down" filled its own, so
     * the row read as visibly off-centre. Measuring each block and centring it makes every
     * button's visible content sit dead-centre in its cell, which is what looks balanced
     * across the four. Pixel-snap the block origin so text/icon stay crisp. */
    int iw = pb->icon ? gdk_pixbuf_get_width(pb->icon) : 0;
    int ih = pb->icon ? gdk_pixbuf_get_height(pb->icon) : 0;
    PangoLayout *lay = pango_cairo_create_layout(cr);
    PangoFontDescription *fd = pango_font_description_new();
    pango_font_description_set_family(fd, AZ_FONT_FAMILY);
    pango_font_description_set_size(fd, AZ_FONT_POWER * PANGO_SCALE);
    pango_layout_set_font_description(lay, fd);
    pango_layout_set_text(lay, pb->label, -1);
    int tw, th;
    pango_layout_get_pixel_size(lay, &tw, &th);

    /* Centre on the icon's OPTICAL INK, not its pixbuf box. The Breeze pixbuf has
     * asymmetric transparent padding, so ink_x0 (first opaque column) and ink_x1 (last)
     * bound the actually-visible glyph; ink_x0>0 means dead space on the left. We lay the
     * block out on those bounds so the icon's left ink edge and the label's right edge sit
     * an equal margin from the cell walls (per-cell left_margin == right_margin), and we
     * meter the icon->text gap from the ink's RIGHT edge (ink_x1) rather than the box edge,
     * so the visual space between glyph and text is exactly `gap` regardless of padding.
     * Falls back to the full box (ink_x0=0, ink_x1=iw-1) when there is no ink to trim
     * (no alpha channel or a fully-transparent pixbuf); the opaque placeholder has alpha
     * so it is scanned and simply yields full-box bounds -- same geometric result.
     * NOTE: the block's right edge is the text's LOGICAL width tw; this assumes the label
     * has ~0 trailing side-bearing (true for the four session labels in Noto Sans, checked
     * to <=1px). A relabel to a glyph with large right overhang would meter the right edge
     * a hair early and could reintroduce a small right-lean -- re-check the ink margins. */
    int ink_x0 = 0, ink_x1 = iw - 1;
    if (pb->icon) icon_ink_hbounds(pb->icon, &ink_x0, &ink_x1);
    int ink_w = pb->icon ? (ink_x1 - ink_x0 + 1) : 0;   /* visible icon width */

    int gap = pb->icon ? 8 : 0;           /* Tk icon padx=(0,8); no gap if no icon */
    double cy = a.height / 2.0;
    /* Visible block = [icon ink][gap][text]; span it and centre that span. */
    int visible = ink_w + gap + tw;
    /* draw_x is the pixbuf's paint origin; the ink then begins at draw_x + ink_x0. Solve
     * for equal margins: (draw_x + ink_x0) == a.width - (draw_x + ink_x0 + visible). */
    double draw_x = round((a.width - visible) / 2.0) - ink_x0;
    if (pb->icon) {
        gdk_cairo_set_source_pixbuf(cr, pb->icon, draw_x, round(cy - ih / 2.0));
        cairo_paint(cr);
    }
    gdk_rgba_parse(&c, AZ_TEXT_COLOR);
    cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
    /* Text starts `gap` past the icon ink's right edge (draw_x + ink_x1 + 1). */
    double text_x = pb->icon ? (draw_x + ink_x1 + 1 + gap) : draw_x;
    cairo_move_to(cr, round(text_x), round(cy - th / 2.0));
    pango_cairo_show_layout(cr, lay);

    pango_font_description_free(fd);
    g_object_unref(lay);
    return TRUE;
}

/* Only NORMAL pointer crossings are real hover transitions. When the menu takes
 * its seat grab (menu.c grab_all) the pointer may already sit over a button; the
 * grab then injects synthetic crossings (mode GDK_CROSSING_GRAB / _UNGRAB /
 * _GTK_GRAB / _GTK_UNGRAB) even though the pointer never physically moved. Acting
 * on those flipped `hover` off under a stationary cursor, so the highlight blinked
 * out and only came back on the next real move (or via TAB focus) -- the "no hover
 * unless I TAB" bug. Ignore every non-NORMAL crossing so hover tracks the pointer,
 * not the grab. */
static gboolean crossing_is_real(GdkEvent *e) {
    return ((GdkEventCrossing *)e)->mode == GDK_CROSSING_NORMAL;
}

/* Redraw the whole row: hover on one button changes what the TAB-focused button
 * shows (hover take-over), so every sibling must repaint, not just this one. */
static void redraw_row(PowerBtn *pb, GtkWidget *self) {
    if (!pb->row) { gtk_widget_queue_draw(self); return; }
    for (int i = 0; i < pb->row_n; i++)
        gtk_widget_queue_draw(pb->row[i]);
}

/* Set this button hovered/not. When it becomes hovered, clear every sibling's hover so
 * at most one button is ever hovered (moving between adjacent buttons under the grab may
 * not deliver a leave to the one we left, which would otherwise leave it stuck lit).
 *
 * On the rising edge (not-hovered -> hovered) we also fire hover_cb, which the menu uses
 * to MOVE the keyboard focus onto this button. That is what makes the highlight STAY here
 * after the pointer leaves: `hover` clears on leave but `focused` now points at this same
 * button, so power_draw keeps it lit -- no snap-back to the old TAB position. Rising-edge
 * only, so a stream of motion events over one button does not re-fire it. */
static void set_hover(PowerBtn *pb, GtkWidget *w, gboolean on) {
    gboolean rising = (on && !pb->hover);
    gboolean changed = (pb->hover != on);
    if (on && pb->row) {
        for (int i = 0; i < pb->row_n; i++) {
            PowerBtn *o = btn_of(pb->row[i]);
            if (o && o != pb && o->hover) { o->hover = FALSE; changed = TRUE; }
        }
    }
    if (pb->hover != on) pb->hover = on;
    if (rising && pb->hover_cb) pb->hover_cb(pb->hover_user, w);
    if (changed) redraw_row(pb, w);
}

static gboolean power_enter(GtkWidget *w, GdkEvent *e, gpointer data) {
    PowerBtn *pb = data;
    if (!crossing_is_real(e)) return FALSE;
    set_hover(pb, w, TRUE); return FALSE;
}
static gboolean power_leave(GtkWidget *w, GdkEvent *e, gpointer data) {
    PowerBtn *pb = data;
    if (!crossing_is_real(e)) return FALSE;
    set_hover(pb, w, FALSE); return FALSE;
}
/* Belt-and-braces hover: under the menu's seat grab, some setups do not deliver
 * enter/leave crossings to these child drawing-areas for a physically-moving pointer
 * (the grab keeps pointer focus on the toplevel), so hover never lit for a real mouse
 * even though it worked for injected motion. Motion IS delivered under the grab, so we
 * also derive hover from the pointer position: inside the allocation -> lit. This makes
 * hover track the real cursor regardless of whether crossings arrive. */
static gboolean power_motion(GtkWidget *w, GdkEventMotion *e, gpointer data) {
    PowerBtn *pb = data;
    GtkAllocation a; gtk_widget_get_allocation(w, &a);
    gboolean inside = (e->x >= 0 && e->y >= 0 && e->x < a.width && e->y < a.height);
    set_hover(pb, w, inside);
    return FALSE;
}
static gboolean power_click(GtkWidget *w, GdkEventButton *e, gpointer data) {
    (void)w;
    PowerBtn *pb = data;
    if (e->button == 1) {
        if (pb->before) pb->before(pb->before_user);
        if (pb->action) pb->action();
    }
    return TRUE;
}

static void power_free(gpointer data, GClosure *closure) {
    (void)closure;
    PowerBtn *pb = data;
    g_free(pb->label);
    g_free(pb);
}

void az_power_button_clear_hover(GtkWidget *btn) {
    PowerBtn *pb = g_object_get_data(G_OBJECT(btn), "pbtn");
    if (pb && pb->hover) {
        pb->hover = FALSE;
        redraw_row(pb, btn);
    }
}

/* Tell every button about the full row so it can (a) keep at most one button hovered
 * and (b) let hover take over the TAB highlight. Call once after the row is built. */
void az_power_row_set_siblings(GtkWidget **btns, int n) {
    for (int i = 0; i < n; i++) {
        PowerBtn *pb = btn_of(btns[i]);
        if (pb) { pb->row = btns; pb->row_n = n; }
    }
}

/* Register the hover->focus promotion callback on every button in the row. */
void az_power_row_set_hover_cb(GtkWidget **btns, int n, AzPowerHoverFn cb, gpointer user) {
    for (int i = 0; i < n; i++) {
        PowerBtn *pb = btn_of(btns[i]);
        if (pb) { pb->hover_cb = cb; pb->hover_user = user; }
    }
}

GtkWidget *az_power_button_new(AzIcons *icons, const char *icon_name,
                               const char *label, AzPowerAction action,
                               AzPowerBeforeFn before, gpointer before_user) {
    PowerBtn *pb = g_new0(PowerBtn, 1);
    pb->icon = az_icons_load(icons, icon_name);
    pb->label = g_strdup(label);
    pb->action = action;
    pb->before = before;
    pb->before_user = before_user;

    GtkWidget *ev = gtk_drawing_area_new();
    gtk_widget_set_size_request(ev, -1, 48);
    gtk_widget_add_events(ev, GDK_BUTTON_PRESS_MASK | GDK_ENTER_NOTIFY_MASK |
                          GDK_LEAVE_NOTIFY_MASK | GDK_POINTER_MOTION_MASK);
    /* Object data the menu reads: focus state + the action for Enter-on-focus, and
     * the PowerBtn itself so az_power_button_clear_hover can reset hover on hide. */
    g_object_set_data(G_OBJECT(ev), "focused", GINT_TO_POINTER(FALSE));
    g_object_set_data(G_OBJECT(ev), "action", (gpointer)action);
    g_object_set_data(G_OBJECT(ev), "pbtn", pb);
    /* Tie the PowerBtn lifetime to the widget: freed when the last signal closure is. */
    g_signal_connect_data(ev, "draw", G_CALLBACK(power_draw), pb, power_free, 0);
    g_signal_connect(ev, "enter-notify-event", G_CALLBACK(power_enter), pb);
    g_signal_connect(ev, "leave-notify-event", G_CALLBACK(power_leave), pb);
    g_signal_connect(ev, "motion-notify-event", G_CALLBACK(power_motion), pb);
    g_signal_connect(ev, "button-press-event", G_CALLBACK(power_click), pb);
    return ev;
}
