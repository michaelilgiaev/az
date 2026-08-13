/* Az'arch bare-`azarch` TUI (C) -- preview pane. See preview.h. */
/* POSIX APIs (fork/execlp/waitpid/localtime_r) under -std=c11. */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1

#include "preview.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>
#include <fcntl.h>

/* Visible width in cells (UTF-8 code-point starts). Defined below; forward-declared so
 * win_frame() can measure its padded title. */
int vwidth_like(const char *s);

/* --- helpers to emit ANSI straight to stdout (the renderer already flushed) --- */
static void out(const char *s) { ssize_t w = write(STDOUT_FILENO, s, strlen(s)); (void)w; }
static void outf(const char *fmt, ...)
{
    char buf[1024];
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    if (n > 0) { ssize_t w = write(STDOUT_FILENO, buf, (size_t)n); (void)w; }
}
static void mv(int row, int col) { outf("\033[%d;%dH", row, col); }

/* --- kitty graphics --------------------------------------------------------- */
void az_preview_clear(void)
{
    /* Remove all images. Best-effort; if kitten is missing this is a no-op fork. */
    pid_t pid = fork();
    if (pid == 0) {
        int dn = open("/dev/null", O_RDWR);
        if (dn >= 0) { dup2(dn, 0); dup2(dn, 1); dup2(dn, 2); }
        execlp("kitten", "kitten", "icat", "--clear", "--silent", (char *)NULL);
        _exit(127);
    } else if (pid > 0) {
        waitpid(pid, NULL, 0);
    }
}

static int wallpaper_preview(const AzUI *ui, const AzRect *r)
{
    const AzScreen *s = az_ui_screen(ui);
    const AzRow *vis[64];
    int nvis = az_visible_rows(ui, vis, 64);
    (void)s;
    if (ui->sel < 0 || ui->sel >= nvis) return 0;
    const AzRow *row = vis[ui->sel];
    if (!row->preview_arg) return 0;

    char img[512];
    az_wallpaper_image(row->preview_arg, img, sizeof img);
    if (access(img, R_OK) != 0) {
        /* No image on disk: draw a placeholder frame + note. */
        mv(r->row, r->col);
        outf("\033[%sm(preview unavailable: %s)\033[0m", AZ_SGR_DIM, img);
        return 0;
    }

    /* Place the image into the reserved rectangle via kitten icat. Positioning at the
     * rectangle's top-left; kitty scales into WxH cells and centres horizontally. */
    char place[64];
    snprintf(place, sizeof place, "%dx%d@%d,%d", r->w, r->h, r->col - 1, r->row - 1);
    pid_t pid = fork();
    if (pid == 0) {
        int dn = open("/dev/null", O_RDWR);
        if (dn >= 0) { dup2(dn, 0); dup2(dn, 2); }   /* keep stdout: icat writes graphics there */
        execlp("kitten", "kitten", "icat",
               "--clear", "--silent",
               "--transfer-mode", "file",
               "--stdin", "no",
               "--place", place,
               img, (char *)NULL);
        _exit(127);
    } else if (pid > 0) {
        int st = 0;
        waitpid(pid, &st, 0);
        return 1;
    }
    return 0;
}

/* --- theme mock-ups (ANSI) -------------------------------------------------- */
/* Draw a small titled window at (row,col) of size (w,h). Colours flip with `dark`. The
 * frame uses the accent for the title so both apps read as "Az'arch themed". */
static void win_frame(int row, int col, int w, int h, int dark, const char *title)
{
    const char *bg  = dark ? "48;2;30;33;38"   : "48;2;245;246;248";
    const char *fg  = dark ? "38;2;222;228;234" : "38;2;40;44;52";
    const char *bar = dark ? "48;2;44;48;56"    : "48;2;225;228;232";
    /* title bar */
    mv(row, col);
    outf("\033[%s;%sm", bar, AZ_SGR_ACCENT);
    /* a leading dot + title, padded to width */
    char line[256];
    snprintf(line, sizeof line, " \xe2\x97\x8f %s", title);
    int used = vwidth_like(line);
    outf("%s", line);
    for (int i = used; i < w; i++) out(" ");
    out("\033[0m");
    /* body rows */
    for (int y = 1; y < h; y++) {
        mv(row + y, col);
        outf("\033[%s;%sm", bg, fg);
        for (int i = 0; i < w; i++) out(" ");
        out("\033[0m");
    }
}

/* We need a width measure here too; keep a local copy (render.c's is static). */
int vwidth_like(const char *s)
{
    int w = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++)
        if ((*p & 0xC0) != 0x80) w++;
    return w;
}

/* text inside a window body row */
static void win_text(int row, int col, int dark, const char *sgr_extra, const char *s)
{
    const char *bg = dark ? "48;2;30;33;38" : "48;2;245;246;248";
    const char *fg = dark ? "38;2;222;228;234" : "38;2;40;44;52";
    mv(row, col);
    outf("\033[%s;%sm", bg, fg);
    if (sgr_extra) outf("\033[%sm", sgr_extra);
    outf("%s", s);
    out("\033[0m");
}

static int theme_preview(const AzUI *ui, const AzRect *r)
{
    const AzRow *vis[64];
    int nvis = az_visible_rows(ui, vis, 64);
    if (ui->sel < 0 || ui->sel >= nvis) return 0;
    const char *arg = vis[ui->sel]->preview_arg;
    int dark = arg && strcmp(arg, "dark") == 0;

    /* Two side-by-side app windows inside the rectangle: LibreWolf (timedate home page)
     * on the left, Dolphin (file manager) on the right. */
    int gap = 2;
    int ww = (r->w - gap) / 2;
    if (ww < 22) ww = r->w;                 /* too narrow: stack just LibreWolf */
    int wh = r->h;
    int lcol = r->col;
    int rcol = r->col + ww + gap;

    /* --- LibreWolf: the timedate Time+Calendar home page --- */
    win_frame(r->row, lcol, ww, wh, dark, "LibreWolf \xe2\x80\x94 localhost:49154");
    {
        /* current time-ish seed (display only) */
        time_t t = time(NULL);
        struct tm lt;
        localtime_r(&t, &lt);
        int h12 = lt.tm_hour % 12; if (h12 == 0) h12 = 12;
        const char *ampm = lt.tm_hour < 12 ? "AM" : "PM";
        char clock[32];
        snprintf(clock, sizeof clock, "%02d:%02d %s", h12, lt.tm_min, ampm);
        static const char *dow[] = {"Sunday","Monday","Tuesday","Wednesday",
                                    "Thursday","Friday","Saturday"};
        int cy = r->row + 2;
        /* big-ish clock (accent) + day, centred within the window */
        int cx = lcol + (ww - (int)strlen(clock)) / 2;
        win_text(cy, cx < lcol + 1 ? lcol + 1 : cx, dark,
                 AZ_SGR_ACCENT ";" AZ_SGR_BOLD, clock);
        const char *day = dow[lt.tm_wday];
        int dx = lcol + (ww - (int)strlen(day)) / 2;
        win_text(cy + 1, dx < lcol + 1 ? lcol + 1 : dx, dark, AZ_SGR_DIM_ATTR, day);
        /* a tiny calendar strip: Mo Tu We Th Fr Sa Su + a row of numbers, today accent */
        if (wh >= 7) {
            win_text(cy + 3, lcol + 2, dark, AZ_SGR_DIM_ATTR, "Mo Tu We Th Fr Sa Su");
            char nums[64] = {0};
            int start = ((lt.tm_mday - 1) / 7) * 7 + 1;
            for (int d = start; d < start + 7 && d <= 28; d++) {
                char cell[16];
                snprintf(cell, sizeof cell, "%2d ", d & 31);
                strncat(nums, cell, sizeof nums - strlen(nums) - 1);
            }
            win_text(cy + 4, lcol + 2, dark, NULL, nums);
            /* highlight today */
            int idx = (lt.tm_mday - start);
            if (idx >= 0 && idx < 7) {
                char today[16];
                snprintf(today, sizeof today, "%2d", lt.tm_mday & 31);
                win_text(cy + 4, lcol + 2 + idx * 3, dark,
                         AZ_SGR_ACCENT ";" AZ_SGR_BOLD, today);
            }
        }
    }

    /* --- Dolphin: file manager --- */
    if (rcol + ww <= r->col + r->w && ww >= 22) {
        win_frame(r->row, rcol, ww, wh, dark, "Dolphin \xe2\x80\x94 Home");
        /* ASCII-safe leading glyphs (a folder [+] / file [.]) so the columns never
         * misalign the way variable-width emoji would across terminals. */
        const char *entries[] = {"[+] Documents", "[+] Downloads",
                                 "[+] Pictures", "[.] notes.txt"};
        for (int i = 0; i < 4 && (r->row + 2 + i) < r->row + wh; i++) {
            /* first entry "selected" -> accent bar */
            if (i == 0)
                win_text(r->row + 2 + i, rcol + 1, dark, AZ_SGR_ACCENT, entries[i]);
            else
                win_text(r->row + 2 + i, rcol + 1, dark, NULL, entries[i]);
        }
    }

    /* caption under the pane */
    if (r->row + wh + 0 < ui->rows - 3) {
        const char *cap = dark
            ? "Preview: dark. Apps follow it; kitty keeps its own look."
            : "Preview: white. Apps follow it; kitty keeps its own look.";
        int cx = (ui->cols - (int)strlen(cap)) / 2 + 1;
        mv(r->row + wh, cx < 1 ? 1 : cx);
        outf("\033[%sm%s\033[0m", AZ_SGR_DIM, cap);
    }
    return 0;   /* ANSI only -- no kitty image to clear */
}

int az_preview_draw(const AzUI *ui, const AzRect *r)
{
    if (!r || !r->valid) return 0;
    const AzRow *vis[64];
    int nvis = az_visible_rows(ui, vis, 64);
    if (ui->sel < 0 || ui->sel >= nvis) return 0;
    switch (vis[ui->sel]->preview) {
        case AZ_PV_WALLPAPER: return wallpaper_preview(ui, r);
        case AZ_PV_THEME:     return theme_preview(ui, r);
        default:              return 0;
    }
}
