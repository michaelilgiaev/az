/* Az'arch application menu (C port) -- unit tests for the hidden-id / installer
 * swap and app scanning. Built with `make test` (see Makefile); links apps.o and
 * its deps. Pure asserts, no framework -- exits non-zero on first failure.
 *
 * The key contract (the installer fix): calamares.desktop is HIDDEN (its stock
 * "Install System" entry runs a dead `pkexec calamares` with no polkit agent),
 * and azarch-install.desktop ("Az'arch Linux Installer", passwordless-sudo Exec)
 * is SHOWN so the menu launches/re-opens it. This mirrors what the C daemon ships
 * and must stay swapped relative to the old Python behaviour.
 */
#include "apps.h"
#include <glib.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

#define CHECK(cond, msg) do { \
    if (cond) { g_print("  ok   %s\n", msg); } \
    else      { g_print("  FAIL %s\n", msg); failures++; } \
} while (0)

/* --- the installer swap (the fix) ---------------------------------------- */
static void test_installer_swap(void) {
    g_print("installer swap:\n");
    CHECK(az_is_hidden_desktop_id("calamares.desktop") == TRUE,
          "calamares.desktop is HIDDEN");
    CHECK(az_is_hidden_desktop_id("azarch-install.desktop") == FALSE,
          "azarch-install.desktop is SHOWN");
}

/* --- other denylist ids stay hidden -------------------------------------- */
static void test_denylist(void) {
    g_print("denylist:\n");
    const char *hidden[] = {
        "azarch-application-menu.desktop",
        "azarch-application-menu-shortcut.desktop",
        "bssh.desktop", "bvnc.desktop", "avahi-discover.desktop",
        "kdesystemsettings.desktop", "lstopo.desktop", "htop.desktop",
        "lftp.desktop", "cups.desktop", "org.kde.kmenuedit.desktop",
        "assistant.desktop", "qdbusviewer.desktop", "linguist.desktop",
        "qv4l2.desktop", "qvidcap.desktop", "designer.desktop",
        "vim.desktop", NULL,
    };
    for (int i = 0; hidden[i]; i++)
        CHECK(az_is_hidden_desktop_id(hidden[i]) == TRUE, hidden[i]);
    /* The real System Settings must NOT be hidden (only KDE's duplicate is). */
    CHECK(az_is_hidden_desktop_id("systemsettings.desktop") == FALSE,
          "systemsettings.desktop is SHOWN");
    /* A normal app is never hidden. */
    CHECK(az_is_hidden_desktop_id("kitty.desktop") == FALSE,
          "kitty.desktop is SHOWN");
}

/* --- category typing (a couple of spot checks) --------------------------- */
static void test_category_type(void) {
    g_print("category type:\n");
    char *web[]  = { "Network", "WebBrowser", NULL };
    char *t1 = az_category_type(web);
    CHECK(t1 && strcmp(t1, "Web Browser") == 0, "WebBrowser -> 'Web Browser'");
    g_free(t1);

    char *term[] = { "System", "TerminalEmulator", NULL };
    char *t2 = az_category_type(term);
    CHECK(t2 && strcmp(t2, "Terminal") == 0, "TerminalEmulator -> 'Terminal'");
    g_free(t2);

    char *empty[] = { NULL };
    char *t3 = az_category_type(empty);
    CHECK(t3 != NULL && t3[0] != '\0', "empty categories -> non-empty fallback");
    g_free(t3);
}

int main(void) {
    test_installer_swap();
    test_denylist();
    test_category_type();
    if (failures) {
        g_printerr("\n%d test(s) FAILED\n", failures);
        return 1;
    }
    g_print("\nall tests passed\n");
    return 0;
}
