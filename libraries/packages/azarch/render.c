/* Az'arch bare-`azarch` TUI (C) -- the renderer. See render.h.
 *
 * Everything is CENTRED and drawn with raw ANSI into one back buffer that is flushed in a
 * single write(), so a keystroke repaints without flicker. The accent (logo cyan) marks
 * the title, the selection, the "Current" line and the nav keys; the rest stays muted.
 */
#include "render.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* --- a tiny growable output buffer ----------------------------------------- */
typedef struct { char *p; size_t len, cap; } Buf;

static void buf_reserve(Buf *b, size_t extra)
{
    if (b->len + extra + 1 <= b->cap) return;
    size_t cap = b->cap ? b->cap : 4096;
    while (b->len + extra + 1 > cap) cap *= 2;
    b->p = realloc(b->p, cap);
    b->cap = cap;
}
static void buf_add(Buf *b, const char *s, size_t n)
{
    buf_reserve(b, n);
    memcpy(b->p + b->len, s, n);
    b->len += n;
    b->p[b->len] = '\0';
}
static void buf_str(Buf *b, const char *s) { buf_add(b, s, strlen(s)); }
__attribute__((format(printf, 2, 3)))
static void buf_fmt(Buf *b, const char *fmt, ...)
{
    char tmp[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if ((size_t)n < sizeof tmp) { buf_add(b, tmp, (size_t)n); return; }
    buf_reserve(b, (size_t)n);
    va_start(ap, fmt);
    vsnprintf(b->p + b->len, (size_t)n + 1, fmt, ap);
    va_end(ap);
    b->len += (size_t)n;
}

/* Move the cursor to (row, col), 1-based. */
static void at(Buf *b, int row, int col) { buf_fmt(b, "\033[%d;%dH", row, col); }
/* SGR wrappers. */
static void sgr(Buf *b, const char *body) { buf_fmt(b, "\033[%sm", body); }
static void reset(Buf *b) { buf_str(b, "\033[0m"); }

/* Visible width of a UTF-8 string in terminal cells: count code-point starts (skip
 * 0x80..0xBF continuation bytes). Our text is ASCII plus a few boxy/arrow glyphs that are
 * each one cell, so this is exact for what we draw. */
static int vwidth(const char *s)
{
    int w = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++)
        if ((*p & 0xC0) != 0x80) w++;
    return w;
}

/* Starting column to CENTER a string of visible width `w` in `cols`. */
static int center_col(int cols, int w) { int c = (cols - w) / 2 + 1; return c < 1 ? 1 : c; }

/* Put a centred string on `row` with the given SGR body (NULL == plain). */
static void put_center(Buf *b, const AzUI *ui, int row, const char *sgr_body, const char *s)
{
    at(b, row, center_col(ui->cols, vwidth(s)));
    if (sgr_body) sgr(b, sgr_body);
    buf_str(b, s);
    if (sgr_body) reset(b);
}

/* --- model helpers ---------------------------------------------------------- */
const AzScreen *az_ui_screen(const AzUI *ui)
{
    return az_screen_find(ui->stack[ui->depth - 1]);
}

int az_visible_rows(const AzUI *ui, const AzRow **out, int cap)
{
    const AzScreen *s = az_ui_screen(ui);
    int n = 0;
    if (!s) return 0;
    for (int i = 0; i < s->nrows && n < cap; i++)
        if (az_row_matches(&s->rows[i], ui->query))
            out[n++] = &s->rows[i];
    return n;
}

/* --- the navigation line ---------------------------------------------------- */
/* The keys are UPPERCASED and COLOURED (accent); the explanation labels stay as-is and
 * muted, exactly as the spec asks. az_nav_plain gives the same content without colour for
 * the tests. The key GROUPS: movement (WASD / HJKL / arrows, packed) then the verbs. */

/* A run of key glyphs drawn as ONE tight coloured group with NO internal spacing (e.g.
 * "WASD"), then a single trailing space. `keys` is a NUL-terminated array of glyph strings.
 * The spec wants the clusters packed ("WASD HJKL ←↑→↓ move"), not spaced out. */
static void capgroup(Buf *b, const char *const *keys)
{
    sgr(b, AZ_SGR_KEYCAP);
    for (const char *const *k = keys; *k; k++) buf_str(b, *k);
    reset(b);
    buf_str(b, " ");
}

/* a coloured verb: one key-cap + a space + a dim label + trailing gap. */
static void verb(Buf *b, const char *key, const char *label)
{
    sgr(b, AZ_SGR_KEYCAP); buf_str(b, key); reset(b);
    buf_str(b, " ");
    sgr(b, AZ_SGR_DIM); buf_str(b, label); reset(b);
}

static void draw_nav(Buf *b, const AzUI *ui, int row)
{
    /* Build it twice: once to measure the visible width (for centring), once to emit.
     * Simplest correct approach: assemble into a temp Buf, measure, then place. */
    Buf t = {0};
    if (ui->searching) {
        sgr(&t, AZ_SGR_KEYCAP); buf_str(&t, "TYPE"); reset(&t);
        sgr(&t, AZ_SGR_DIM); buf_str(&t, " to filter   "); reset(&t);
        sgr(&t, AZ_SGR_KEYCAP); buf_str(&t, "ENTER"); reset(&t);
        buf_str(&t, "/");
        sgr(&t, AZ_SGR_KEYCAP); buf_str(&t, "ESC"); reset(&t);
        sgr(&t, AZ_SGR_DIM); buf_str(&t, " leave search"); reset(&t);
    } else {
        /* movement: three tight clusters "WASD HJKL ←↑→↓" then the dim "move" label, exactly
         * as the spec spells it. */
        static const char *wasd[]  = {"W", "A", "S", "D", NULL};
        static const char *hjkl[]  = {"H", "J", "K", "L", NULL};
        static const char *arrows[] = {"\xe2\x86\x90", "\xe2\x86\x91",   /* <- ^ */
                                       "\xe2\x86\x92", "\xe2\x86\x93", NULL}; /* -> v */
        capgroup(&t, wasd);
        capgroup(&t, hjkl);
        capgroup(&t, arrows);
        sgr(&t, AZ_SGR_DIM); buf_str(&t, "move"); reset(&t);
        buf_str(&t, "   ");
        verb(&t, "ENTER", "open");
        buf_str(&t, "   ");
        /* ESC is GO BACK everywhere (the newest spec: "ESC is 'go back' not 'quit'"); Q is the
         * one, always-instant QUIT. So the labels are fixed -- no depth-dependent relabelling. */
        verb(&t, "ESC", "back");
        buf_str(&t, "   ");
        verb(&t, "Q", "quit");
        buf_str(&t, "   ");
        verb(&t, "/", "search");
    }
    /* Measure visible width: strip SGR escapes when counting. */
    int w = 0;
    for (const unsigned char *p = (const unsigned char *)t.p; p && *p; ) {
        if (*p == 0x1b) {                 /* skip \033[...m */
            while (*p && *p != 'm') p++;
            if (*p) p++;
            continue;
        }
        if ((*p & 0xC0) != 0x80) w++;
        p++;
    }
    at(b, row, center_col(ui->cols, w));
    buf_add(b, t.p ? t.p : "", t.len);
    free(t.p);
}

const char *az_nav_plain(char *buf, size_t n)
{
    /* Uncoloured content for tests: the packed movement clusters + the verbs, matching what
     * draw_nav renders ("WASD HJKL ←↑→↓ move   ENTER open   ESC back   Q quit   / search"). */
    snprintf(buf, n,
             "WASD HJKL \xe2\x86\x90\xe2\x86\x91\xe2\x86\x92\xe2\x86\x93 "
             "move   ENTER open   ESC back   Q quit   / search");
    return buf;
}

/* --- the frame -------------------------------------------------------------- */
void az_render(const AzUI *ui, AzRect *preview_out)
{
    if (preview_out) preview_out->valid = 0;
    Buf b = {0};
    /* Hide the cursor (re-asserted every frame so it can NEVER reappear blinking after an
     * apply/preview subprocess re-enabled it), then clear + home. We repaint the whole screen
     * each frame (it is small) so there are no stale cells; the single flush is flicker-free. */
    buf_str(&b, "\033[?25l\033[2J\033[H");

    const AzScreen *scr = az_ui_screen(ui);
    const AzRow *vis[64];
    int nvis = az_visible_rows(ui, vis, 64);
    /* Clamp the selection to a valid visible index BOTH ways. The input loop already keeps
     * ui->sel in range, but clamping here too means a future change there can never turn a
     * stale/negative index into an out-of-bounds vis[] read during draw. */
    int sel = ui->sel;
    if (sel < 0) sel = 0;
    if (sel >= nvis) sel = nvis > 0 ? nvis - 1 : 0;

    int rows = ui->rows, cols = ui->cols;

    /* Row layout (all centred). Top margin scales a little with height. */
    int y = rows >= 24 ? 2 : 1;

    /* 1. breadcrumb / title (accent, bold). "Settings / Network / Firewall". */
    {
        char crumb[256] = {0};
        for (int i = 0; i < ui->depth; i++) {
            const AzScreen *s = az_screen_find(ui->stack[i]);
            if (i) strncat(crumb, "  \xe2\x80\xba  ", sizeof crumb - strlen(crumb) - 1); /* › */
            if (s) strncat(crumb, s->title, sizeof crumb - strlen(crumb) - 1);
        }
        put_center(&b, ui, y, AZ_SGR_ACCENT ";" AZ_SGR_BOLD, crumb);
    }
    y += 2;

    /* 2. search box (centred, accent border). A rounded box with a `/` glyph. */
    {
        int inner = 30;                       /* fixed inner width for a stable, tidy box */
        int boxw = inner + 4;                 /* "│ " + inner + " │" */
        int col = center_col(ui->cols, boxw);
        const char *hbar = "\xe2\x94\x80";    /* ─ */
        /* top */
        at(&b, y, col);
        sgr(&b, ui->searching ? AZ_SGR_ACCENT : AZ_SGR_DIM);
        buf_str(&b, "\xe2\x95\xad");          /* ╭ */
        for (int i = 0; i < boxw - 2; i++) buf_str(&b, hbar);
        buf_str(&b, "\xe2\x95\xae");          /* ╮ */
        reset(&b);
        /* middle: "│ query_ …padding… │". No leading "/" glyph inside the box -- the spec
         * says leave it as just "search" (the "/" still lives on the nav line as the key). */
        at(&b, y + 1, col);
        sgr(&b, ui->searching ? AZ_SGR_ACCENT : AZ_SGR_DIM);
        buf_str(&b, "\xe2\x94\x82 ");         /* │ */
        reset(&b);
        /* query text (truncate to fit) + a caret when focused */
        char shown[sizeof ui->query];
        snprintf(shown, sizeof shown, "%s", ui->query);
        int avail = inner;
        int qw = vwidth(shown);
        if (qw > avail) { shown[avail] = '\0'; qw = avail; }
        if (ui->query[0]) { sgr(&b, AZ_SGR_TEXT); buf_str(&b, shown); reset(&b); }
        else if (!ui->searching) { sgr(&b, AZ_SGR_DIM); buf_str(&b, "search"); reset(&b); qw = 6; }
        if (ui->searching) { sgr(&b, AZ_SGR_ACCENT); buf_str(&b, "\xe2\x96\x8f"); reset(&b); qw += 1; } /* ▏ caret */
        for (int i = qw; i < avail; i++) buf_str(&b, " ");
        sgr(&b, ui->searching ? AZ_SGR_ACCENT : AZ_SGR_DIM);
        buf_str(&b, " \xe2\x94\x82");         /* │ */
        reset(&b);
        /* bottom */
        at(&b, y + 2, col);
        sgr(&b, ui->searching ? AZ_SGR_ACCENT : AZ_SGR_DIM);
        buf_str(&b, "\xe2\x95\xb0");          /* ╰ */
        for (int i = 0; i < boxw - 2; i++) buf_str(&b, hbar);
        buf_str(&b, "\xe2\x95\xaf");          /* ╯ */
        reset(&b);
    }
    y += 4;

    /* 3. subtitle (dim, centred): the wallpaper dir path, kitty disclaimer, etc. */
    if (scr && scr->subtitle && scr->subtitle[0]) {
        put_center(&b, ui, y, AZ_SGR_DIM, scr->subtitle);
        y += 2;
    }

    /* 4. "Current: X" line (accent) -- Theme/Wallpaper want the current state shown ONCE at
     * the top. It comes from the screen's own `current` probe (NOT a per-row status), so the
     * rows below stay label-only with no "white"/"years" echo trailing each option. */
    if (scr && scr->current) {
        char sb[128];
        const char *cur = az_status_cached(scr->current, sb, sizeof sb);
        char line[160];
        snprintf(line, sizeof line, "Current: %s", cur ? cur : "");
        put_center(&b, ui, y, AZ_SGR_ACCENT ";" AZ_SGR_BOLD, line);
        y += 2;
    }

    /* 5. the rows, centred as a BLOCK: compute the widest "label   status" then place the
     * block so its left edge is centred. Selected row: accent chevron + accent label. */
    int list_top = y;
    if (nvis == 0) {
        put_center(&b, ui, y, AZ_SGR_DIM, "(nothing matches your search)");
        y += 1;
    } else {
        int label_w = 0, status_w = 0;
        char sbuf[128];
        for (int i = 0; i < nvis; i++) {
            int lw = vwidth(vis[i]->label);
            if (lw > label_w) label_w = lw;
            if (vis[i]->status) {
                const char *st = az_status_cached(vis[i]->status, sbuf, sizeof sbuf);
                int sw = vwidth(st ? st : "");
                if (sw > status_w) status_w = sw;
            }
        }
        int gap = 3;
        int blockw = 2 + label_w + (status_w ? gap + status_w : 0); /* "› " + label + gap + status */
        int col = center_col(ui->cols, blockw);
        int maxrows = rows - list_top - 6;      /* leave room for hint + nav */
        if (maxrows < 1) maxrows = 1;
        for (int i = 0; i < nvis && i < maxrows; i++) {
            int selected = (i == sel);
            at(&b, list_top + i, col);
            if (selected) { sgr(&b, AZ_SGR_ACCENT ";" AZ_SGR_BOLD); buf_str(&b, "\xe2\x80\xba "); } /* › */
            else buf_str(&b, "  ");
            /* label */
            if (selected) sgr(&b, AZ_SGR_ACCENT ";" AZ_SGR_BOLD);
            else sgr(&b, AZ_SGR_TEXT);
            buf_str(&b, vis[i]->label);
            int pad = label_w - vwidth(vis[i]->label);
            for (int k = 0; k < pad; k++) buf_str(&b, " ");
            reset(&b);
            /* status */
            if (vis[i]->status) {
                const char *st = az_status_cached(vis[i]->status, sbuf, sizeof sbuf);
                for (int k = 0; k < gap; k++) buf_str(&b, " ");
                sgr(&b, selected ? AZ_SGR_ACCENT : AZ_SGR_DIM);
                buf_str(&b, st ? st : "");
                reset(&b);
            }
        }
        y = list_top + (nvis < maxrows ? nvis : maxrows);
    }

    /* 6. reserve a PREVIEW rectangle for the hovered row (below the list, centred). The
     * renderer only reserves the space + draws a faint frame label; preview.c places the
     * kitty image inside it. */
    if (nvis > 0 && sel < nvis && vis[sel]->preview != AZ_PV_NONE) {
        int pv_top = y + 1;
        int pv_h = rows - pv_top - 3;         /* down to just above the nav line */
        if (pv_h > 12) pv_h = 12;
        int pv_w = ui->cols > 72 ? 64 : ui->cols - 6;
        if (pv_h >= 4 && pv_w >= 20 && preview_out) {
            preview_out->row = pv_top;
            preview_out->col = center_col(ui->cols, pv_w);
            preview_out->w = pv_w;
            preview_out->h = pv_h;
            preview_out->valid = 1;
        }
        y = pv_top + (pv_h >= 4 ? pv_h : 0);
    }

    /* 7. hovered row hint (dim, centred), just above the message/nav. */
    if (nvis > 0 && sel < nvis && vis[sel]->hint && vis[sel]->hint[0]) {
        put_center(&b, ui, rows - 3, AZ_SGR_DIM, vis[sel]->hint);
    }

    /* 8. message line (last action result, accent) OR blank; then the nav line. */
    if (ui->message[0]) {
        put_center(&b, ui, rows - 2, AZ_SGR_ACCENT, ui->message);
    }
    draw_nav(&b, ui, rows - 1);

    /* Park the cursor in the BOTTOM-RIGHT corner and hide it again at the very end of the
     * buffer. main.c re-asserts this after the kitty preview (which re-shows the cursor at
     * home -- the "cursor at the top-left" artifact); doing it here too means a frame with no
     * preview is already clean. Bottom-right (not home) keeps any cursor a terminal insists on
     * showing out of the way of the centred UI. */
    at(&b, rows > 0 ? rows : 1, cols > 0 ? cols : 1);
    buf_str(&b, "\033[?25l");

    if (b.p) { ssize_t w = write(STDOUT_FILENO, b.p, b.len); (void)w; }
    free(b.p);
}
