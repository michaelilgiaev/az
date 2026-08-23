/* Az'arch window switcher -- the horizontal tile strip. See layout.h.
 *
 * Look mirrors the application menu's dark Breeze family (theme.c colours): a rounded
 * panel, tiles with a live thumbnail (or the app icon when no pixmap exists yet), the app
 * icon badged bottom-left, the title underneath, and a Breeze-blue border on the selected
 * tile. */
#include "layout.h"
#include "ordering.h"
#include "windows.h"
#include "thumbnail.h"

#include "theme.h"      /* AZ_*_COLOR, az_color(AZ_C_SELECT_BORDER) */
#include "icons.h"      /* AzIcons, az_icons_new/az_icons_load */

#define TILE_W       200
#define TILE_H       130
#define BADGE_PX      36
#define STRIP_SPACING 12

struct AzStrip {
    GtkWidget *box;             /* the horizontal GtkBox of tiles */
    GPtrArray *tiles;           /* GtkWidget* per tile (borrowed; owned by GTK tree) */
    GArray    *xids;            /* unsigned long per tile, parallel to tiles */
    AzIcons   *icons;           /* icon resolver for the badge + fallback */
    int        selected;
};

/* Install the strip CSS once per display (idempotent-ish; cheap to repeat). */
static void ensure_css(void) {
    static gboolean done = FALSE;
    if (done) return;
    done = TRUE;
    char *css = g_strdup_printf(
        ".az-strip { background-color: %s; border-radius: 12px; padding: 16px; }"
        ".az-tile { background-color: %s; border-radius: 6px; padding: 6px;"
        "           border: 3px solid transparent; }"
        ".az-tile-selected { border: 3px solid %s;"
        "           background-color: %s; }"
        ".az-title { color: %s; font-size: 11px; }",
        AZ_BG_COLOR, AZ_SURFACE_COLOR,
        az_color(AZ_C_SELECT_BORDER), az_color(AZ_C_SELECT_FILL),
        AZ_TEXT_COLOR);
    GtkCssProvider *p = gtk_css_provider_new();
    gtk_css_provider_load_from_data(p, css, -1, NULL);
    gtk_style_context_add_provider_for_screen(
        gdk_screen_get_default(), GTK_STYLE_PROVIDER(p),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(p);
    g_free(css);
}

AzStrip *az_strip_new(GtkWidget *parent) {
    ensure_css();
    AzStrip *s = g_new0(AzStrip, 1);
    s->box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, STRIP_SPACING);
    gtk_style_context_add_class(gtk_widget_get_style_context(s->box), "az-strip");
    gtk_widget_set_halign(s->box, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(s->box, GTK_ALIGN_CENTER);
    s->tiles = g_ptr_array_new();
    s->xids = g_array_new(FALSE, FALSE, sizeof(unsigned long));
    s->icons = az_icons_new(BADGE_PX);
    s->selected = 0;
    gtk_container_add(GTK_CONTAINER(parent), s->box);
    return s;
}

/* The tile image: the live thumbnail if we can grab one, else the app icon scaled up. */
static GtkWidget *tile_image(AzStrip *s, const AzWinIdent *w) {
    GdkPixbuf *thumb = az_thumbnail_capture(w->xid, TILE_W, TILE_H);
    if (thumb) {
        GtkWidget *img = gtk_image_new_from_pixbuf(thumb);
        g_object_unref(thumb);
        return img;
    }
    /* Fallback: the app icon (borrowed pixbuf, do not unref). */
    GdkPixbuf *icon = az_icons_load(s->icons, w->icon_name ? w->icon_name : "");
    GtkWidget *img = icon ? gtk_image_new_from_pixbuf(icon)
                          : gtk_image_new_from_icon_name("application-x-executable",
                                                         GTK_ICON_SIZE_DIALOG);
    gtk_widget_set_size_request(img, TILE_W, TILE_H);
    return img;
}

/* One tile: [ overlay(thumbnail, corner icon badge) ] over [ title label ]. */
static GtkWidget *make_tile(AzStrip *s, const AzWinIdent *w) {
    GtkWidget *tile = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_style_context_add_class(gtk_widget_get_style_context(tile), "az-tile");
    gtk_widget_set_size_request(tile, TILE_W, -1);

    GtkWidget *overlay = gtk_overlay_new();
    GtkWidget *img = tile_image(s, w);
    gtk_widget_set_halign(img, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(img, GTK_ALIGN_CENTER);
    gtk_container_add(GTK_CONTAINER(overlay), img);

    /* Corner app-icon badge (bottom-left, Windows-like). */
    GdkPixbuf *badge = az_icons_load(s->icons, w->icon_name ? w->icon_name : "");
    if (badge) {
        GtkWidget *bimg = gtk_image_new_from_pixbuf(badge);
        gtk_widget_set_halign(bimg, GTK_ALIGN_START);
        gtk_widget_set_valign(bimg, GTK_ALIGN_END);
        gtk_overlay_add_overlay(GTK_OVERLAY(overlay), bimg);
    }
    gtk_box_pack_start(GTK_BOX(tile), overlay, FALSE, FALSE, 0);

    GtkWidget *label = gtk_label_new(w->display_name ? w->display_name : "");
    gtk_style_context_add_class(gtk_widget_get_style_context(label), "az-title");
    gtk_label_set_ellipsize(GTK_LABEL(label), PANGO_ELLIPSIZE_END);
    gtk_label_set_max_width_chars(GTK_LABEL(label), 18);
    gtk_label_set_xalign(GTK_LABEL(label), 0.5f);
    gtk_box_pack_start(GTK_BOX(tile), label, FALSE, FALSE, 0);

    return tile;
}

static void clear_tiles(AzStrip *s) {
    GList *kids = gtk_container_get_children(GTK_CONTAINER(s->box));
    for (GList *l = kids; l; l = l->next)
        gtk_widget_destroy(GTK_WIDGET(l->data));
    g_list_free(kids);
    g_ptr_array_set_size(s->tiles, 0);
    g_array_set_size(s->xids, 0);
}

void az_strip_set_windows(AzStrip *s, GPtrArray *windows) {
    clear_tiles(s);
    guint n = windows ? windows->len : 0;
    for (guint i = 0; i < n; i++) {
        AzWinIdent *w = g_ptr_array_index(windows, i);
        GtkWidget *tile = make_tile(s, w);
        gtk_box_pack_start(GTK_BOX(s->box), tile, FALSE, FALSE, 0);
        g_ptr_array_add(s->tiles, tile);
        unsigned long xid = w->xid;
        g_array_append_val(s->xids, xid);
    }
    gtk_widget_show_all(s->box);
    if (s->selected >= (int)n) s->selected = (n > 0) ? (int)n - 1 : 0;
    az_strip_select(s, s->selected);
}

void az_strip_select(AzStrip *s, int i) {
    int n = (int)s->tiles->len;
    if (n <= 0) { s->selected = 0; return; }
    i = ((i % n) + n) % n;                 /* wrap into [0,n) */
    s->selected = i;
    for (int k = 0; k < n; k++) {
        GtkWidget *tile = g_ptr_array_index(s->tiles, k);
        GtkStyleContext *ctx = gtk_widget_get_style_context(tile);
        if (k == i) gtk_style_context_add_class(ctx, "az-tile-selected");
        else        gtk_style_context_remove_class(ctx, "az-tile-selected");
    }
}

int az_strip_selected(AzStrip *s) { return s->selected; }
int az_strip_count(AzStrip *s)    { return (int)s->tiles->len; }

unsigned long az_strip_selected_xid(AzStrip *s) {
    if (s->xids->len == 0) return 0;
    int i = s->selected;
    if (i < 0 || i >= (int)s->xids->len) return 0;
    return g_array_index(s->xids, unsigned long, i);
}

void az_strip_free(AzStrip *s) {
    if (!s) return;
    if (s->icons) az_icons_free(s->icons);
    if (s->tiles) g_ptr_array_free(s->tiles, TRUE);
    if (s->xids)  g_array_free(s->xids, TRUE);
    g_free(s);
}
