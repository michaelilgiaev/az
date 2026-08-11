# Az'arch -- C test runner for the application-menu daemon.
#
# The C sources live in libraries/packages/application_menu/; this dir is the single home
# for their tests (the Python pytest suite lives here too, run by `bash tests.sh`).
#
#   make -C tests test      headless C unit tests (test_apps.c + the shipping apps.c);
#                           no GTK/X needed. This is what the top-level `make test` and
#                           the package Makefile's `test` target both delegate to.
#
# APP_DIR points back at the daemon sources so test_apps.c can compile apps.c and resolve
# "apps.h". Nothing here dirties the package tree.
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

clean:
	rm -f $(TEST_BIN)

.PHONY: test clean
