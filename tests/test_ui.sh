#!/usr/bin/env bash
# Az'arch application menu -- interactive UI regression checks.
#
# These cover the behaviours that the headless unit tests (test_apps.c) cannot:
#   1. No black flash while deleting a search query down (scrollbar re-appearing must
#      not blank the override-redirect toplevel).
#   2. No cover/gap under the search box at MAX scroll: the strip immediately below the
#      search box must be ROW CONTENT (icon/text ink), not the window background. This is
#      the scroll-drag "cover" regression -- a viewport desync used to leave a ~64px
#      unpainted band there; software scrolling must keep it filled.
#   3. Power buttons highlight on mouse hover (not only on TAB focus), and the highlight
#      is the SAME blue outline (#3daee9) as keyboard focus -- the seat grab's synthetic
#      crossings must not clobber hover, and the fill+outline must actually be drawn.
#   4. Hover TAKES OVER the TAB highlight: with the mouse over one button while another
#      is TAB-focused, only the hovered button is lit and the focused one goes dark.
#   5. Dragging the scrollbar thumb keeps scrolling even when the pointer drifts off the
#      narrow bar (grab + root-coordinate tracking).
#
# This script lives in the repo-root tests/ dir (the single home for the suite). It drives
# the REAL daemon on the live hypervisor over SSH using a tiny XTEST injector it compiles
# on the target, and reads the screen back with ffmpeg x11grab. It is opt-in and self-
# skips (exit 0) if the hypervisor or its tools are missing, so `make test` stays headless-
# only; run this explicitly with `make test-ui` (from tests/ or the repo root).
#
# Env overrides: SSH_PORT (2221), SSH_HOST (main@localhost), DISP (:0).
set -u

PORT="${SSH_PORT:-2221}"
HOST="${SSH_HOST:-main@localhost}"
DISP="${DISP:-:0}"
SSH="ssh -p ${PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 ${HOST}"
SCP="scp -P ${PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
HERE="$(cd "$(dirname "$0")" && pwd)"
# The C daemon sources + their Makefile live in the package dir; this test dir reaches
# back to it to build the binary under test.
APP_DIR="$HERE/../libraries/packages/application_menu"

skip() { echo "SKIP test_ui: $*"; exit 0; }
fail() { echo "FAIL test_ui: $*"; exit 1; }

# --- preflight: reachable target with the tools we need ----------------------
timeout 12 $SSH "command -v ffmpeg gcc >/dev/null && [ -e /usr/lib/libXtst.so ]" \
    </dev/null >/dev/null 2>&1 || skip "hypervisor unreachable or missing ffmpeg/gcc/libXtst"

echo "test_ui: building daemon + injector on target ..."
( cd "$APP_DIR" && make >/dev/null 2>&1 ) || fail "daemon build failed"
# A daemon left running from a previous run holds /tmp/azd-test mapped (text-file-busy),
# so scp cannot overwrite it -- stop it and remove the old binary FIRST, then copy. Without
# this the copy fails and the whole suite silently skips on every repeat run.
timeout 20 $SSH 'kill -TERM "$(cat /run/user/1000/azarch-application-menu.pid 2>/dev/null)" 2>/dev/null; sleep 0.4; rm -f /tmp/azd-test /run/user/1000/azarch-application-menu.pid' </dev/null >/dev/null 2>&1
timeout 30 $SCP "$APP_DIR/azarch-application-menu-daemon" "${HOST}:/tmp/azd-test" </dev/null >/dev/null 2>&1 \
    || skip "cannot copy daemon to target"

# Injector (XTEST): move/click/key/type/drag2 (drag with x-drift).
INJ_SRC='/tmp/az_inject.c'
timeout 30 $SSH "cat > ${INJ_SRC} <<'EOF'
#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>
#include <X11/keysym.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static Display*d; static void fl(int u){XFlush(d); if(u)usleep(u);}
int main(int c,char**v){ d=XOpenDisplay(0); if(!d)return 1; if(c<2)return 2;
 if(!strcmp(v[1],\"move\")&&c>=4){XTestFakeMotionEvent(d,-1,atoi(v[2]),atoi(v[3]),0);fl(60000);}
 else if(!strcmp(v[1],\"click\")){XTestFakeButtonEvent(d,1,1,0);fl(40000);XTestFakeButtonEvent(d,1,0,0);fl(40000);}
 else if(!strcmp(v[1],\"key\")&&c>=3){KeySym k=XStringToKeysym(v[2]);KeyCode kc=XKeysymToKeycode(d,k);XTestFakeKeyEvent(d,kc,1,0);fl(25000);XTestFakeKeyEvent(d,kc,0,0);fl(25000);}
 else if(!strcmp(v[1],\"type\")&&c>=3){for(char*p=v[2];*p;++p){KeySym k=(KeySym)(unsigned char)*p;KeyCode kc=XKeysymToKeycode(d,k);int s=(*p>='A'&&*p<='Z');if(s)XTestFakeKeyEvent(d,XKeysymToKeycode(d,XK_Shift_L),1,0);XTestFakeKeyEvent(d,kc,1,0);fl(20000);XTestFakeKeyEvent(d,kc,0,0);if(s)XTestFakeKeyEvent(d,XKeysymToKeycode(d,XK_Shift_L),0,0);fl(20000);}}
 else if(!strcmp(v[1],\"drag2\")&&c>=7){int x0=atoi(v[2]),y0=atoi(v[3]),x1=atoi(v[4]),y1=atoi(v[5]),n=atoi(v[6]);
   XTestFakeMotionEvent(d,-1,x0,y0,0);fl(80000);XTestFakeButtonEvent(d,1,1,0);fl(20000);
   for(int i=1;i<=n;i++){int xx=x0+(x1-x0)*i/n,yy=y0+(y1-y0)*i/n;XTestFakeMotionEvent(d,-1,xx,yy,0);fl(12000);}
   XTestFakeButtonEvent(d,1,0,0);fl(40000);}
 XCloseDisplay(d);return 0;}
EOF
gcc -O2 -o /tmp/az_inject ${INJ_SRC} -lX11 -lXtst" </dev/null >/dev/null 2>&1 || skip "injector build failed on target"

# --- helpers that run wholly on the target -----------------------------------
# mean_brightness <pngpath> : prints the mean RGB brightness of the centered menu
# (582x497) region, using ffmpeg's signalstats (no PIL on the target).
REMOTE_HELPERS='
mean_menu() {  # $1 = png
  # crop the centered 582x497 menu and print average luma*... use ffmpeg signalstats.
  ffmpeg -loglevel error -i "$1" -vf "crop=582:497:(iw-582)/2:(ih-497)/2,signalstats,metadata=print:file=-" -f null - 2>/dev/null \
    | awk -F= "/YAVG/{print \$2; exit}"
}
shot() { ffmpeg -loglevel error -f x11grab -video_size 1920x1080 -i '"$DISP"' -frames:v 1 -y "$1" >/dev/null 2>&1; }
'

start_daemon='
export DISPLAY='"$DISP"'
OLD=$(cat /run/user/1000/azarch-application-menu.pid 2>/dev/null); kill -TERM "$OLD" 2>/dev/null; sleep 0.3
rm -f /run/user/1000/azarch-application-menu.pid; chmod +x /tmp/azd-test
nohup /tmp/azd-test >/tmp/azd-test.log 2>&1 & sleep 1.5
PID=$(cat /run/user/1000/azarch-application-menu.pid)
'

echo "test_ui: (1) black-flash-on-delete ..."
Y=$(timeout 90 $SSH "${REMOTE_HELPERS}${start_daemon}"'
kill -USR2 "$PID"; sleep 0.6
/tmp/az_inject type fire; sleep 0.3
minY=999
for s in 3 2 1 0; do
  /tmp/az_inject key BackSpace; sleep 0.3
  shot /tmp/ui_bs.png
  y=$(mean_menu /tmp/ui_bs.png); y=${y%.*}; [ -z "$y" ] && y=0
  [ "$y" -lt "$minY" ] && minY=$y
done
echo "$minY"' </dev/null 2>/dev/null | tail -1)
echo "     min menu brightness across delete = ${Y:-?} (black would be ~0)"
[ -n "${Y:-}" ] && [ "$Y" -ge 12 ] || fail "menu went black while deleting (min brightness ${Y:-none})"

echo "test_ui: (2) no cover/gap under search box at max scroll ..."
# The scroll-drag "cover" regression: a viewport desync used to leave a ~64px UNPAINTED
# band (window background) directly under the search box on a large scroll jump. Software
# scrolling must keep that band filled with ROW CONTENT. Walk the selection to the LAST app
# (Down x45 overshoots the list -> viewport pinned at the bottom = max scroll), then assert
# the strip just under the search box is row ink, not background.
#   Geometry (menu 582x497 centered on 1920x1080 -> x0=669,y0=291): the search box + 1px
#   divider end ~menu-local y54, so the viewport-top slot is menu-local y[54..112) = screen
#   y[345..403); crop full width minus the scrollbar column (menu x[10..566] -> screen
#   x[679..1235]). A painted row => YMAX well above the ~46 bg luma; a cover gap => YMAX~46.
TOPINK=$(timeout 70 $SSH "${REMOTE_HELPERS}
export DISPLAY=$DISP
PID=\$(cat /run/user/1000/azarch-application-menu.pid)
kill -USR1 \"\$PID\" 2>/dev/null; sleep 0.3
kill -USR2 \"\$PID\"; sleep 0.6
for i in \$(seq 1 45); do /tmp/az_inject key Down >/dev/null 2>&1; done; sleep 0.3
shot /tmp/ui_max.png
ffmpeg -loglevel error -i /tmp/ui_max.png -vf 'crop=556:58:679:345,signalstats,metadata=print:file=-' -f null - 2>/dev/null | awk -F= '/YMAX/{print \$2; exit}'" </dev/null 2>/dev/null | tail -1)
TOPINK=${TOPINK%.*}
echo "     brightest pixel in the strip under the search box (max scroll) = ${TOPINK:-?} (bg ~ 46, row ink > 150)"
[ -n "${TOPINK:-}" ] && [ "$TOPINK" -ge 120 ] || fail "cover/gap under search box at max scroll (strip is background, YMAX ${TOPINK:-none})"

echo "test_ui: (3) power-button hover highlights with the blue outline ..."
# Pre-park pointer on the Lock button center, then show (grab fires with pointer on it).
# The Lock cell must (a) brighten (the selection FILL) AND (b) carry the Breeze blue
# OUTLINE #3daee9 -- the same highlight TAB focus draws. In YUV the blue outline shows as
# high Cb (UMAX) and low Cr (VMIN): measured hovered UMAX~171 / VMIN~74 vs un-hovered
# ~131 / ~126, so VMIN<=100 is a wide-margin "the blue outline was drawn" test.
# Lock cell screen coords: x[815..959] y[729..781] -> crop 144:52:815:729.
read LOCKY LOCKV < <(timeout 60 $SSH "${REMOTE_HELPERS}
export DISPLAY=$DISP
PID=\$(cat /run/user/1000/azarch-application-menu.pid)
kill -USR1 \"\$PID\" 2>/dev/null; sleep 0.4
/tmp/az_inject move 887 758
kill -USR2 \"\$PID\"; sleep 0.7
shot /tmp/ui_hov.png
ffmpeg -loglevel error -i /tmp/ui_hov.png -vf 'crop=144:52:815:729,signalstats,metadata=print:file=-' -f null - 2>/dev/null | awk -F= '/YAVG/{y=\$2} /VMIN/{v=\$2} END{printf \"%d %d\", y, v}'" </dev/null 2>/dev/null | tail -1)
echo "     Lock cell while hovered: brightness=${LOCKY:-?} (bg ~40)  VMIN=${LOCKV:-?} (blue outline => <=100)"
[ -n "${LOCKY:-}" ] && [ "$LOCKY" -ge 48 ] || fail "power button did not brighten on hover (brightness ${LOCKY:-none})"
[ -n "${LOCKV:-}" ] && [ "$LOCKV" -le 100 ] || fail "power button hover lacked the blue outline (VMIN ${LOCKV:-none}, expected <=100)"

echo "test_ui: (4) hover TAKES OVER the TAB highlight ..."
# TAB into the power row lands focus on "Shut Down" (index 3, rightmost). With the mouse
# then moved onto Lock (index 1), hover must TAKE OVER: only Lock lights blue and the
# TAB-focused "Shut Down" goes dark. Assert Lock has the blue outline (VMIN low) while
# Shut Down does NOT (VMIN near-neutral, ~126). Shut Down cell screen x[1105..1249].
read LOCKV SDOWNV < <(timeout 60 $SSH "${REMOTE_HELPERS}
export DISPLAY=$DISP
PID=\$(cat /run/user/1000/azarch-application-menu.pid)
kill -USR1 \"\$PID\" 2>/dev/null; sleep 0.4
/tmp/az_inject move 100 100
kill -USR2 \"\$PID\"; sleep 0.6
/tmp/az_inject key Tab; sleep 0.2          # focus -> Shut Down (index 3)
/tmp/az_inject move 887 758; sleep 0.3     # hover Lock -> should take over
shot /tmp/ui_takeover.png
LV=\$(ffmpeg -loglevel error -i /tmp/ui_takeover.png -vf 'crop=144:52:815:729,signalstats,metadata=print:file=-' -f null - 2>/dev/null | awk -F= '/VMIN/{print \$2; exit}')
SV=\$(ffmpeg -loglevel error -i /tmp/ui_takeover.png -vf 'crop=144:52:1105:729,signalstats,metadata=print:file=-' -f null - 2>/dev/null | awk -F= '/VMIN/{print \$2; exit}')
printf '%d %d' \"\${LV%.*}\" \"\${SV%.*}\"" </dev/null 2>/dev/null | tail -1)
echo "     Lock VMIN=${LOCKV:-?} (hovered => <=100)   Shut Down VMIN=${SDOWNV:-?} (dark => >=110)"
[ -n "${LOCKV:-}" ] && [ "$LOCKV" -le 100 ] || fail "hover did not light Lock under TAB focus (VMIN ${LOCKV:-none})"
[ -n "${SDOWNV:-}" ] && [ "$SDOWNV" -ge 110 ] || fail "hover did not take over: TAB-focused Shut Down still lit (VMIN ${SDOWNV:-none})"

echo "test_ui: (5) scrollbar thumb drag tracks off-bar ..."
# Full list overflows; drag from on-bar (x=1245) drifting left off the bar while going
# down. The top-of-list must change (list scrolled).
SCROLLED=$(timeout 70 $SSH "${REMOTE_HELPERS}
export DISPLAY=$DISP
PID=\$(cat /run/user/1000/azarch-application-menu.pid)
kill -USR1 \"\$PID\" 2>/dev/null; sleep 0.3
kill -USR2 \"\$PID\"; sleep 0.7
shot /tmp/ui_top.png
/tmp/az_inject drag2 1245 380 1150 700 45
shot /tmp/ui_bot.png
# Compare a crop of the first row region between the two shots via ffmpeg PSNR-ish:
# use blend difference average; nonzero => content moved.
ffmpeg -loglevel error -i /tmp/ui_top.png -i /tmp/ui_bot.png -filter_complex \
 'crop=330:60:740:355[a];[1:v]crop=330:60:740:355[b];[a][b]blend=all_mode=difference,signalstats,metadata=print:file=-' \
 -f null - 2>/dev/null | awk -F= '/YAVG/{print \$2; exit}'" </dev/null 2>/dev/null | tail -1)
SCROLLED=${SCROLLED%.*}
echo "     top-of-list difference after drag = ${SCROLLED:-?} (0 => did not scroll)"
[ -n "${SCROLLED:-}" ] && [ "$SCROLLED" -ge 3 ] || fail "scrollbar drag did not scroll the list off-bar (diff ${SCROLLED:-none})"

# restore a clean daemon instance
timeout 20 $SSH "export DISPLAY=$DISP; kill -USR1 \$(cat /run/user/1000/azarch-application-menu.pid) 2>/dev/null" </dev/null >/dev/null 2>&1

echo "PASS test_ui: black-flash, no-gap-at-max-scroll, hover blue outline, hover-takeover, and off-bar drag all OK"
