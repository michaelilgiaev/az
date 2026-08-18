# Az'arch bare-`azarch` TERMINAL UI (C port) build.
# Produces TWO binaries:
#   azarch      -- the full-screen terminal user interface. Pure libc + raw ANSI/termios (no
#                  ncurses, no GTK) so it is tiny and starts instantly. Image previews shell
#                  out to `kitten icat` at runtime -- no compile-time dep on kitty.
#   azarch-osd  -- the media OSD: the bottom-middle cyan volume/brightness bar (osd.c). It is
#                  an Xlib GUI (single window, no flicker), so it links X11 + Xrandr (primary
#                  monitor) + Xft (anti-aliased percent text, matching the old tkinter look).
#                  Kept a SEPARATE binary from `azarch`: it has its own main() and its own
#                  (X) dependencies, which the tiny terminal UI must not drag in.
CC      ?= gcc
CFLAGS  += -O2 -Wall -Wextra -std=c11
LDFLAGS +=

# The X libraries the OSD links. pkg-config resolves the include/lib flags on the build host
# (falls back to plain -l switches if pkg-config is unavailable, which is enough on a normal
# Xorg dev host). Only azarch-osd uses these; the terminal UI links plain libc.
OSD_PKGS    = x11 xrandr xft
OSD_CFLAGS := $(shell pkg-config --cflags $(OSD_PKGS) 2>/dev/null)
OSD_LIBS   := $(shell pkg-config --libs $(OSD_PKGS) 2>/dev/null)
ifeq ($(strip $(OSD_LIBS)),)
OSD_LIBS   := -lX11 -lXrandr -lXft
OSD_CFLAGS := -I/usr/include/freetype2
endif

# model.c holds the UI infrastructure (capture, probe cache, status probes, filter, row
# helpers); model_tree.c holds the static screen TREE data (ROWS_* + SCREENS[] +
# az_screens/find/count); model_defaultapps.c holds the RUNTIME Default Applications screens
# (az_da_screen, resolved live from installed .desktop files) -- split so each stays under the
# per-file size budget.
OBJS = main.o render.o model.o model_tree.o model_defaultapps.o preview.o action.o
BIN  = azarch
OSD_BIN = azarch-osd

# Repo-root tests dir (single home for tests). `make test` delegates there, matching the
# application_menu Makefile; this Makefile stays the source of truth for BUILDING the
# binaries (build_terminal_user_interface() copies these C sources + this Makefile into a scratch dir and runs
# `make $(BIN)` / `make $(OSD_BIN)`), which is unaffected.
TESTS_DIR = ../../../tests

all: $(BIN) $(OSD_BIN)

$(BIN): $(OBJS)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

# The OSD is a single self-contained translation unit; compile+link it directly with the X
# flags. It shares no headers with the terminal UI (it is a standalone Xlib program).
$(OSD_BIN): osd.c
	$(CC) $(CFLAGS) $(OSD_CFLAGS) osd.c -o $@ $(LDFLAGS) $(OSD_LIBS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

test:
	$(MAKE) -C $(TESTS_DIR) test

clean:
	rm -f $(OBJS) $(BIN) $(OSD_BIN)

.PHONY: all clean test
