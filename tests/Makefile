# Az'arch -- C test runner for the application-menu daemon.
#
# The C sources live in libraries/packages/application_menu/; this is the single
# home for their tests (the Python pytest suite already lives here too). Two targets:
#
#   make -C tests test      headless unit tests (test_apps.c + the shipping apps.c);
#                           no GTK/X needed. This is what the top-level `make test` and
#                           the package Makefile's `test` target both delegate to.
#   make -C tests test-ui   interactive UI regression checks against the live hypervisor
#                           (test_ui.sh); self-skips if the hypervisor/ffmpeg/XTEST are
#                           unavailable, so it is kept out of the default `test`.
#
# APP_DIR points back at the daemon sources so test_apps.c can compile apps.c and
# resolve "apps.h". The daemon binary itself is built by the package Makefile (test_ui.sh
# invokes that); nothing here dirties the package tree.
CC      ?= gcc
APP_DIR  = ../libraries/packages/application_menu

TEST_BIN    = test_apps
TEST_PKGS   = glib-2.0
TEST_CFLAGS = -O2 -Wall -Wextra -std=c11 -I$(APP_DIR) $(shell pkg-config --cflags $(TEST_PKGS))
TEST_LIBS   = $(shell pkg-config --libs $(TEST_PKGS))

$(TEST_BIN): test_apps.c $(APP_DIR)/apps.c $(APP_DIR)/apps.h
	$(CC) $(TEST_CFLAGS) test_apps.c $(APP_DIR)/apps.c -o $@ $(TEST_LIBS)

test: $(TEST_BIN)
	./$(TEST_BIN)

test-ui:
	./test_ui.sh

clean:
	rm -f $(TEST_BIN)

.PHONY: test test-ui clean
