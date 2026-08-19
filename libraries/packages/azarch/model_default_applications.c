/* Az'arch bare-`azarch` terminal user interface (C) -- the Default Applications RUNTIME screens.
 *
 * Split out of model_tree.c (which holds the static screen TREE) so each file stays under the
 * per-file size budget. This TU owns the ONE dynamic corner of the model: the per-category
 * "defaultapps.<key>" screens whose candidate rows RESOLVE LIVE against the installed .desktop
 * files (install Firefox -> firefox.desktop appears under Web/HTML/PDF; remove it -> it drops
 * off), each labelled with the bare .desktop id and disclosing WHERE the .desktop files live.
 *
 * az_screen_find() (model_tree.c) spots the "defaultapps." prefix and calls az_da_screen() here.
 * The AZ_DA_CATS descriptor table (key + full MIME list + curated seed) mirrors
 * packages/azarch/default_applications.py (CATEGORIES / CANDIDATES / CATEGORY_KEYS) and is pinned
 * to it by a test, so the C resolver offers the same seed and matches the same MIME types as the
 * Python side (packages/azarch/default_applications_cli._da_resolved_candidates).
 */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1

#include "terminal_user_interface.h"

#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <dirent.h>

/* The category descriptor: key (CLI token + screen id suffix), the FULL mime list (space-joined,
 * for the base command and the installed-app MIME match), and the CURATED seed handlers
 * (space-joined, shipped-with-Az'arch, offered first if installed). Empty mimes => a non-MIME
 * category (Calculator/Terminal), where the seed IS the whole list. Mirrors default_applications.py. */
typedef struct {
    const char *key;
    const char *mimes;   /* space-separated MIME types, "" for non-MIME categories */
    const char *seed;    /* space-separated curated .desktop ids (shipped defaults first) */
} AzDaCat;

static const AzDaCat AZ_DA_CATS[] = {
    {"web",          "x-scheme-handler/http x-scheme-handler/https", "librewolf.desktop"},
    {"html",         "text/html application/xhtml+xml", "librewolf.desktop org.gnome.gedit.desktop"},
    {"music",        "audio/mpeg audio/flac audio/ogg audio/x-wav audio/x-vorbis+ogg audio/mp4 audio/aac audio/x-m4a", "vlc.desktop"},
    {"video",        "video/mp4 video/x-matroska video/webm video/x-msvideo video/quicktime video/mpeg video/x-flv", "vlc.desktop"},
    {"photos",       "image/jpeg image/png image/gif image/bmp image/tiff image/webp image/x-xpixmap image/svg+xml", "xviewer.desktop gimp.desktop feh.desktop"},
    {"word",         "application/vnd.openxmlformats-officedocument.wordprocessingml.document application/msword application/vnd.oasis.opendocument.text application/rtf", "libreoffice-writer.desktop"},
    {"spreadsheet",  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet application/vnd.ms-excel application/vnd.oasis.opendocument.spreadsheet text/csv", "libreoffice-calc.desktop"},
    {"pdf",          "application/pdf", "librewolf.desktop"},
    {"source-code",  "text/x-csrc text/x-chdr text/x-python text/x-shellscript application/javascript text/x-c++src application/json text/markdown text/xml", "org.gnome.gedit.desktop vim.desktop"},
    {"file-manager", "inode/directory", "thunar.desktop"},
    {"plain-text",   "text/plain", "org.gnome.gedit.desktop vim.desktop"},
    {"calculator",   "", "qalculate-gtk.desktop"},
    {"terminal",     "", "kitty.desktop"},
};

#define AZ_DA_MAX_ROWS 64           /* generous: a category never has this many installed handlers */
/* String arena for the subtitle + every row's label/target/base. Sized for the WORST case so a
 * real system never truncates: AZ_DA_MAX_ROWS rows, each up to a long .desktop id (label) + the
 * `azarch default-applications set <key> <id>` target + a base command that repeats the id and
 * the full MIME list (the widest is Music/Video at ~120 bytes of MIME). ~48KB is comfortably
 * above 64 * (worst row) + the disclosure subtitle, so interning never fails in practice; if it
 * somehow did, az_da_intern returns NULL and the row is skipped cleanly (never a smash), and the
 * subtitle is interned FIRST so the disclosure line is never the thing dropped. */
#define AZ_DA_ARENA    49152

static AzScreen  g_da_screen;
static AzRow     g_da_rows[AZ_DA_MAX_ROWS];
static char      g_da_arena[AZ_DA_ARENA];
static size_t    g_da_used;
static char      g_da_id[96];       /* our own copy of the looked-up id (screen->id lifetime) */

/* Map a category key to its display LABEL and its live-handler probe. Kept beside the probes
 * (declared in the header) so the runtime screen shows the same title + "Current:" the static
 * ones did. Pinned to default_applications.py's labels by a test (via AZ_DA_CATS ordering). */
static const char *az_da_label(const char *key)
{
    if (!strcmp(key, "web"))          return "Web";
    if (!strcmp(key, "html"))         return "HTML";
    if (!strcmp(key, "music"))        return "Music";
    if (!strcmp(key, "video"))        return "Video";
    if (!strcmp(key, "photos"))       return "Photos";
    if (!strcmp(key, "word"))         return "Word";
    if (!strcmp(key, "spreadsheet"))  return "Spreadsheet";
    if (!strcmp(key, "pdf"))          return "PDF";
    if (!strcmp(key, "source-code"))  return "Source Code";
    if (!strcmp(key, "file-manager")) return "File Manager";
    if (!strcmp(key, "plain-text"))   return "Plain Text";
    if (!strcmp(key, "calculator"))   return "Calculator";
    if (!strcmp(key, "terminal"))     return "Terminal";
    return key;
}

static const char *(*az_da_probe(const char *key))(char *, size_t)
{
    if (!strcmp(key, "web"))          return az_status_da_web;
    if (!strcmp(key, "html"))         return az_status_da_html;
    if (!strcmp(key, "music"))        return az_status_da_music;
    if (!strcmp(key, "video"))        return az_status_da_video;
    if (!strcmp(key, "photos"))       return az_status_da_photos;
    if (!strcmp(key, "word"))         return az_status_da_word;
    if (!strcmp(key, "spreadsheet"))  return az_status_da_spreadsheet;
    if (!strcmp(key, "pdf"))          return az_status_da_pdf;
    if (!strcmp(key, "source-code"))  return az_status_da_source_code;
    if (!strcmp(key, "file-manager")) return az_status_da_file_manager;
    if (!strcmp(key, "plain-text"))   return az_status_da_plain_text;
    if (!strcmp(key, "calculator"))   return az_status_da_calculator;
    if (!strcmp(key, "terminal"))     return az_status_da_terminal;
    return NULL;
}

static const AzDaCat *az_da_cat(const char *key)
{
    for (size_t i = 0; i < sizeof AZ_DA_CATS / sizeof AZ_DA_CATS[0]; i++)
        if (!strcmp(AZ_DA_CATS[i].key, key)) return &AZ_DA_CATS[i];
    return NULL;
}

/* Copy a NUL-terminated string into the arena; return a stable pointer, or NULL if it would
 * overflow (the caller then skips that row -- a truncated menu is better than a smash). */
static const char *az_da_intern(const char *s)
{
    size_t n = strlen(s) + 1;
    if (g_da_used + n > sizeof g_da_arena) return NULL;
    char *p = g_da_arena + g_da_used;
    memcpy(p, s, n);
    g_da_used += n;
    return p;
}

/* The .desktop application directories, in priority order (user dir first), honouring
 * $XDG_DATA_HOME / $XDG_DATA_DIRS. Fills dirs[] (up to max), returns the count. Mirrors
 * default_applications_cli._da_desktop_dirs. */
/* A directory path buffer. Sized generously; the base (XDG dir) is bounded to AZ_DA_DIRBASE so
 * appending "/applications" always fits (keeps -Wformat-truncation quiet). */
#define AZ_DA_DIRBASE 480
#define AZ_DA_DIRLEN  512
typedef char AzDaDir[AZ_DA_DIRLEN];

static int az_da_dirs(AzDaDir *dirs, int max)
{
    int n = 0;
    const char *home = getenv("HOME");
    const char *dh = getenv("XDG_DATA_HOME");
    char databuf[AZ_DA_DIRBASE];
    if (dh && dh[0]) snprintf(databuf, sizeof databuf, "%s", dh);
    else snprintf(databuf, sizeof databuf, "%s/.local/share", home ? home : "");
    if (n < max) snprintf(dirs[n++], AZ_DA_DIRLEN, "%s/applications", databuf);
    const char *dd = getenv("XDG_DATA_DIRS");
    if (!dd || !dd[0]) dd = "/usr/local/share:/usr/share";
    char ddcopy[1024];
    snprintf(ddcopy, sizeof ddcopy, "%s", dd);
    char *save = NULL;
    for (char *tok = strtok_r(ddcopy, ":", &save); tok && n < max;
         tok = strtok_r(NULL, ":", &save)) {
        if (!tok[0]) continue;
        char base[AZ_DA_DIRBASE];
        snprintf(base, sizeof base, "%s", tok);
        char cand[AZ_DA_DIRLEN];
        snprintf(cand, sizeof cand, "%s/applications", base);
        int dup = 0;
        for (int i = 0; i < n; i++) if (!strcmp(dirs[i], cand)) { dup = 1; break; }
        if (!dup) snprintf(dirs[n++], AZ_DA_DIRLEN, "%s", cand);
    }
    return n;
}

/* A .desktop id is at most this long (basename). Path buffers = dir + '/' + id + NUL, with a
 * little slack so -Wformat-truncation is satisfied even when it treats the (decayed) dir pointer
 * as unbounded -- we cap both components with %.*s at the call sites. */
#define AZ_DA_IDLEN   256
#define AZ_DA_PATHLEN (AZ_DA_DIRLEN + AZ_DA_IDLEN + 8)

/* True if <desktop_id> exists as a regular file in any application dir. */
static int az_da_installed(AzDaDir *dirs, int ndirs, const char *desktop_id)
{
    for (int i = 0; i < ndirs; i++) {
        char path[AZ_DA_PATHLEN];
        /* %.*s caps both components (dir <= AZ_DA_DIRLEN-1, id <= AZ_DA_IDLEN-1; a .desktop
         * basename is never longer), so -Wformat-truncation is provably safe. */
        snprintf(path, sizeof path, "%.*s/%.*s",
                 AZ_DA_DIRLEN - 1, dirs[i], AZ_DA_IDLEN - 1, desktop_id);
        FILE *f = fopen(path, "r");
        if (f) { fclose(f); return 1; }
    }
    return 0;
}

/* True if the .desktop at <path> declares ANY of the space-separated <mimes> on its MimeType=
 * line and is not Hidden/NoDisplay. Mirrors default_applications_cli._da_desktop_declares_mime. */
static int az_da_declares_mime(const char *path, const char *mimes)
{
    if (!mimes || !mimes[0]) return 0;
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    char line[4096];
    int in_entry = 0, hidden = 0, match = 0;
    while (fgets(line, sizeof line, f)) {
        char *s = line;
        while (*s == ' ' || *s == '\t') s++;
        size_t l = strlen(s);
        while (l > 0 && (s[l-1] == '\n' || s[l-1] == '\r' || s[l-1] == ' ' || s[l-1] == '\t'))
            s[--l] = '\0';
        if (s[0] == '[' && l > 1 && s[l-1] == ']') { in_entry = !strcmp(s, "[Desktop Entry]"); continue; }
        if (!in_entry) continue;
        char *eq = strchr(s, '=');
        if (!eq) continue;
        *eq = '\0';
        const char *k = s, *v = eq + 1;
        if (!strcmp(k, "MimeType")) {
            /* does any ';'-separated declared type appear in the wanted space-separated set? */
            char decls[4096];
            snprintf(decls, sizeof decls, "%s", v);
            char *save = NULL;
            for (char *t = strtok_r(decls, ";", &save); t; t = strtok_r(NULL, ";", &save)) {
                if (!t[0]) continue;
                /* wanted-set membership: match " t " within " mimes " (space-bounded). */
                char needle[256], hay[4096];
                snprintf(needle, sizeof needle, " %s ", t);
                snprintf(hay, sizeof hay, " %s ", mimes);
                if (strstr(hay, needle)) { match = 1; break; }
            }
        } else if ((!strcmp(k, "Hidden") || !strcmp(k, "NoDisplay"))) {
            if (!strcmp(v, "true") || !strcmp(v, "True")) hidden = 1;
        }
    }
    fclose(f);
    return match && !hidden;
}

/* Append a candidate row (label = bare id, target = the set-command, base = the xdg-mime/exo
 * line) if we have not already added <id> and the arena has room. Returns 1 if added. */
static int az_da_add_row(int *pn, const char *seen[], int *pseen, const char *key,
                         const char *mimes, const char *id)
{
    for (int i = 0; i < *pseen; i++) if (!strcmp(seen[i], id)) return 0;
    if (*pn >= AZ_DA_MAX_ROWS) return 0;
    char tmp[1024];
    const char *label = az_da_intern(id);
    snprintf(tmp, sizeof tmp, "azarch default-applications set %s %s", key, id);
    const char *target = az_da_intern(tmp);
    const char *base;
    if (!strcmp(key, "terminal")) {
        char *bn = tmp;
        snprintf(tmp, sizeof tmp, "%s", id);
        char *dot = strstr(bn, ".desktop");
        if (dot) *dot = '\0';
        char b2[1024];
        snprintf(b2, sizeof b2, "printf 'TerminalEmulator=%s\\n' >> ~/.config/xfce4/helpers.rc", bn);
        base = az_da_intern(b2);
    } else if (!mimes || !mimes[0]) {
        base = az_da_intern("(no MIME default -- this app is recorded, not xdg-mime backed)");
    } else {
        char b2[2048];
        snprintf(b2, sizeof b2, "xdg-mime default %s %s", id, mimes);
        base = az_da_intern(b2);
    }
    if (!label || !target || !base) return 0;   /* arena exhausted: skip cleanly */
    seen[(*pseen)++] = label;
    g_da_rows[*pn].label = label;
    g_da_rows[*pn].kind = AZ_ACT_APPLY;
    g_da_rows[*pn].target = target;
    g_da_rows[*pn].base = base;
    (*pn)++;
    return 1;
}

/* Build (into the module-static storage) the runtime screen for `defaultapps.<key>`, or return
 * NULL if <id> is not a defaultapps category id. Rows = curated-installed (curated order) then
 * every OTHER installed .desktop declaring one of the category's MIME types (sorted), deduped. */
const AzScreen *az_da_screen(const char *id)
{
    const char *prefix = "defaultapps.";
    size_t plen = strlen(prefix);
    if (strncmp(id, prefix, plen) != 0) return NULL;
    const char *key = id + plen;
    const AzDaCat *cat = az_da_cat(key);
    if (!cat) return NULL;

    /* reset the arenas for this build */
    g_da_used = 0;
    snprintf(g_da_id, sizeof g_da_id, "%s", id);

    /* Intern the disclosure subtitle FIRST -- WHERE the .desktop files live (accented, like the
     * Wallpaper screen). Doing it before any row guarantees the disclosure line is never the
     * string starved out if the arena ever filled (rows would drop before the subtitle). Terse
     * on purpose (user request): just the ONE drop-in directory, trailing slash, nothing else. */
    const char *subtitle = az_da_intern(".desktop directory: " AZ_DA_DIRS_LINE "/");

    AzDaDir dirs[8];
    int ndirs = az_da_dirs(dirs, 8);

    int n = 0, nseen = 0;
    const char *seen[AZ_DA_MAX_ROWS];

    /* 1. curated seed, in order, ONLY if installed (so the shipped choice stays on top). */
    char seedcopy[512];
    snprintf(seedcopy, sizeof seedcopy, "%s", cat->seed);
    char *save = NULL;
    for (char *t = strtok_r(seedcopy, " ", &save); t; t = strtok_r(NULL, " ", &save)) {
        if (!t[0]) continue;
        if (az_da_installed(dirs, ndirs, t))
            az_da_add_row(&n, seen, &nseen, key, cat->mimes, t);
    }

    /* 2. every OTHER installed .desktop that declares one of this category's MIME types.
     *    Collect names, sort, then add (skip ones already seeded). Non-MIME categories skip. */
    if (cat->mimes[0]) {
        char extras[AZ_DA_MAX_ROWS][AZ_DA_IDLEN];
        int nextra = 0;
        for (int di = 0; di < ndirs && nextra < AZ_DA_MAX_ROWS; di++) {
            DIR *d = opendir(dirs[di]);
            if (!d) continue;
            struct dirent *e;
            while ((e = readdir(d)) && nextra < AZ_DA_MAX_ROWS) {
                const char *nm = e->d_name;
                size_t l = strlen(nm);
                if (l < 8 || strcmp(nm + l - 8, ".desktop") != 0) continue;
                /* already collected (across dirs) or seeded? skip. */
                int dup = 0;
                for (int i = 0; i < nextra; i++) if (!strcmp(extras[i], nm)) { dup = 1; break; }
                if (dup) continue;
                for (int i = 0; i < nseen; i++) if (!strcmp(seen[i], nm)) { dup = 1; break; }
                if (dup) continue;
                char path[AZ_DA_PATHLEN];
                snprintf(path, sizeof path, "%.*s/%.*s",
                         AZ_DA_DIRLEN - 1, dirs[di], AZ_DA_IDLEN - 1, nm);
                if (az_da_declares_mime(path, cat->mimes))
                    snprintf(extras[nextra++], AZ_DA_IDLEN, "%s", nm);
            }
            closedir(d);
        }
        /* sort the discovered extras (simple insertion sort; nextra is small). */
        for (int i = 1; i < nextra; i++) {
            char tmp[AZ_DA_IDLEN];
            snprintf(tmp, sizeof tmp, "%s", extras[i]);
            int j = i - 1;
            while (j >= 0 && strcmp(extras[j], tmp) > 0) {
                snprintf(extras[j+1], AZ_DA_IDLEN, "%s", extras[j]);
                j--;
            }
            snprintf(extras[j+1], AZ_DA_IDLEN, "%s", tmp);
        }
        for (int i = 0; i < nextra; i++)
            az_da_add_row(&n, seen, &nseen, key, cat->mimes, extras[i]);
    }

    g_da_screen.id = g_da_id;
    g_da_screen.title = az_da_label(key);
    g_da_screen.subtitle = subtitle ? subtitle : ".desktop directory: " AZ_DA_DIRS_LINE "/";
    g_da_screen.subtitle_accent = 1;
    g_da_screen.current = az_da_probe(key);
    g_da_screen.rows = g_da_rows;
    g_da_screen.nrows = n;
    return &g_da_screen;
}
