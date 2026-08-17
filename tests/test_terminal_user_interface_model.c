/* Az'arch -- headless C unit tests for the bare-`azarch` terminal user interface MODEL.
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
#include "terminal_user_interface.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;
#define CHECK(cond) do { \
    if (!(cond)) { printf("FAIL: %s (line %d)\n", #cond, __LINE__); failures++; } \
} while (0)

/* The top-level subsystems, in order (Network FIRST per the spec): Network, Theme, Wallpaper,
 * then the media controls Volume + Brightness (the follow-up spec added these -- they were
 * missing from the UI), then Machine Type (the PC/Laptop screen), and nothing else. */
static void test_top_level_is_network_theme_wallpaper(void)
{
    const AzScreen *m = az_screen_find("main");
    CHECK(m != NULL);
    CHECK(m->nrows == 8);
    CHECK(strcmp(m->rows[0].label, "Network") == 0);   /* Network is the first option */
    CHECK(strcmp(m->rows[1].label, "Theme") == 0);
    CHECK(strcmp(m->rows[2].label, "Wallpaper") == 0);
    CHECK(strcmp(m->rows[3].label, "Volume") == 0);
    CHECK(strcmp(m->rows[4].label, "Brightness") == 0);
    CHECK(strcmp(m->rows[5].label, "Default Applications") == 0);
    CHECK(strcmp(m->rows[6].label, "Display") == 0);
    CHECK(strcmp(m->rows[7].label, "Machine Type") == 0);
    /* the entry title is the (re)named "Az'arch Settings" */
    CHECK(strcmp(m->title, "Az'arch Settings") == 0);
}

/* Exactly the subsystems + the network sub-screens + the volume/brightness + the machine screen
 * are reachable -- no extras. */
static void test_screen_set_is_exactly_expected(void)
{
    const char *want[] = {
        "main", "theme", "wallpaper", "network",
        "network.wifi", "network.wired", "network.bluetooth",
        "network.airplane", "network.firewall",
        "volume", "brightness", "machine",
        /* Default Applications: the category list + one screen per category (Mail excluded --
         * no mail client shipped, so the TUI does not surface it). */
        "defaultapps",
        "defaultapps.web", "defaultapps.html", "defaultapps.music", "defaultapps.video",
        "defaultapps.photos", "defaultapps.word", "defaultapps.spreadsheet", "defaultapps.pdf",
        "defaultapps.source-code", "defaultapps.file-manager", "defaultapps.plain-text",
        "defaultapps.calculator", "defaultapps.terminal",
        /* Display: the screen + the scale chooser + the xrandr feature screens. */
        "display", "display.scale", "display.resolution", "display.refresh",
        "display.orientation", "display.monitors",
    };
    int n = az_screen_count();
    CHECK(n == (int)(sizeof want / sizeof want[0]));
    for (size_t i = 0; i < sizeof want / sizeof want[0]; i++)
        CHECK(az_screen_find(want[i]) != NULL);
    CHECK(az_screen_find("nonesuch") == NULL);
}

/* Volume + Brightness screens (the follow-up spec: "I don't see Volume and Brightness settings,
 * that should be there"). Volume shows the live level via a screen-level Current: probe and its
 * rows set a PRECISE level (or step/mute) via `azarch volume ...`. Brightness is the same but
 * LAPTOP-ONLY (its Current: probe reports PC vs Laptop). Neither needs sudo (the user session
 * owns audio/backlight), and neither echoes a per-row status (Current: shows it once). */
static void test_volume_and_brightness_screens(void)
{
    const AzScreen *v = az_screen_find("volume");
    CHECK(v != NULL);
    CHECK(strcmp(v->title, "Volume") == 0);
    CHECK(v->current == az_status_volume);          /* live level shown once, up top */
    CHECK(v->nrows >= 5);
    int has_mute = 0, has_set50 = 0, has_set100 = 0;
    for (int i = 0; i < v->nrows; i++) {
        CHECK(v->rows[i].kind == AZ_ACT_APPLY);
        CHECK(v->rows[i].needs_root == 0);          /* PipeWire/ALSA run in the user session */
        CHECK(v->rows[i].status == NULL);           /* no per-row echo (Current: shows it) */
        if (strcmp(v->rows[i].target, "azarch volume mute") == 0) has_mute = 1;
        if (strcmp(v->rows[i].target, "azarch volume set 50") == 0) has_set50 = 1;
        if (strcmp(v->rows[i].target, "azarch volume set 100") == 0) has_set100 = 1;
    }
    CHECK(has_mute == 1);
    CHECK(has_set50 == 1);
    CHECK(has_set100 == 1);

    const AzScreen *b = az_screen_find("brightness");
    CHECK(b != NULL);
    CHECK(strcmp(b->title, "Brightness") == 0);
    CHECK(b->current == az_status_brightness);      /* PC vs Laptop / the level, shown once */
    CHECK(b->nrows >= 4);
    int has_bset100 = 0;
    for (int i = 0; i < b->nrows; i++) {
        CHECK(b->rows[i].kind == AZ_ACT_APPLY);
        CHECK(b->rows[i].needs_root == 0);
        CHECK(b->rows[i].status == NULL);
        if (strcmp(b->rows[i].target, "azarch brightness set 100") == 0) has_bset100 = 1;
    }
    CHECK(has_bset100 == 1);

    /* the main-menu rows that descend here carry the live level as their at-a-glance summary */
    const AzScreen *main_s = az_screen_find("main");
    CHECK(main_s->rows[3].status == az_status_volume);
    CHECK(strcmp(main_s->rows[3].target, "volume") == 0);
    CHECK(main_s->rows[4].status == az_status_brightness);
    CHECK(strcmp(main_s->rows[4].target, "brightness") == 0);
}

/* The Machine Type screen: it shows the recognised type ONCE via a screen-level `.current`
 * probe (PC/Laptop), and its rows HARD-SWITCH the type -- Force PC / Force Laptop / Autodetect
 * -- each an apply that runs `azarch machine ...` (no sudo: it writes the user's own pointer).
 * This backs the spec's "add Machine Type ... display what it recognizes ... allow a hard
 * switch." */
static void test_machine_type_screen(void)
{
    const AzScreen *m = az_screen_find("machine");
    CHECK(m != NULL);
    CHECK(strcmp(m->title, "Machine Type") == 0);
    /* the recognised type is shown once, up top (a screen-level Current: probe) */
    CHECK(m->current == az_status_machine);
    /* three hard-switch rows: force PC, force Laptop, autodetect */
    CHECK(m->nrows == 3);
    CHECK(strcmp(m->rows[0].target, "azarch machine --pc") == 0);
    CHECK(strcmp(m->rows[1].target, "azarch machine --laptop") == 0);
    CHECK(strcmp(m->rows[2].target, "azarch machine --auto") == 0);
    for (int i = 0; i < m->nrows; i++) {
        CHECK(m->rows[i].kind == AZ_ACT_APPLY);
        CHECK(m->rows[i].needs_root == 0);       /* writes the user's own config, no sudo */
        CHECK(m->rows[i].status == NULL);        /* no per-row echo (Current: shows it once) */
    }
    /* the main-menu row that descends here carries the machine status as its at-a-glance summary
     * (Machine Type is now the EIGHTH row, after Volume, Brightness, Default Applications AND
     * Display were added before it) */
    const AzScreen *main_s = az_screen_find("main");
    CHECK(main_s->rows[7].status == az_status_machine);
    CHECK(main_s->rows[7].kind == AZ_ACT_SCREEN);
    CHECK(strcmp(main_s->rows[7].target, "machine") == 0);
}

/* Default Applications: a category list + one screen per category, each letting the user CHANGE
 * that category's default via an `azarch default-applications set ...` apply. The category set,
 * keys and the current-handler probes are the TUI half of the default_applications.py source;
 * a Python test pins the labels/keys against that source so C and Python cannot drift. */
static void test_default_applications_screens(void)
{
    /* the ROWS_MAIN entry that opens it */
    const AzScreen *main_s = az_screen_find("main");
    CHECK(strcmp(main_s->rows[5].label, "Default Applications") == 0);
    CHECK(main_s->rows[5].kind == AZ_ACT_SCREEN);
    CHECK(strcmp(main_s->rows[5].target, "defaultapps") == 0);

    /* the category list screen: 13 categories (Mail excluded), each a SCREEN row with a live
     * current-handler status. */
    const AzScreen *da = az_screen_find("defaultapps");
    CHECK(da != NULL);
    CHECK(strcmp(da->title, "Default Applications") == 0);
    CHECK(da->nrows == 13);
    const char *cats[] = {
        "Web", "HTML", "Music", "Video", "Photos", "Word", "Spreadsheet", "PDF",
        "Source Code", "File Manager", "Plain Text", "Calculator", "Terminal",
    };
    for (int i = 0; i < da->nrows; i++) {
        CHECK(da->rows[i].kind == AZ_ACT_SCREEN);
        CHECK(da->rows[i].status != NULL);          /* shows the live handler at a glance */
        CHECK(strcmp(da->rows[i].label, cats[i]) == 0);
    }
    /* Mail is NOT a category screen (no mail client shipped). */
    CHECK(az_screen_find("defaultapps.mail") == NULL);

    /* each category screen shows the current handler up top and CHANGES it via an apply that
     * runs `azarch default-applications set ...` -- no sudo (writes the user's own config). */
    const AzScreen *web = az_screen_find("defaultapps.web");
    CHECK(web != NULL);
    CHECK(web->current == az_status_da_web);
    CHECK(web->nrows >= 1);
    CHECK(web->rows[0].kind == AZ_ACT_APPLY);
    CHECK(web->rows[0].needs_root == 0);
    CHECK(strncmp(web->rows[0].target, "azarch default-applications set web ",
                  strlen("azarch default-applications set web ")) == 0);

    /* a multi-candidate category (Photos: xviewer + gimp + feh) really offers all choices. */
    const AzScreen *ph = az_screen_find("defaultapps.photos");
    CHECK(ph != NULL);
    CHECK(ph->current == az_status_da_photos);
    CHECK(ph->nrows == 3);
    int has_xviewer = 0, has_gimp = 0, has_feh = 0;
    for (int i = 0; i < ph->nrows; i++) {
        if (strstr(ph->rows[i].target, "xviewer.desktop")) has_xviewer = 1;
        if (strstr(ph->rows[i].target, "gimp.desktop")) has_gimp = 1;
        if (strstr(ph->rows[i].target, "feh.desktop")) has_feh = 1;
    }
    CHECK(has_xviewer == 1);
    CHECK(has_gimp == 1);
    CHECK(has_feh == 1);
}

/* Display: cinnamon-settings-display parity (xrandr) + the GLOBAL SCALE chooser. The scale
 * chooser is the firm requirement; its rows set the ONE scale via `azarch display scale`. */
static void test_display_screens(void)
{
    /* the ROWS_MAIN entry */
    const AzScreen *main_s = az_screen_find("main");
    CHECK(strcmp(main_s->rows[6].label, "Display") == 0);
    CHECK(main_s->rows[6].kind == AZ_ACT_SCREEN);
    CHECK(strcmp(main_s->rows[6].target, "display") == 0);
    CHECK(main_s->rows[6].status == az_status_display);

    const AzScreen *d = az_screen_find("display");
    CHECK(d != NULL);
    CHECK(strcmp(d->title, "Display") == 0);
    /* the top "Current: scale 1.35x" line was REMOVED at the user's request: the display screen
     * has NO .current, and each row shows its OWN current value inline via .status instead. */
    CHECK(d->current == NULL);
    /* the feature set: Global Scale + resolution/refresh/orientation/monitors, EACH with an
     * inline current-value probe (.status). */
    int has_scale = 0, has_res = 0, has_refresh = 0, has_orient = 0, has_mon = 0;
    for (int i = 0; i < d->nrows; i++) {
        CHECK(d->rows[i].status != NULL);   /* every display row shows its current value inline */
        if (strcmp(d->rows[i].target, "display.scale") == 0)
            { has_scale = 1; CHECK(d->rows[i].status == az_status_display_scale); }
        if (strcmp(d->rows[i].target, "display.resolution") == 0)
            { has_res = 1; CHECK(d->rows[i].status == az_status_display_resolution); }
        if (strcmp(d->rows[i].target, "display.refresh") == 0)
            { has_refresh = 1; CHECK(d->rows[i].status == az_status_display_refresh); }
        if (strcmp(d->rows[i].target, "display.orientation") == 0)
            { has_orient = 1; CHECK(d->rows[i].status == az_status_display_orientation); }
        if (strcmp(d->rows[i].target, "display.monitors") == 0)
            { has_mon = 1; CHECK(d->rows[i].status == az_status_display_monitors); }
    }
    CHECK(has_scale && has_res && has_refresh && has_orient && has_mon);

    /* the GLOBAL SCALE chooser: offers the scale options, each an apply, none needing sudo. */
    const AzScreen *sc = az_screen_find("display.scale");
    CHECK(sc != NULL);
    CHECK(sc->current == az_status_display_scale);
    CHECK(sc->nrows == 6);                       /* 1.00 .. 2.00 */
    int has_135 = 0, has_100 = 0, has_200 = 0;
    for (int i = 0; i < sc->nrows; i++) {
        CHECK(sc->rows[i].kind == AZ_ACT_APPLY);
        CHECK(sc->rows[i].needs_root == 0);      /* the X resource DB is per-session, no sudo */
        if (strcmp(sc->rows[i].target, "azarch display scale 1.35") == 0) has_135 = 1;
        if (strcmp(sc->rows[i].target, "azarch display scale 1.00") == 0) has_100 = 1;
        if (strcmp(sc->rows[i].target, "azarch display scale 2.00") == 0) has_200 = 1;
    }
    CHECK(has_135 && has_100 && has_200);

    /* orientation offers the four rotations. */
    const AzScreen *ori = az_screen_find("display.orientation");
    CHECK(ori != NULL);
    int has_normal = 0, has_left = 0, has_right = 0, has_inv = 0;
    for (int i = 0; i < ori->nrows; i++) {
        if (strstr(ori->rows[i].target, "rotate normal")) has_normal = 1;
        if (strstr(ori->rows[i].target, "rotate left")) has_left = 1;
        if (strstr(ori->rows[i].target, "rotate right")) has_right = 1;
        if (strstr(ori->rows[i].target, "rotate inverted")) has_inv = 1;
    }
    CHECK(has_normal && has_left && has_right && has_inv);
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
    /* theme needs no sudo (it configures the user session) -> needs_root stays 0 */
    CHECK(t->rows[0].needs_root == 0);
    CHECK(t->rows[1].needs_root == 0);
}

/* Every apply teaches its bash command (az_row_command); a plain sub-screen row teaches
 * nothing. This backs the "show the bash command that invokes the setting" requirement. */
static void test_row_command(void)
{
    const AzScreen *t = az_screen_find("theme");
    CHECK(strcmp(az_row_command(&t->rows[0]), "azarch theme --dark") == 0);
    /* a SCREEN row (Network parent) has no command to type */
    const AzScreen *m = az_screen_find("main");
    CHECK(az_row_command(&m->rows[0]) == NULL);
    /* a PORT row's command carries the "<port>" placeholder the user would type */
    const AzScreen *fw = az_screen_find("network.firewall");
    int found_port = 0;
    for (int i = 0; i < fw->nrows; i++) {
        if (fw->rows[i].kind == AZ_ACT_PORT) {
            found_port = 1;
            CHECK(strstr(az_row_command(&fw->rows[i]), "<port>") != NULL);
        }
    }
    CHECK(found_port == 1);
}

/* PROMPT: every apply/port row now teaches its UNDERLYING base command too (az_row_base) --
 * the "Base Command: $ ..." line, which `x` copies -- alongside the azarch wrapper (`c`). A
 * SCREEN row teaches neither. A PORT row's base carries the same "<port>" placeholder the
 * wrapper does. These are the exact commands wired in the model, verified end-to-end. */
static void test_row_base_command(void)
{
    /* Theme: the base is the gsettings call, the wrapper is the azarch one. */
    const AzScreen *t = az_screen_find("theme");
    CHECK(strcmp(az_row_base(&t->rows[0]),
                 "gsettings set org.gnome.desktop.interface color-scheme prefer-dark") == 0);
    CHECK(strcmp(az_row_command(&t->rows[0]), "azarch theme --dark") == 0);

    /* Airplane on: the PROMPT's worked example -- base nmcli, wrapper azarch. */
    const AzScreen *air = az_screen_find("network.airplane");
    CHECK(strcmp(air->rows[0].label, "Turn airplane mode on") == 0);
    CHECK(strcmp(az_row_base(&air->rows[0]), "sudo nmcli networking off") == 0);
    CHECK(strcmp(az_row_command(&air->rows[0]), "azarch network airplane on") == 0);

    /* Wallpaper base is the feh line ending in the real image path. */
    const AzScreen *w = az_screen_find("wallpaper");
    CHECK(strstr(az_row_base(&w->rows[0]), "feh --no-fehbg --bg-fill") != NULL);
    CHECK(strstr(az_row_base(&w->rows[0]),
                 "/usr/share/wallpapers/years/contents/images/1672x941.png") != NULL);

    /* A SCREEN row (main > Network) teaches NO command and NO base. */
    const AzScreen *m = az_screen_find("main");
    CHECK(az_row_command(&m->rows[0]) == NULL);
    CHECK(az_row_base(&m->rows[0]) == NULL);

    /* A PORT row's base AND wrapper both carry the "<port>" the user would type. */
    const AzScreen *fw = az_screen_find("network.firewall");
    for (int i = 0; i < fw->nrows; i++) {
        if (fw->rows[i].kind == AZ_ACT_PORT) {
            CHECK(strstr(az_row_base(&fw->rows[i]), "<port>") != NULL);
            CHECK(strstr(az_row_base(&fw->rows[i]), "ufw") != NULL);
            CHECK(strstr(az_row_command(&fw->rows[i]), "<port>") != NULL);
        }
    }
    /* Every APPLY/PORT row that has a wrapper also declares a base (no half-filled rows). */
    const char *screens[] = {"theme", "wallpaper", "volume", "brightness", "machine",
                             "network.wifi", "network.wired", "network.bluetooth",
                             "network.airplane", "network.firewall"};
    for (size_t s = 0; s < sizeof screens / sizeof screens[0]; s++) {
        const AzScreen *sc = az_screen_find(screens[s]);
        CHECK(sc != NULL);
        for (int i = 0; i < sc->nrows; i++)
            if (sc->rows[i].kind == AZ_ACT_APPLY || sc->rows[i].kind == AZ_ACT_PORT)
                CHECK(az_row_base(&sc->rows[i]) != NULL);
    }
}

/* PROMPT: the Wallpaper subtitle became the directory PATH ("Wallpapers directory: .../") and is
 * flagged to render in the accent (cyan) tight above "Current:". Other screens' subtitles stay
 * default (subtitle_accent == 0) and now EXPLAIN the wrapped tools. */
static void test_subtitles_explain_and_wallpaper_is_accented(void)
{
    const AzScreen *w = az_screen_find("wallpaper");
    CHECK(strstr(w->subtitle, "Wallpapers directory:") != NULL);
    CHECK(strstr(w->subtitle, "/usr/share/wallpapers/") != NULL);   /* trailing slash, per spec */
    CHECK(w->subtitle_accent == 1);                                  /* cyan + tight */

    /* The explanatory subtitles name the tool they wrap; they are NOT accented. */
    const AzScreen *fw = az_screen_find("network.firewall");
    CHECK(strstr(fw->subtitle, "ufw") != NULL);
    CHECK(fw->subtitle_accent == 0);
    const AzScreen *air = az_screen_find("network.airplane");
    CHECK(strstr(air->subtitle, "nmcli") != NULL);
    const AzScreen *vol = az_screen_find("volume");
    CHECK(strstr(vol->subtitle, "wpctl") != NULL);
    /* Theme keeps the pinned kitty-exemption phrase AND now names gsettings. */
    const AzScreen *th = az_screen_find("theme");
    CHECK(strstr(th->subtitle, "gsettings") != NULL);
    CHECK(strstr(th->subtitle, "Kitty does not follow the system theme") != NULL);
}

/* The Firewall screen can LIST ports (show_output) and OPEN/CLOSE/DELETE a port by typing its
 * number (AZ_ACT_PORT) -- the in-UI firewall config the spec asks for. Every firewall apply
 * needs root, so needs_root is set (the UI secures a credential first, no black screen). */
static void test_firewall_lists_and_configures_ports(void)
{
    const AzScreen *fw = az_screen_find("network.firewall");
    CHECK(fw != NULL);
    int has_list = 0, n_port = 0;
    for (int i = 0; i < fw->nrows; i++) {
        CHECK(fw->rows[i].needs_root == 1);        /* all firewall applies secure sudo first */
        if (fw->rows[i].kind == AZ_ACT_APPLY &&
            strcmp(fw->rows[i].target, "azarch network firewall port list") == 0) {
            has_list = 1;
            CHECK(fw->rows[i].show_output == 1);    /* the listing renders in the overlay */
        }
        if (fw->rows[i].kind == AZ_ACT_PORT) {
            n_port++;
            CHECK(fw->rows[i].show_output == 1);
        }
    }
    CHECK(has_list == 1);
    CHECK(n_port == 3);                             /* open / close / delete */
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
    test_volume_and_brightness_screens();
    test_machine_type_screen();
    test_default_applications_screens();
    test_display_screens();
    test_network_rows_descend();
    test_theme_rows_are_applies();
    test_row_command();
    test_row_base_command();
    test_subtitles_explain_and_wallpaper_is_accented();
    test_firewall_lists_and_configures_ports();
    test_current_is_screen_level_not_per_row();
    test_network_subscreens_have_current_and_no_row_spam();
    test_wallpaper_rows_preview();
    test_row_matches();
    test_wallpaper_image_path();

    if (failures == 0) {
        printf("test_terminal_user_interface_model: all checks passed\n");
        return 0;
    }
    printf("test_terminal_user_interface_model: %d check(s) FAILED\n", failures);
    return 1;
}
