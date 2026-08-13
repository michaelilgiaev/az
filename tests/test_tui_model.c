/* Az'arch -- headless C unit tests for the bare-`azarch` TUI MODEL.
 *
 * The UI's menu tree + the search filter + the wallpaper path are pure data/logic in
 * model.c (no terminal), so we exercise them directly here -- the C counterpart of the old
 * Python build_menu()/filter_items tests. No X, no kitty, no ncurses.
 *
 * We deliberately test az_row_matches only with queries that hit the LABEL (or the empty
 * query), both of which short-circuit BEFORE the live status probe -- so the tests never
 * fork nmcli/ufw and stay deterministic on any host. tests/Makefile compiles this against
 * the shipping model.c.
 */
#include "tui.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;
#define CHECK(cond) do { \
    if (!(cond)) { printf("FAIL: %s (line %d)\n", #cond, __LINE__); failures++; } \
} while (0)

/* The three top-level subsystems, in order (Network FIRST per the spec), and nothing else. */
static void test_top_level_is_network_theme_wallpaper(void)
{
    const AzScreen *m = az_screen_find("main");
    CHECK(m != NULL);
    CHECK(m->nrows == 3);
    CHECK(strcmp(m->rows[0].label, "Network") == 0);   /* Network is the first option */
    CHECK(strcmp(m->rows[1].label, "Theme") == 0);
    CHECK(strcmp(m->rows[2].label, "Wallpaper") == 0);
    /* the entry title is the (re)named "Az'arch Settings" */
    CHECK(strcmp(m->title, "Az'arch Settings") == 0);
}

/* Exactly the three subsystems + the network sub-screens are reachable -- no extras. */
static void test_screen_set_is_exactly_expected(void)
{
    const char *want[] = {
        "main", "theme", "wallpaper", "network",
        "network.wifi", "network.wired", "network.bluetooth",
        "network.airplane", "network.firewall",
    };
    int n = az_screen_count();
    CHECK(n == (int)(sizeof want / sizeof want[0]));
    for (size_t i = 0; i < sizeof want / sizeof want[0]; i++)
        CHECK(az_screen_find(want[i]) != NULL);
    CHECK(az_screen_find("nonesuch") == NULL);
}

/* Network rows all DESCEND into a real child screen (they are navigation, not applies). */
static void test_network_rows_descend(void)
{
    const AzScreen *net = az_screen_find("network");
    CHECK(net != NULL);
    for (int i = 0; i < net->nrows; i++) {
        CHECK(net->rows[i].kind == AZ_ACT_SCREEN);
        CHECK(az_screen_find(net->rows[i].target) != NULL);
    }
}

/* Theme rows are APPLIES that run the tested `azarch theme` subcommand. */
static void test_theme_rows_are_applies(void)
{
    const AzScreen *t = az_screen_find("theme");
    CHECK(t != NULL);
    CHECK(t->nrows == 2);
    CHECK(strcmp(t->rows[0].label, "Dark") == 0);
    CHECK(strcmp(t->rows[1].label, "White") == 0);
    CHECK(t->rows[0].kind == AZ_ACT_APPLY);
    CHECK(strcmp(t->rows[0].target, "azarch theme --dark") == 0);
    CHECK(strcmp(t->rows[1].target, "azarch theme --white") == 0);
    /* both request the theme preview */
    CHECK(t->rows[0].preview == AZ_PV_THEME);
    CHECK(t->rows[1].preview == AZ_PV_THEME);
    /* both apply QUIETLY (no sudo/tty needed -> no CLI text flashes over the UI) */
    CHECK(t->rows[0].quiet == 1);
    CHECK(t->rows[1].quiet == 1);
}

/* The "Current:" line comes from the SCREEN, not a per-row status: Theme and Wallpaper set
 * a `.current` probe and their rows carry NO status (so no "white"/"years" echoes trail each
 * option), while other screens have no `.current` line at all. */
static void test_current_is_screen_level_not_per_row(void)
{
    const AzScreen *t = az_screen_find("theme");
    const AzScreen *w = az_screen_find("wallpaper");
    const AzScreen *m = az_screen_find("main");
    CHECK(t->current != NULL);
    CHECK(w->current != NULL);
    CHECK(m->current == NULL);              /* main has no "Current:" line */
    /* Theme/Wallpaper rows are label-only (no trailing status echo). */
    for (int i = 0; i < t->nrows; i++) CHECK(t->rows[i].status == NULL);
    for (int i = 0; i < w->nrows; i++) CHECK(w->rows[i].status == NULL);
    /* main's rows DO keep a status (the at-a-glance sub-screen summary). */
    CHECK(m->rows[0].status != NULL);
}

/* THE ANTI-SPAM CONTRACT. Every network sub-screen (Wifi/Wired/Bluetooth/Airplane/Firewall)
 * shows its live state EXACTLY ONCE via a screen-level `.current` probe -- and its action rows
 * carry NO per-row .status. This is the fix for "radio enabled" being echoed on all four Wifi
 * rows: the state now appears only in the "Current:" line, never after each option. */
static void test_network_subscreens_have_current_and_no_row_spam(void)
{
    const char *subs[] = {
        "network.wifi", "network.wired", "network.bluetooth",
        "network.airplane", "network.firewall",
    };
    for (size_t i = 0; i < sizeof subs / sizeof subs[0]; i++) {
        const AzScreen *s = az_screen_find(subs[i]);
        CHECK(s != NULL);
        CHECK(s->current != NULL);                       /* state shown ONCE, up top */
        for (int r = 0; r < s->nrows; r++)
            CHECK(s->rows[r].status == NULL);            /* no per-row echo (no spam) */
    }
    /* The Network PARENT screen keeps one distinct status per row (a genuine at-a-glance
     * summary of each sub-screen -- not a repeated label), so those DO have a status. */
    const AzScreen *net = az_screen_find("network");
    for (int r = 0; r < net->nrows; r++) CHECK(net->rows[r].status != NULL);
}

/* Wallpaper rows request the image preview and carry the right ids. */
static void test_wallpaper_rows_preview(void)
{
    const AzScreen *w = az_screen_find("wallpaper");
    CHECK(w != NULL);
    CHECK(w->nrows == 2);
    CHECK(w->rows[0].preview == AZ_PV_WALLPAPER);
    CHECK(strcmp(w->rows[0].preview_arg, "years") == 0);
    CHECK(strcmp(w->rows[1].preview_arg, "decades") == 0);
    /* the screen names the wallpaper directory (the spec) */
    CHECK(strstr(w->subtitle, "/usr/share/wallpapers") != NULL);
}

/* The search filter: empty query matches all; a label substring matches; a miss doesn't.
 * All three cases short-circuit before the live status probe. */
static void test_row_matches(void)
{
    const AzScreen *net = az_screen_find("network");
    const AzRow *fw = &net->rows[4];    /* Firewall */
    CHECK(strcmp(fw->label, "Firewall") == 0);
    CHECK(az_row_matches(fw, "") == 1);        /* empty -> all */
    CHECK(az_row_matches(fw, NULL) == 1);
    CHECK(az_row_matches(fw, "fire") == 1);    /* case-insensitive label substring */
    CHECK(az_row_matches(fw, "FIRE") == 1);
    CHECK(az_row_matches(fw, "wall") == 1);
    CHECK(az_row_matches(fw, "zzz") == 0);     /* a miss */
    /* Wifi row must NOT match "fire" */
    CHECK(az_row_matches(&net->rows[0], "fire") == 0);
}

/* The wallpaper image path mirrors wallpaper.py's on-disk layout. */
static void test_wallpaper_image_path(void)
{
    char buf[512];
    az_wallpaper_image("years", buf, sizeof buf);
    CHECK(strcmp(buf, "/usr/share/wallpapers/years/contents/images/1672x941.png") == 0);
    az_wallpaper_image("decades", buf, sizeof buf);
    CHECK(strstr(buf, "/decades/contents/images/1672x941.png") != NULL);
}

int main(void)
{
    test_top_level_is_network_theme_wallpaper();
    test_screen_set_is_exactly_expected();
    test_network_rows_descend();
    test_theme_rows_are_applies();
    test_current_is_screen_level_not_per_row();
    test_network_subscreens_have_current_and_no_row_spam();
    test_wallpaper_rows_preview();
    test_row_matches();
    test_wallpaper_image_path();

    if (failures == 0) {
        printf("test_tui_model: all checks passed\n");
        return 0;
    }
    printf("test_tui_model: %d check(s) FAILED\n", failures);
    return 1;
}
