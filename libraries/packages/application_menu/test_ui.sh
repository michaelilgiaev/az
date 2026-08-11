#!/usr/bin/env bash
# Az'arch application menu -- interactive UI regression checks.
#
# These cover the behaviours that the headless unit tests (test_apps.c) cannot:
#   1. No black flash while deleting a search query down (scrollbar re-appearing must
#      not blank the override-redirect toplevel).
#   2. Power buttons highlight on mouse hover (not only on TAB focus) -- i.e. the seat
#      grab's synthetic crossings do not clobber hover.
#   3. Dragging the scrollbar thumb keeps scrolling even when the pointer drifts off
#      the narrow bar (grab + root-coordinate tracking).
#
# It drives the REAL daemon on the live hypervisor over SSH using a tiny XTEST
# injector it compiles on the target, and reads the screen back with ffmpeg x11grab.
# It is opt-in and self-skips (exit 0) if the hypervisor or its tools are missing, so
# `make test` stays headless-only; run this explicitly with `make test-ui`.
#
# Env overrides: SSH_PORT (2221), SSH_HOST (main@localhost), DISP (:0).
set -u

PORT="${SSH_PORT:-2221}"
HOST="${SSH_HOST:-main@localhost}"
DISP="${DISP:-:0}"
SSH="ssh -p ${PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=8 ${HOST}"
SCP="scp -P ${PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
HERE="$(cd "$(dirname "$0")" && pwd)"

skip() { echo "SKIP test_ui: $*"; exit 0; }
fail() { echo "FAIL test_ui: $*"; exit 1; }

# --- preflight: reachable target with the tools we need ----------------------
timeout 12 $SSH "command -v ffmpeg gcc >/dev/null && [ -e /usr/lib/libXtst.so ]" \
    </dev/null >/dev/null 2>&1 || skip "hypervisor unreachable or missing ffmpeg/gcc/libXtst"

echo "test_ui: building daemon + injector on target ..."
( cd "$HERE" && make >/dev/null 2>&1 ) || fail "daemon build failed"
timeout 30 $SCP "$HERE/azarch-application-menu-daemon" "${HOST}:/tmp/azd-test" </dev/null >/dev/null 2>&1 \
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

echo "test_ui: (2) power-button hover highlights ..."
# Pre-park pointer on the Lock button center, then show (grab fires with pointer on it);
# the Lock cell must be brighter than the menu-background hover threshold.
LOCKY=$(timeout 60 $SSH "${REMOTE_HELPERS}
export DISPLAY=$DISP
PID=\$(cat /run/user/1000/azarch-application-menu.pid)
kill -USR1 \"\$PID\" 2>/dev/null; sleep 0.4
/tmp/az_inject move 887 758
kill -USR2 \"\$PID\"; sleep 0.7
shot /tmp/ui_hov.png
# brightness of the Lock cell (x ~ 814..960, y ~ 740..788)
ffmpeg -loglevel error -i /tmp/ui_hov.png -vf 'crop=120:40:820:742,signalstats,metadata=print:file=-' -f null - 2>/dev/null | awk -F= '/YAVG/{print \$2; exit}'" </dev/null 2>/dev/null | tail -1)
LOCKY=${LOCKY%.*}
echo "     Lock cell brightness while hovered = ${LOCKY:-?} (rest bg ~ 40)"
[ -n "${LOCKY:-}" ] && [ "$LOCKY" -ge 48 ] || fail "power button did not highlight on hover (brightness ${LOCKY:-none})"

echo "test_ui: (3) scrollbar thumb drag tracks off-bar ..."
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

echo "PASS test_ui: black-flash, hover, and off-bar drag all OK"
