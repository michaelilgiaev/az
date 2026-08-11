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

# Unit tests (headless, no GTK/X needed): assert the hidden-id installer swap and
# category typing against the SHIPPING apps.c. Run with `make test`.
TEST_BIN  = test_apps
TEST_PKGS = glib-2.0
TEST_CFLAGS = -O2 -Wall -Wextra -std=c11 $(shell pkg-config --cflags $(TEST_PKGS))

$(BIN): $(OBJS)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

$(TEST_BIN): test_apps.c apps.c apps.h
	$(CC) $(TEST_CFLAGS) test_apps.c apps.c -o $@ $(shell pkg-config --libs $(TEST_PKGS))

test: $(TEST_BIN)
	./$(TEST_BIN)

# Interactive UI regression checks against the live hypervisor (black-flash on
# delete, power-button hover, off-bar scrollbar drag). Needs the daemon built; self-
# skips if the hypervisor/ffmpeg/XTEST are unavailable. Kept out of `test` so the
# default test run stays headless.
test-ui: $(BIN)
	./test_ui.sh

clean:
	rm -f $(OBJS) $(BIN) $(TEST_BIN)

.PHONY: clean test test-ui
