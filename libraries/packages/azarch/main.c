/* Az'arch bare-`azarch` TUI (C) -- the driver (raw termios, input loop, actions).
 *
 * This is what `azarch` (no arguments) runs: a full-screen, CENTRED, coloured settings UI
 * for the three things a fresh machine needs -- Theme, Wallpaper, Network. It is C over
 * raw ANSI + termios so it feels INSTANT: a keystroke is a read() + a diff + one write(),
 * never an interpreter round-trip.
 *
 * NAVIGATION (per the spec): arrow keys, WASD, and HJKL all move; Enter opens/applies; Esc
 * (or the movement "back") goes up a screen; `/` focuses the search box. The nav keys are
 * uppercased + coloured by the renderer.
 *
 * ACTIONS shell out to the installed `azarch` subcommands (theme/wallpaper/network). Since
 * some prompt for a sudo password or print output, we RESTORE the terminal (cooked mode,
 * normal screen) around the command so its I/O is visible, then re-enter raw mode and show
 * a one-line result. So the UI adds navigation + previews, not new system behaviour.
 *
 * If stdin/stdout is not a terminal, main() prints a short pointer to the subcommands and
 * exits 0 (so `azarch </dev/null` or a pipe never breaks) -- mirroring the old Python UI.
 */
/* POSIX APIs (termios, sigaction, fork, ioctl) under -std=c11. */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1

#include "render.h"
#include "preview.h"

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/wait.h>

static struct termios g_orig_termios;
static int g_raw = 0;
static volatile sig_atomic_t g_resized = 0;
static int g_had_image = 0;      /* did the last frame place a kitty image? */

/* --- terminal mode ---------------------------------------------------------- */
/* write a NUL-terminated control string (length computed, so it can never drift). */
static void wr(const char *s) { ssize_t w = write(STDOUT_FILENO, s, strlen(s)); (void)w; }

static void enter_raw(void)
{
    if (g_raw) return;
    struct termios t = g_orig_termios;
    t.c_lflag &= ~(ECHO | ICANON | ISIG | IEXTEN);
    t.c_iflag &= ~(IXON | ICRNL | BRKINT | INPCK | ISTRIP);
    t.c_oflag &= ~(OPOST);
    t.c_cc[VMIN] = 1;
    t.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &t);
    /* Alt screen ON, then WIPE it (2J) and the scrollback (3J) and home the cursor, then
     * hide the cursor. The 2J+3J is what makes launching `azarch` leave NO trace of whatever
     * was on the terminal before -- the previous CLI output is gone, not just scrolled. */
    wr("\033[?1049h\033[2J\033[3J\033[H\033[?25l");
    g_raw = 1;
}
static void leave_raw(void)
{
    if (!g_raw) return;
    /* Clear any kitty image, wipe the alt screen so nothing flashes as we drop back, SHOW the
     * cursor again, leave the alt screen, restore cooked mode. */
    az_preview_clear();
    wr("\033[2J\033[H\033[?25h\033[?1049l");
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &g_orig_termios);
    g_raw = 0;
}
static void on_exit_restore(void) { leave_raw(); }
static void on_signal(int sig) { leave_raw(); signal(sig, SIG_DFL); raise(sig); }
static void on_winch(int sig) { (void)sig; g_resized = 1; }

/* current terminal size (fallback 80x24) */
static void term_size(int *rows, int *cols)
{
    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_row && ws.ws_col) {
        *rows = ws.ws_row; *cols = ws.ws_col;
    } else { *rows = 24; *cols = 80; }
}

/* --- input: read one logical key ------------------------------------------- */
enum {
    K_NONE = 0, K_UP = 256, K_DOWN, K_LEFT, K_RIGHT,
    K_ENTER, K_ESC, K_BACKSPACE, K_RESIZE
};

/* Read a key, decoding arrow escape sequences. Returns a K_* code or a byte (>=0). On
 * SIGWINCH mid-read it returns K_RESIZE. */
static int read_key(void)
{
    unsigned char c;
    ssize_t r = read(STDIN_FILENO, &c, 1);
    if (r <= 0) {
        if (errno == EINTR && g_resized) { g_resized = 0; return K_RESIZE; }
        if (r == 0) return K_ESC;    /* EOF -> treat as quit */
        return K_NONE;
    }
    if (c == '\r' || c == '\n') return K_ENTER;
    if (c == 127 || c == 8) return K_BACKSPACE;
    if (c == 27) {
        /* Could be a bare ESC or a CSI sequence. Peek with a short non-blocking read. */
        unsigned char seq[2];
        struct termios t; tcgetattr(STDIN_FILENO, &t);
        cc_t vmin = t.c_cc[VMIN], vtime = t.c_cc[VTIME];
        t.c_cc[VMIN] = 0; t.c_cc[VTIME] = 1;   /* 100ms */
        tcsetattr(STDIN_FILENO, TCSANOW, &t);
        ssize_t n0 = read(STDIN_FILENO, &seq[0], 1);
        int key = K_ESC;
        if (n0 == 1 && (seq[0] == '[' || seq[0] == 'O')) {
            ssize_t n1 = read(STDIN_FILENO, &seq[1], 1);
            if (n1 == 1) {
                switch (seq[1]) {
                    case 'A': key = K_UP; break;
                    case 'B': key = K_DOWN; break;
                    case 'C': key = K_RIGHT; break;
                    case 'D': key = K_LEFT; break;
                    default:  key = K_ESC; break;
                }
            }
        }
        t.c_cc[VMIN] = vmin; t.c_cc[VTIME] = vtime;
        tcsetattr(STDIN_FILENO, TCSANOW, &t);
        return key;
    }
    return c;
}

/* --- run an apply command, VISIBLY (terminal restored) --------------------- */
/* For applies that may prompt (sudo password) or print output worth seeing -- network /
 * firewall. We drop out of the alt screen so the command's I/O is on the real terminal, run
 * it, wait for a key, then come back and report. */
static void run_apply_visible(AzUI *ui, const char *cmdline)
{
    az_preview_clear();
    wr("\033[?25h\033[?1049l");
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &g_orig_termios);
    g_raw = 0;

    printf("\n\033[%sm$ %s\033[0m\n", AZ_SGR_DIM, cmdline);
    fflush(stdout);
    int rc = -1;
    pid_t pid = fork();
    if (pid == 0) {
        execl("/bin/sh", "sh", "-c", cmdline, (char *)NULL);
        _exit(127);
    } else if (pid > 0) {
        int st = 0; waitpid(pid, &st, 0);
        rc = WIFEXITED(st) ? WEXITSTATUS(st) : -1;
    }
    printf("\n\033[%sm[ Press any key to return ]\033[0m", AZ_SGR_DIM);
    fflush(stdout);

    enter_raw();
    /* consume the acknowledgement key */
    (void)read_key();

    snprintf(ui->message, sizeof ui->message, "%s",
             rc == 0 ? "Done." : "That reported an error (see above).");
}

/* --- run an apply command, SILENTLY (stay on the UI) ----------------------- */
/* For applies that never need a tty -- theme, wallpaper (they configure the user session, no
 * sudo). We run the command with stdin/stdout/stderr on /dev/null WITHOUT leaving the alt
 * screen, so NO raw CLI text ever flashes over the UI; the next frame just redraws with the
 * new "Current:" state and a one-line result. This is the fix for the "changing themes is
 * buggy, CLI text appears" report -- the toggle now stays entirely inside the UI. */
static void run_apply_quiet(AzUI *ui, const char *cmdline)
{
    int rc = -1;
    pid_t pid = fork();
    if (pid == 0) {
        int dn = open("/dev/null", O_RDWR);
        if (dn >= 0) { dup2(dn, 0); dup2(dn, 1); dup2(dn, 2); if (dn > 2) close(dn); }
        execl("/bin/sh", "sh", "-c", cmdline, (char *)NULL);
        _exit(127);
    } else if (pid > 0) {
        int st = 0; waitpid(pid, &st, 0);
        rc = WIFEXITED(st) ? WEXITSTATUS(st) : -1;
    }
    snprintf(ui->message, sizeof ui->message, "%s",
             rc == 0 ? "Done." : "That reported an error.");
}

/* --- navigation ------------------------------------------------------------- */
static void go_back(AzUI *ui)
{
    if (ui->query[0]) { ui->query[0] = '\0'; ui->sel = 0; return; }
    if (ui->depth > 1) { ui->depth--; ui->sel = 0; ui->message[0] = '\0'; }
}

static void activate(AzUI *ui)
{
    const AzRow *vis[64];
    int nvis = az_visible_rows(ui, vis, 64);
    if (ui->sel < 0 || ui->sel >= nvis) return;
    const AzRow *row = vis[ui->sel];
    if (row->kind == AZ_ACT_SCREEN) {
        if (az_screen_find(row->target) && ui->depth < 15) {
            ui->stack[ui->depth++] = row->target;
            ui->sel = 0; ui->query[0] = '\0'; ui->message[0] = '\0';
        }
    } else {
        if (row->quiet) run_apply_quiet(ui, row->target);
        else            run_apply_visible(ui, row->target);
    }
}

/* search-box editing; returns 0 to quit (never happens here) */
static void search_key(AzUI *ui, int k)
{
    if (k == K_ENTER || k == K_ESC) { ui->searching = 0; return; }
    if (k == K_BACKSPACE) {
        size_t l = strlen(ui->query);
        if (l) ui->query[l - 1] = '\0';
        ui->sel = 0;
        return;
    }
    if (k >= 32 && k < 127) {
        size_t l = strlen(ui->query);
        if (l < sizeof ui->query - 1) { ui->query[l] = (char)k; ui->query[l + 1] = '\0'; }
        ui->sel = 0;
    }
}

/* --- no-tty fallback -------------------------------------------------------- */
static int no_tty_pointer(void)
{
    printf("azarch: no interactive terminal. Use the subcommands instead, e.g.:\n"
           "  azarch theme --dark        set the theme\n"
           "  azarch wallpaper           show / set the wallpaper\n"
           "  azarch network             network status and controls\n"
           "Run `azarch --help` for the full list.\n");
    return 0;
}

int main(void)
{
    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO))
        return no_tty_pointer();

    if (tcgetattr(STDIN_FILENO, &g_orig_termios) != 0)
        return no_tty_pointer();

    atexit(on_exit_restore);
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGHUP, on_signal);
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_winch;
    sigaction(SIGWINCH, &sa, NULL);

    AzUI ui; memset(&ui, 0, sizeof ui);
    ui.stack[0] = "main";
    ui.depth = 1;

    enter_raw();

    for (;;) {
        term_size(&ui.rows, &ui.cols);
        /* If the previous frame drew a kitty image and this one won't be at the same
         * place, clearing happens inside kitten icat --clear; but on plain redraws we
         * must clear a lingering image when the hovered row has no preview. */
        AzRect pv;
        az_render(&ui, &pv);
        if (g_had_image && !(pv.valid)) { az_preview_clear(); g_had_image = 0; }
        int drew_img = az_preview_draw(&ui, &pv);
        if (drew_img) g_had_image = 1;

        int k = read_key();
        if (k == K_RESIZE) continue;

        if (ui.searching) { search_key(&ui, k); continue; }

        switch (k) {
            case K_UP: case 'k': case 'w':
                if (ui.sel > 0) ui.sel--;
                ui.message[0] = '\0';
                break;
            case K_DOWN: case 'j': case 's': {
                const AzRow *vis[64];
                int nvis = az_visible_rows(&ui, vis, 64);
                if (ui.sel < nvis - 1) ui.sel++;
                ui.message[0] = '\0';
                break;
            }
            case K_RIGHT: case 'l': case 'd': case ' ':
                activate(&ui); break;
            case K_ENTER:
                activate(&ui); break;
            case K_LEFT: case 'h': case 'a':
                go_back(&ui); break;
            case '/':
                ui.searching = 1; break;
            case K_ESC:
                if (ui.depth == 1 && !ui.query[0]) { leave_raw(); return 0; }
                go_back(&ui);
                break;
            case 'q':
                if (ui.depth == 1) { leave_raw(); return 0; }
                go_back(&ui);
                break;
            default: break;
        }
    }
}
