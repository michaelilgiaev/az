# Az'arch -- C test runner for the compiled C packages.
#
# The C sources live in libraries/packages/{application_menu,azarch}/ (the bare-`azarch` TUI
# is C inside the azarch package now); this dir is the single home for their tests (the Python
# pytest suite lives here too, run by `bash tests.sh`).
#
#   make -C tests test      headless C unit tests -- the application-menu (test_applications.c
#                           + the shipping applications.c) AND the bare-`azarch` TUI model
#                           (test_tui_model.c + the shipping model.c). No GTK/X/kitty needed.
#                           This is what the top-level `make test` and the package Makefiles'
#                           `test` targets delegate to.
#
# APP_DIR / TUI_DIR point back at the package sources so the tests can compile the shipping
# translation units and resolve their headers. Nothing here dirties the package trees.
CC      ?= gcc
APP_DIR  = ../libraries/packages/application_menu
TUI_DIR  = ../libraries/packages/azarch

TEST_BIN    = test_applications
TEST_PKGS   = glib-2.0
TEST_CFLAGS = -O2 -Wall -Wextra -std=c11 -I$(APP_DIR) $(shell pkg-config --cflags $(TEST_PKGS))
TEST_LIBS   = $(shell pkg-config --libs $(TEST_PKGS))

# The TUI model test: pure libc, no pkg-config libs (the model.c under test forks tools at
# RUNTIME for status, but the tested paths -- the tree, the filter, the wallpaper path --
# never do). _POSIX_C_SOURCE matches model.c's own feature-test level.
TUI_TEST_BIN    = test_tui_model
TUI_TEST_CFLAGS = -O2 -Wall -Wextra -std=c11 -D_POSIX_C_SOURCE=200809L -I$(TUI_DIR)

$(TEST_BIN): test_applications.c $(APP_DIR)/applications.c $(APP_DIR)/applications.h
	$(CC) $(TEST_CFLAGS) test_applications.c $(APP_DIR)/applications.c -o $@ $(TEST_LIBS)

$(TUI_TEST_BIN): test_tui_model.c $(TUI_DIR)/model.c $(TUI_DIR)/tui.h
	$(CC) $(TUI_TEST_CFLAGS) test_tui_model.c $(TUI_DIR)/model.c -o $@

test: $(TEST_BIN) $(TUI_TEST_BIN)
	./$(TEST_BIN)
	./$(TUI_TEST_BIN)

clean:
	rm -f $(TEST_BIN) $(TUI_TEST_BIN)

.PHONY: test clean
