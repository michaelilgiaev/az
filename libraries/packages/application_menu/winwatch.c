/* Az'arch application menu (C port) -- system-wide "app opened" detection.
 * One-to-one port of winwatch.py. See winwatch.h. */
#include "winwatch.h"

#include <string.h>
#include <stdlib.h>
#include <glib.h>

#define POLL_MS         400
#define PID_BURST_TICKS 8

static const char *SKIP_TYPES[] = {
    "_NET_WM_WINDOW_TYPE_DESKTOP", "_NET_WM_WINDOW_TYPE_DOCK",
    "_NET_WM_WINDOW_TYPE_TOOLBAR", "_NET_WM_WINDOW_TYPE_MENU",
    "_NET_WM_WINDOW_TYPE_UTILITY", "_NET_WM_WINDOW_TYPE_SPLASH",
    "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU", "_NET_WM_WINDOW_TYPE_POPUP_MENU",
    "_NET_WM_WINDOW_TYPE_TOOLTIP", "_NET_WM_WINDOW_TYPE_NOTIFICATION",
    "_NET_WM_WINDOW_TYPE_COMBO", "_NET_WM_WINDOW_TYPE_DND", NULL
};

/* ---- desktop index (window identity -> desktop id) ---------------------- */
typedef struct {
    GHashTable *by_startup_wmclass;  /* casefolded -> did (both owned) */
    GHashTable *by_exec_bin;
    GHashTable *by_id_stem;
} DesktopIndex;

/* Basename of the real launched binary from an Exec argv[0], skipping a leading
 * env/wrapper (env FOO=1 kitty). Returns newly-allocated or NULL. */
static char *exec_binary(char **argv) {
    if (!argv) return NULL;
    int idx = 0;
    while (argv[idx]) {
        char *base = g_path_get_basename(argv[idx]);
        gboolean is_env = (strcmp(base, "env") == 0) || (strchr(argv[idx], '=') != NULL);
        g_free(base);
        if (is_env) { idx++; continue; }
        break;
    }
    if (!argv[idx]) return NULL;
    char *b = g_path_get_basename(argv[idx]);
    if (!b[0]) { g_free(b); return NULL; }
    return b;
}

static void idx_set_default(GHashTable *t, const char *key_cf, const char *did) {
    if (!g_hash_table_contains(t, key_cf))
        g_hash_table_insert(t, g_strdup(key_cf), g_strdup(did));
}

static DesktopIndex *index_build(GPtrArray *entries) {
    DesktopIndex *ix = g_new0(DesktopIndex, 1);
    ix->by_startup_wmclass = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_free);
    ix->by_exec_bin        = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_free);
    ix->by_id_stem         = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_free);

    for (guint i = 0; i < entries->len; i++) {
        AzAppEntry *e = g_ptr_array_index(entries, i);
        const char *did = e->desktop_id;
        if (e->startup_wmclass && e->startup_wmclass[0]) {
            char *cf = g_utf8_casefold(e->startup_wmclass, -1);
            idx_set_default(ix->by_startup_wmclass, cf, did);
            g_free(cf);
        }
        char *eb = exec_binary(e->exec_argv);
        if (eb) {
            char *cf = g_utf8_casefold(eb, -1);
            idx_set_default(ix->by_exec_bin, cf, did);
            g_free(cf);
            g_free(eb);
        }
        char *stem;
        if (g_str_has_suffix(did, ".desktop"))
            stem = g_strndup(did, strlen(did) - 8);
        else
            stem = g_strdup(did);
        char *stem_cf = g_utf8_casefold(stem, -1);
        idx_set_default(ix->by_id_stem, stem_cf, did);
        g_free(stem_cf);
        char *dot = strrchr(stem, '.');
        if (dot) {
            char *last_cf = g_utf8_casefold(dot + 1, -1);
            idx_set_default(ix->by_id_stem, last_cf, did);
            g_free(last_cf);
        }
        g_free(stem);
    }
    return ix;
}

static void index_free(DesktopIndex *ix) {
    if (!ix) return;
    g_hash_table_destroy(ix->by_startup_wmclass);
    g_hash_table_destroy(ix->by_exec_bin);
    g_hash_table_destroy(ix->by_id_stem);
    g_free(ix);
}

static char *proc_exe_basename(int pid) {
    char *link = g_strdup_printf("/proc/%d/exe", pid);
    char *target = g_file_read_link(link, NULL);
    g_free(link);
    if (!target) return NULL;
    char *base = g_path_get_basename(target);
    g_free(target);
    if (g_str_has_suffix(base, " (deleted)"))
        base[strlen(base) - strlen(" (deleted)")] = '\0';
    if (!base[0]) { g_free(base); return NULL; }
    return base;
}

static GPtrArray *proc_cmdline_bins(int pid) {
    GPtrArray *out = g_ptr_array_new_with_free_func(g_free);
    char *path = g_strdup_printf("/proc/%d/cmdline", pid);
    char *raw = NULL; gsize len = 0;
    if (g_file_get_contents(path, &raw, &len, NULL)) {
        gsize start = 0; int i = 0;
        for (gsize p = 0; p <= len && i < 4; p++) {
            if (p == len || raw[p] == '\0') {
                if (p > start) {
                    char *tok = g_strndup(raw + start, p - start);
                    char *base = g_path_get_basename(tok);
                    if (base[0] && (i == 0 || strchr(tok, '/')))
                        g_ptr_array_add(out, g_strdup(base));
                    g_free(base); g_free(tok);
                    i++;
                }
                start = p + 1;
            }
        }
    }
    g_free(raw); g_free(path);
    return out;
}

static const char *index_resolve(DesktopIndex *ix, GPtrArray *wm_classes, int pid) {
    for (guint i = 0; i < wm_classes->len; i++) {
        char *cf = g_utf8_casefold(g_ptr_array_index(wm_classes, i), -1);
        const char *hit = g_hash_table_lookup(ix->by_startup_wmclass, cf);
        g_free(cf);
        if (hit) return hit;
    }
    for (guint i = 0; i < wm_classes->len; i++) {
        char *cf = g_utf8_casefold(g_ptr_array_index(wm_classes, i), -1);
        const char *hit = g_hash_table_lookup(ix->by_exec_bin, cf);
        if (!hit) hit = g_hash_table_lookup(ix->by_id_stem, cf);
        g_free(cf);
        if (hit) return hit;
    }
    if (pid > 0) {
        char *base = proc_exe_basename(pid);
        if (base) {
            char *cf = g_utf8_casefold(base, -1);
            const char *hit = g_hash_table_lookup(ix->by_exec_bin, cf);
            if (!hit) hit = g_hash_table_lookup(ix->by_id_stem, cf);
            g_free(cf); g_free(base);
            if (hit) return hit;
        }
        GPtrArray *bins = proc_cmdline_bins(pid);
        const char *hit = NULL;
        for (guint i = 0; i < bins->len && !hit; i++) {
            char *cf = g_utf8_casefold(g_ptr_array_index(bins, i), -1);
            hit = g_hash_table_lookup(ix->by_exec_bin, cf);
            if (!hit) hit = g_hash_table_lookup(ix->by_id_stem, cf);
            g_free(cf);
        }
        g_ptr_array_free(bins, TRUE);
        if (hit) return hit;
    }
    return NULL;
}

/* ---- xprop helpers ------------------------------------------------------ */
static char *run_xprop(char **args) {
    char *out = NULL;
    int status = 0;
    if (g_spawn_sync(NULL, args, NULL,
                     G_SPAWN_SEARCH_PATH | G_SPAWN_STDERR_TO_DEV_NULL,
                     NULL, NULL, &out, NULL, &status, NULL)) {
        return out ? out : g_strdup("");
    }
    g_free(out);
    return g_strdup("");
}

static GPtrArray *client_list(void) {
    GPtrArray *ids = g_ptr_array_new_with_free_func(g_free);
    char *args[] = { "xprop", "-root", "_NET_CLIENT_LIST", NULL };
    char *out = run_xprop(args);
    char *hash = strchr(out, '#');
    if (hash) {
        char **parts = g_strsplit(hash + 1, ",", -1);
        for (int i = 0; parts[i]; i++) {
            char *w = g_strstrip(g_strdup(parts[i]));
            if (w[0]) g_ptr_array_add(ids, w);
            else g_free(w);
        }
        g_strfreev(parts);
    }
    g_free(out);
    return ids;
}

/* ---- watcher ------------------------------------------------------------ */
struct AzWatcher {
    AzUsage          *usage;
    AzEntriesProvider provider;
    gpointer          user;
    int               own_pid;
    DesktopIndex     *index;
    GHashTable       *seen;         /* char* win id -> 1 */
    GHashTable       *pid_last_tick;/* int pid -> int tick */
    int               tick;
    guint             source_id;
};

static DesktopIndex *watcher_index(AzWatcher *w) {
    if (!w->index) {
        GPtrArray *entries = w->provider(w->user);
        w->index = index_build(entries);
        g_ptr_array_free(entries, TRUE);
    }
    return w->index;
}

void az_watcher_refresh_index(AzWatcher *w) {
    if (w->index) { index_free(w->index); w->index = NULL; }
}

static void parse_props(const char *out, GPtrArray *wm_classes, int *pid,
                        GPtrArray *types) {
    char **lines = g_strsplit(out, "\n", -1);
    for (int i = 0; lines[i]; i++) {
        const char *ln = lines[i];
        if (g_str_has_prefix(ln, "WM_CLASS")) {
            const char *eq = strchr(ln, '=');
            if (eq) {
                char **chunks = g_strsplit(eq + 1, ",", -1);
                for (int k = 0; chunks[k]; k++) {
                    char *c = g_strstrip(g_strdup(chunks[k]));
                    char *s = c;
                    if (*s == '"') s++;
                    char *end = s + strlen(s);
                    while (end > s && (end[-1] == '"' || g_ascii_isspace(end[-1]))) end--;
                    *end = '\0';
                    if (*s) g_ptr_array_add(wm_classes, g_strdup(s));
                    g_free(c);
                }
                g_strfreev(chunks);
            }
        } else if (g_str_has_prefix(ln, "_NET_WM_PID")) {
            const char *eq = strchr(ln, '=');
            if (eq) *pid = atoi(eq + 1);
        } else if (g_str_has_prefix(ln, "_NET_WM_WINDOW_TYPE")) {
            const char *eq = strchr(ln, '=');
            if (eq) {
                char **ts = g_strsplit(eq + 1, ",", -1);
                for (int k = 0; ts[k]; k++) {
                    char *t = g_strstrip(g_strdup(ts[k]));
                    if (t[0]) g_ptr_array_add(types, t);
                    else g_free(t);
                }
                g_strfreev(ts);
            }
        }
    }
    g_strfreev(lines);
}

static gboolean all_skippable(GPtrArray *types) {
    if (types->len == 0) return FALSE;
    for (guint i = 0; i < types->len; i++) {
        const char *t = g_ptr_array_index(types, i);
        gboolean skip = FALSE;
        for (int k = 0; SKIP_TYPES[k]; k++)
            if (strcmp(t, SKIP_TYPES[k]) == 0) { skip = TRUE; break; }
        if (!skip) return FALSE;
    }
    return TRUE;
}

static void consider(AzWatcher *w, const char *win, DesktopIndex *ix) {
    char *args[] = { "xprop", "-id", (char *)win, "WM_CLASS",
                     "_NET_WM_PID", "_NET_WM_WINDOW_TYPE", "WM_COMMAND", NULL };
    char *out = run_xprop(args);

    GPtrArray *wm_classes = g_ptr_array_new_with_free_func(g_free);
    GPtrArray *types = g_ptr_array_new_with_free_func(g_free);
    int pid = 0;
    parse_props(out, wm_classes, &pid, types);
    g_free(out);

    if (all_skippable(types)) goto done;
    if (pid > 0 && pid == w->own_pid) goto done;

    const char *did = index_resolve(ix, wm_classes, pid);
    if (!did) goto done;

    if (pid > 0) {
        gpointer v;
        if (g_hash_table_lookup_extended(w->pid_last_tick, GINT_TO_POINTER(pid),
                                         NULL, &v)) {
            int last = GPOINTER_TO_INT(v);
            if (w->tick - last <= PID_BURST_TICKS) {
                g_hash_table_insert(w->pid_last_tick, GINT_TO_POINTER(pid),
                                    GINT_TO_POINTER(w->tick));
                goto done;
            }
        }
        g_hash_table_insert(w->pid_last_tick, GINT_TO_POINTER(pid),
                            GINT_TO_POINTER(w->tick));
    }
    az_usage_record(w->usage, did);

done:
    g_ptr_array_free(wm_classes, TRUE);
    g_ptr_array_free(types, TRUE);
}

static void scan_once(AzWatcher *w) {
    GPtrArray *current = client_list();
    if (current->len == 0) { g_ptr_array_free(current, TRUE); return; }

    GHashTable *cur_set = g_hash_table_new(g_str_hash, g_str_equal);
    for (guint i = 0; i < current->len; i++)
        g_hash_table_add(cur_set, g_ptr_array_index(current, i));

    /* Forget closed windows so a reused id counts as fresh. */
    GHashTableIter it; gpointer k;
    GPtrArray *drop = g_ptr_array_new_with_free_func(g_free);
    g_hash_table_iter_init(&it, w->seen);
    while (g_hash_table_iter_next(&it, &k, NULL))
        if (!g_hash_table_contains(cur_set, k))
            g_ptr_array_add(drop, g_strdup((char *)k));
    for (guint i = 0; i < drop->len; i++)
        g_hash_table_remove(w->seen, g_ptr_array_index(drop, i));
    g_ptr_array_free(drop, TRUE);

    GPtrArray *new_ids = g_ptr_array_new();
    for (guint i = 0; i < current->len; i++) {
        char *win = g_ptr_array_index(current, i);
        if (!g_hash_table_contains(w->seen, win))
            g_ptr_array_add(new_ids, win);
    }
    if (new_ids->len > 0) {
        DesktopIndex *ix = watcher_index(w);
        for (guint i = 0; i < new_ids->len; i++) {
            char *win = g_ptr_array_index(new_ids, i);
            g_hash_table_add(w->seen, g_strdup(win));
            consider(w, win, ix);
        }
    }
    g_ptr_array_free(new_ids, TRUE);
    g_hash_table_destroy(cur_set);
    g_ptr_array_free(current, TRUE);
}

static gboolean poll_cb(gpointer data) {
    AzWatcher *w = data;
    w->tick++;
    scan_once(w);
    return G_SOURCE_CONTINUE;
}

AzWatcher *az_watcher_new(AzUsage *usage, AzEntriesProvider provider,
                          gpointer user, int own_pid) {
    AzWatcher *w = g_new0(AzWatcher, 1);
    w->usage = usage;
    w->provider = provider;
    w->user = user;
    w->own_pid = own_pid;
    w->seen = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
    w->pid_last_tick = g_hash_table_new(g_direct_hash, g_direct_equal);
    return w;
}

void az_watcher_start(AzWatcher *w) {
    GPtrArray *cur = client_list();
    for (guint i = 0; i < cur->len; i++)
        g_hash_table_add(w->seen, g_strdup(g_ptr_array_index(cur, i)));
    g_ptr_array_free(cur, TRUE);
    w->source_id = g_timeout_add(POLL_MS, poll_cb, w);
}

void az_watcher_stop(AzWatcher *w) {
    if (w->source_id) { g_source_remove(w->source_id); w->source_id = 0; }
}

void az_watcher_free(AzWatcher *w) {
    if (!w) return;
    az_watcher_stop(w);
    if (w->index) index_free(w->index);
    g_hash_table_destroy(w->seen);
    g_hash_table_destroy(w->pid_last_tick);
    g_free(w);
}
