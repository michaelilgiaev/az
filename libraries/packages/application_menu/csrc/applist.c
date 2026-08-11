/* Az'arch application menu (C port) -- the scrollable application list.
 * One-to-one port of applist.py CanvasAppList, drawn with Cairo/Pango. */
#include "applist.h"
#include "theme.h"
#include "kscroll.h"

#include <string.h>
#include <math.h>
#include <glib.h>

/* Search aliases: pin a .desktop id to the top while the query is a non-empty
 * prefix of the target word (applist.py SEARCH_PIN_ALIASES). */
static const char *PIN_WORDS[]  = { "calculator", NULL };
static const char *PIN_IDS[]    = { "qalculate-gtk.desktop", NULL };

typedef struct {
    AzAppEntry *entry;    /* borrowed */
    GdkPixbuf  *icon;     /* borrowed from the resolver */
    int         y;        /* current top y when shown */
    gboolean    shown;
} Row;

struct AzAppList {
    AzIcons      *icons;
    AzActivateFn  on_activate;
    gpointer      user;

    GtkWidget    *overlay;    /* GtkOverlay: scrolled window + custom scrollbar */
    GtkWidget    *scrolled;   /* GtkScrolledWindow */
    GtkWidget    *area;       /* GtkDrawingArea */
    GtkAdjustment *vadj;
    AzKScroll    *kscroll;    /* Kickoff pill scrollbar (overlaid, right edge) */

    GArray       *rows;       /* Row, canonical order */
    GPtrArray    *visible;    /* Row* currently shown, draw order */
    GString      *signature;  /* fingerprint of built rows */
    int           selected;   /* index into visible */
    int           hover;      /* index into visible */
    gboolean      selection_enabled;
    int           width;
    int           content_h;

    PangoFontDescription *font_name;
    PangoFontDescription *font_sub;
};

/* ---- signature (rebuild-skip fingerprint) ------------------------------- */
static void build_signature(GPtrArray *entries, GString *out) {
    g_string_truncate(out, 0);
    for (guint i = 0; i < entries->len; i++) {
        AzAppEntry *e = g_ptr_array_index(entries, i);
        g_string_append(out, e->desktop_id);   g_string_append_c(out, 31);
        g_string_append(out, e->name);          g_string_append_c(out, 31);
        g_string_append(out, e->type_label);    g_string_append_c(out, 31);
        g_string_append(out, e->icon);          g_string_append_c(out, 31);
        for (int k = 0; e->exec_argv && e->exec_argv[k]; k++) {
            g_string_append(out, e->exec_argv[k]);
            g_string_append_c(out, 30);
        }
        g_string_append_c(out, 29);
    }
}

/* ---- colour helper ------------------------------------------------------ */
static void set_src(cairo_t *cr, const char *hex) {
    GdkRGBA c;
    gdk_rgba_parse(&c, hex);
    cairo_set_source_rgba(cr, c.red, c.green, c.blue, c.alpha);
}

/* ---- drawing ------------------------------------------------------------ */
static gboolean on_draw(GtkWidget *w, cairo_t *cr, gpointer data) {
    (void)w;
    AzAppList *l = data;

    /* Background. */
    set_src(cr, AZ_BG_COLOR);
    cairo_paint(cr);

    PangoLayout *lay = pango_cairo_create_layout(cr);

    for (guint i = 0; i < l->visible->len; i++) {
        Row *r = g_ptr_array_index(l->visible, i);
        int y = r->y;
        gboolean selected = ((int)i == l->selected) && l->selection_enabled;
        gboolean hovered  = ((int)i == l->hover);

        if (selected || hovered) {
            /* Tk draws a SQUARE 1px canvas rectangle (create_rectangle), NOT a rounded
             * outline, inset PAD_X on each side and 2px top/bottom -- copy that exactly.
             * The .5 offset keeps the 1px stroke crisp on the pixel grid. */
            double rx = AZ_ROW_PAD_X + 0.5;
            double ry = y + 2 + 0.5;
            double rw = l->width - 2 * AZ_ROW_PAD_X - 1;
            double rh = AZ_ROW_H - 4 - 1;
            cairo_rectangle(cr, rx, ry, rw, rh);
            set_src(cr, AZ_SELECT_FILL);
            cairo_fill_preserve(cr);
            set_src(cr, AZ_SELECT_BORDER);
            cairo_set_line_width(cr, 1);
            cairo_stroke(cr);
        }

        /* Icon, vertically centred, left edge at ICON_X (anchor="w"). */
        if (r->icon) {
            int iw = gdk_pixbuf_get_width(r->icon);
            int ih = gdk_pixbuf_get_height(r->icon);
            double iy = y + AZ_ROW_H / 2.0 - ih / 2.0;
            gdk_cairo_set_source_pixbuf(cr, r->icon, AZ_ICON_X, iy);
            cairo_paint(cr);
            (void)iw;
        }

        const char *name_col = (selected || hovered) ? AZ_SELECT_TEXT : AZ_TEXT_COLOR;
        const char *sub_col  = (selected || hovered) ? AZ_SELECT_TEXT : AZ_SUBTEXT_COLOR;

        /* Name (baseline-ish anchored at NAME_DY; Tk text anchor 'w' is vertical
         * center of the line, so center the layout on that y). */
        pango_layout_set_font_description(lay, l->font_name);
        pango_layout_set_text(lay, r->entry->name, -1);
        int tw, th;
        pango_layout_get_pixel_size(lay, &tw, &th);
        set_src(cr, name_col);
        cairo_move_to(cr, AZ_TEXT_X, y + AZ_NAME_DY - th / 2.0);
        pango_cairo_show_layout(cr, lay);

        pango_layout_set_font_description(lay, l->font_sub);
        pango_layout_set_text(lay, r->entry->type_label, -1);
        pango_layout_get_pixel_size(lay, &tw, &th);
        set_src(cr, sub_col);
        cairo_move_to(cr, AZ_TEXT_X, y + AZ_SUB_DY - th / 2.0);
        pango_cairo_show_layout(cr, lay);
    }

    g_object_unref(lay);
    return FALSE;
}

/* ---- filtering ---------------------------------------------------------- */
static const char *pinned_id_for_query(const char *query) {
    char *q = g_utf8_casefold(g_strstrip(g_strdup(query)), -1);
    const char *result = NULL;
    size_t best = 0;
    if (q[0]) {
        for (int i = 0; PIN_WORDS[i]; i++) {
            char *wf = g_utf8_casefold(PIN_WORDS[i], -1);
            if (g_str_has_prefix(wf, q) && strlen(PIN_WORDS[i]) > best) {
                best = strlen(PIN_WORDS[i]);
                result = PIN_IDS[i];
            }
            g_free(wf);
        }
    }
    g_free(q);
    return result;
}

static gboolean row_matches(Row *r, const char *qcf) {
    if (!qcf || !qcf[0])
        return TRUE;
    char *n = g_utf8_casefold(r->entry->name, -1);
    char *t = g_utf8_casefold(r->entry->type_label, -1);
    gboolean m = (strstr(n, qcf) != NULL) || (strstr(t, qcf) != NULL);
    g_free(n); g_free(t);
    return m;
}

static void update_scroll_region(AzAppList *l) {
    gtk_widget_set_size_request(l->area, -1, MAX(l->content_h, 1));
    gtk_widget_queue_draw(l->area);
}

void az_applist_apply_filter(AzAppList *l, const char *query) {
    char *qcf = g_utf8_casefold(g_strstrip(g_strdup(query ? query : "")), -1);

    g_ptr_array_set_size(l->visible, 0);
    for (guint i = 0; i < l->rows->len; i++) {
        Row *r = &g_array_index(l->rows, Row, i);
        if (row_matches(r, qcf))
            g_ptr_array_add(l->visible, r);
    }
    g_free(qcf);

    /* Search alias: float the pinned app to the top if it is a match. */
    const char *pinned = pinned_id_for_query(query ? query : "");
    if (pinned) {
        for (guint i = 0; i < l->visible->len; i++) {
            Row *r = g_ptr_array_index(l->visible, i);
            if (strcmp(r->entry->desktop_id, pinned) == 0) {
                if (i != 0) {
                    g_ptr_array_remove_index(l->visible, i);
                    g_ptr_array_insert(l->visible, 0, r);
                }
                break;
            }
        }
    }

    int y = 0;
    for (guint i = 0; i < l->visible->len; i++) {
        Row *r = g_ptr_array_index(l->visible, i);
        r->y = y;
        r->shown = TRUE;
        y += AZ_ROW_H;
    }
    l->content_h = y;

    l->selected = (l->visible->len > 0) ? 0 : -1;
    l->hover = -1;
    update_scroll_region(l);
    gtk_adjustment_set_value(l->vadj, 0.0);
}

/* ---- selection / nav ---------------------------------------------------- */
static void scroll_to_selected(AzAppList *l) {
    if (!(l->selected >= 0 && (guint)l->selected < l->visible->len))
        return;
    Row *r = g_ptr_array_index(l->visible, l->selected);
    double page = gtk_adjustment_get_page_size(l->vadj);
    double val = gtk_adjustment_get_value(l->vadj);
    double top = r->y;
    double bot = r->y + AZ_ROW_H;
    if (top < val)
        gtk_adjustment_set_value(l->vadj, top);
    else if (bot > val + page)
        gtk_adjustment_set_value(l->vadj, bot - page);
}

void az_applist_move_selection(AzAppList *l, int delta) {
    if (l->visible->len == 0)
        return;
    l->selected = CLAMP(l->selected + delta, 0, (int)l->visible->len - 1);
    scroll_to_selected(l);
    gtk_widget_queue_draw(l->area);
}

void az_applist_activate_selected(AzAppList *l) {
    if (l->selected >= 0 && (guint)l->selected < l->visible->len) {
        Row *r = g_ptr_array_index(l->visible, l->selected);
        l->on_activate(r->entry, l->user);
    }
}

void az_applist_set_selection_enabled(AzAppList *l, gboolean enabled) {
    enabled = !!enabled;
    if (enabled == l->selection_enabled)
        return;
    l->selection_enabled = enabled;
    gtk_widget_queue_draw(l->area);
}

void az_applist_scroll_to_top(AzAppList *l) {
    gtk_adjustment_set_value(l->vadj, 0.0);
}

int az_applist_visible_count(AzAppList *l) {
    return (int)l->visible->len;
}

/* ---- pointer -------------------------------------------------------------*/
static int row_at(AzAppList *l, double widget_y) {
    double y = widget_y + gtk_adjustment_get_value(l->vadj);
    int idx = (int)(y / AZ_ROW_H);
    if (idx >= 0 && (guint)idx < l->visible->len)
        return idx;
    return -1;
}

static gboolean on_motion(GtkWidget *w, GdkEventMotion *e, gpointer data) {
    (void)w;
    AzAppList *l = data;
    int idx = row_at(l, e->y);
    if (idx != l->hover) {
        l->hover = idx;
        gtk_widget_queue_draw(l->area);
    }
    return FALSE;
}

static gboolean on_leave(GtkWidget *w, GdkEventCrossing *e, gpointer data) {
    (void)w; (void)e;
    AzAppList *l = data;
    if (l->hover != -1) {
        l->hover = -1;
        gtk_widget_queue_draw(l->area);
    }
    return FALSE;
}

static void on_vadj_changed(GtkAdjustment *adj, gpointer data) {
    (void)adj;
    AzAppList *l = data;
    gtk_widget_queue_draw(l->area);
}

static gboolean on_button(GtkWidget *w, GdkEventButton *e, gpointer data) {
    (void)w;
    AzAppList *l = data;
    if (e->button == 1) {
        int idx = row_at(l, e->y);
        if (idx >= 0 && (guint)idx < l->visible->len) {
            Row *r = g_ptr_array_index(l->visible, idx);
            l->on_activate(r->entry, l->user);
        }
    }
    return FALSE;
}

/* ---- entries / rebuild --------------------------------------------------- */
gboolean az_applist_set_entries(AzAppList *l, GPtrArray *entries) {
    GString *sig = g_string_new(NULL);
    build_signature(entries, sig);
    if (l->rows->len > 0 && strcmp(sig->str, l->signature->str) == 0) {
        g_string_free(sig, TRUE);
        return FALSE;                 /* nothing drawn changed */
    }
    g_string_assign(l->signature, sig->str);
    g_string_free(sig, TRUE);

    g_array_set_size(l->rows, 0);
    for (guint i = 0; i < entries->len; i++) {
        AzAppEntry *e = g_ptr_array_index(entries, i);
        Row r = { 0 };
        r.entry = e;
        r.icon = az_icons_load(l->icons, e->icon);
        r.y = 0;
        r.shown = FALSE;
        g_array_append_val(l->rows, r);
    }
    l->selected = -1;
    l->hover = -1;
    return TRUE;
}

/* ---- construction -------------------------------------------------------- */
static void on_size_alloc(GtkWidget *w, GdkRectangle *alloc, gpointer data) {
    (void)w;
    AzAppList *l = data;
    l->width = alloc->width;
    gtk_widget_queue_draw(l->area);
}

AzAppList *az_applist_new(AzIcons *icons, AzActivateFn on_activate, gpointer user) {
    AzAppList *l = g_new0(AzAppList, 1);
    l->icons = icons;
    l->on_activate = on_activate;
    l->user = user;
    l->rows = g_array_new(FALSE, TRUE, sizeof(Row));
    l->visible = g_ptr_array_new();
    l->signature = g_string_new(NULL);
    l->selected = -1;
    l->hover = -1;
    l->selection_enabled = TRUE;
    l->width = AZ_DEFAULT_WIDTH;

    l->font_name = pango_font_description_new();
    pango_font_description_set_family(l->font_name, AZ_FONT_FAMILY);
    pango_font_description_set_size(l->font_name, AZ_FONT_APP_NAME * PANGO_SCALE);
    l->font_sub = pango_font_description_new();
    pango_font_description_set_family(l->font_sub, AZ_FONT_FAMILY);
    pango_font_description_set_size(l->font_sub, AZ_FONT_APP_TYPE * PANGO_SCALE);

    l->scrolled = gtk_scrolled_window_new(NULL, NULL);
    /* EXTERNAL vertical policy: the scrolled window still scrolls (wheel, adjustment)
     * but draws NO GTK scrollbar -- we overlay our own Kickoff pill instead. Overlay
     * + kinetic scrolling OFF kills GTK's edge-overshoot glow at the scroll limits
     * (item E): Tk had none of that bounce. */
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(l->scrolled),
                                   GTK_POLICY_NEVER, GTK_POLICY_EXTERNAL);
    gtk_scrolled_window_set_overlay_scrolling(GTK_SCROLLED_WINDOW(l->scrolled), FALSE);
    gtk_scrolled_window_set_kinetic_scrolling(GTK_SCROLLED_WINDOW(l->scrolled), FALSE);
    l->vadj = gtk_scrolled_window_get_vadjustment(
        GTK_SCROLLED_WINDOW(l->scrolled));

    l->area = gtk_drawing_area_new();
    gtk_widget_add_events(l->area, GDK_POINTER_MOTION_MASK |
                          GDK_LEAVE_NOTIFY_MASK | GDK_BUTTON_PRESS_MASK);
    g_signal_connect(l->area, "draw", G_CALLBACK(on_draw), l);
    g_signal_connect(l->area, "motion-notify-event", G_CALLBACK(on_motion), l);
    g_signal_connect(l->area, "leave-notify-event", G_CALLBACK(on_leave), l);
    g_signal_connect(l->area, "button-press-event", G_CALLBACK(on_button), l);
    g_signal_connect(l->area, "size-allocate", G_CALLBACK(on_size_alloc), l);
    g_signal_connect(l->vadj, "value-changed",
                     G_CALLBACK(on_vadj_changed), l);

    gtk_container_add(GTK_CONTAINER(l->scrolled), l->area);

    /* Pack the custom scrollbar in a row to the RIGHT of the list, reserving its 12px
     * column exactly like Tk (KickoffScrollBar packed side="right", fill="y"). This
     * makes the list genuinely narrower (so the selection outline stops before the bar,
     * matching Tk) rather than floating over it; when the bar auto-hides (content fits)
     * it gives the column back to the list, like Tk's pack_forget. */
    l->overlay = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_box_pack_start(GTK_BOX(l->overlay), l->scrolled, TRUE, TRUE, 0);
    l->kscroll = az_kscroll_new(l->vadj);
    gtk_box_pack_start(GTK_BOX(l->overlay), az_kscroll_widget(l->kscroll),
                       FALSE, FALSE, 0);
    return l;
}

GtkWidget *az_applist_widget(AzAppList *l) {
    return l->overlay;
}

void az_applist_free(AzAppList *l) {
    if (!l) return;
    az_kscroll_free(l->kscroll);
    g_array_free(l->rows, TRUE);
    g_ptr_array_free(l->visible, TRUE);
    g_string_free(l->signature, TRUE);
    pango_font_description_free(l->font_name);
    pango_font_description_free(l->font_sub);
    g_free(l);
}
