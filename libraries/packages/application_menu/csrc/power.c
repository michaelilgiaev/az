/* Az'arch application menu (C port) -- bottom power/session button.
 * One-to-one port of widgets.py PowerButton, drawn with Cairo/Pango. */
#include "power.h"
#include "theme.h"

typedef struct {
    GdkPixbuf      *icon;       /* borrowed from the resolver */
    char           *label;
    AzPowerAction   action;
    AzPowerBeforeFn before;     /* run before the action (hide the menu) */
    gpointer        before_user;
    gboolean        hover;
} PowerBtn;

static gboolean power_draw(GtkWidget *w, cairo_t *cr, gpointer data) {
    PowerBtn *pb = data;
    GtkAllocation a; gtk_widget_get_allocation(w, &a);
    gboolean focused = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(w), "focused"));

    GdkRGBA c;
    if (pb->hover) gdk_rgba_parse(&c, AZ_HOVER_COLOR);
    else if (focused) gdk_rgba_parse(&c, AZ_SELECT_FILL);
    else gdk_rgba_parse(&c, AZ_BG_COLOR);
    cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
    cairo_paint(cr);

    if (focused) {
        gdk_rgba_parse(&c, AZ_SELECT_BORDER);
        cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
        cairo_set_line_width(cr, 1);
        cairo_rectangle(cr, 0.5, 0.5, a.width - 1, a.height - 1);
        cairo_stroke(cr);
    }

    /* Center icon + label horizontally as a group within the (equal) cell -- Tk's
     * PowerButton packs inner with the default CENTER anchor, giving exactly this. */
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

    int gap = 8;                          /* Tk icon padx=(0,8) */
    int total = iw + gap + tw;
    int x0 = (a.width - total) / 2;
    int cy = a.height / 2;
    if (pb->icon) {
        gdk_cairo_set_source_pixbuf(cr, pb->icon, x0, cy - ih / 2.0);
        cairo_paint(cr);
    }
    gdk_rgba_parse(&c, AZ_TEXT_COLOR);
    cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
    cairo_move_to(cr, x0 + iw + gap, cy - th / 2.0);
    pango_cairo_show_layout(cr, lay);

    pango_font_description_free(fd);
    g_object_unref(lay);
    return TRUE;
}

static gboolean power_enter(GtkWidget *w, GdkEvent *e, gpointer data) {
    (void)e; PowerBtn *pb = data; pb->hover = TRUE; gtk_widget_queue_draw(w); return FALSE;
}
static gboolean power_leave(GtkWidget *w, GdkEvent *e, gpointer data) {
    (void)e; PowerBtn *pb = data; pb->hover = FALSE; gtk_widget_queue_draw(w); return FALSE;
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
                          GDK_LEAVE_NOTIFY_MASK);
    /* Object data the menu reads: focus state + the action for Enter-on-focus. */
    g_object_set_data(G_OBJECT(ev), "focused", GINT_TO_POINTER(FALSE));
    g_object_set_data(G_OBJECT(ev), "action", (gpointer)action);
    /* Tie the PowerBtn lifetime to the widget: freed when the last signal closure is. */
    g_signal_connect_data(ev, "draw", G_CALLBACK(power_draw), pb, power_free, 0);
    g_signal_connect(ev, "enter-notify-event", G_CALLBACK(power_enter), pb);
    g_signal_connect(ev, "leave-notify-event", G_CALLBACK(power_leave), pb);
    g_signal_connect(ev, "button-press-event", G_CALLBACK(power_click), pb);
    return ev;
}
