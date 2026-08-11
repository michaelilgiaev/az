# Az'arch application menu (C/GTK3 port) build.
# Produces a single resident binary: azarch-application-menu-daemon.
CC      ?= gcc
PKGS     = gtk+-3.0 gdk-x11-3.0 x11 glib-2.0 gdk-pixbuf-2.0 pango pangocairo cairo
# GTK3 colour/font override + gdk_screen_width APIs are deprecated in favour of
# CSS/monitor APIs but still correct here; silence the noise, keep real warnings.
CFLAGS  += -O2 -Wall -Wextra -std=c11 -Wno-deprecated-declarations \
           $(shell pkg-config --cflags $(PKGS))
LDFLAGS += $(shell pkg-config --libs $(PKGS)) -lm

OBJS = menu.o applist.o apps.o usage.o icons.o actions.o winwatch.o kscroll.o power.o
BIN  = azarch-application-menu-daemon

# The tests now live in the repo-root tests/ dir (their single home). The `test` and
# `test-ui` targets here just delegate there so `make test` still works from this dir;
# tests/Makefile compiles test_apps.c against this dir's apps.c. This Makefile stays the
# source of truth for BUILDING the daemon (build_daemon() copies only these C sources +
# this Makefile into its scratch dir and runs `make $(BIN)`), which is unaffected.
TESTS_DIR = ../../../tests

$(BIN): $(OBJS)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

test:
	$(MAKE) -C $(TESTS_DIR) test

# Interactive UI regression checks against the live hypervisor (no cover/gap under the
# search box at max scroll, power-button hover outline, off-bar scrollbar drag). Needs
# the daemon built first; self-skips if the hypervisor/ffmpeg/XTEST are unavailable. Kept
# out of `test` so the default test run stays headless.
test-ui: $(BIN)
	$(MAKE) -C $(TESTS_DIR) test-ui

clean:
	rm -f $(OBJS) $(BIN)
	$(MAKE) -C $(TESTS_DIR) clean

.PHONY: clean test test-ui
