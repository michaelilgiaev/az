/* Az'arch application menu (C port) -- application discovery + category typing.
 *
 * Port of apps.py. Scans freedesktop .desktop files and turns each visible one
 * into an AzAppEntry the menu renders: display Name, Exec argv (field codes
 * stripped), Icon name, a human "type" label derived from Categories=, the
 * .desktop id (basename), and StartupWMClass.
 */
#ifndef AZ_APPS_H
#define AZ_APPS_H

#include <glib.h>

typedef struct {
    char  *name;            /* display Name */
    char  *type_label;      /* small subtitle, e.g. "Web Browser" */
    char **exec_argv;       /* NULL-terminated, field codes stripped */
    char  *icon;            /* Icon= value (name or path), may be "" */
    char  *comment;         /* Comment= */
    char  *desktop_id;      /* basename, de-dupe key */
    char  *startup_wmclass; /* StartupWMClass= */
} AzAppEntry;

/* Free one entry's owned strings/arrays and the entry itself. */
void az_app_entry_free(AzAppEntry *e);

/* Human "type" for an app given its Categories tokens (NULL-terminated array).
 * Prefers the most specific Additional category, then a Main category, then a
 * generic fallback. Returns a newly-allocated string (never NULL). */
char *az_category_type(char **categories);

/* Return a GPtrArray* of AzAppEntry*, de-duplicated by .desktop id and sorted
 * A->Z by casefolded display name. Entries in the hidden-id set are skipped.
 * Pass NULL for dirs to use the standard XDG application dirs. */
GPtrArray *az_scan_applications(void);

/* Whether a .desktop basename is hidden from OUR menu (still installed). */
gboolean az_is_hidden_desktop_id(const char *desktop_id);

#endif /* AZ_APPS_H */
