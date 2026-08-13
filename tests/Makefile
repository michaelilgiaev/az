# Az'arch -- C test runner for the compiled C packages.
#
# The C sources live in libraries/packages/{application_menu,azarch}/ (the bare-`azarch` terminal user interface
# is C inside the azarch package now); this dir is the single home for their tests (the Python
# pytest suite lives here too, run by `bash tests.sh`).
#
#   make -C tests test      headless C unit tests -- the application-menu (test_applications.c
#                           + the shipping applications.c) AND the bare-`azarch` terminal user interface model
#                           (test_terminal_user_interface_model.c + the shipping model.c). No GTK/X/kitty needed.
#                           This is what the top-level `make test` and the package Makefiles'
#                           `test` targets delegate to.
#
# APP_DIR / TERMINAL_USER_INTERFACE_DIR point back at the package sources so the tests can compile the shipping
# translation units and resolve their headers. Nothing here dirties the package trees.
CC      ?= gcc
APP_DIR  = ../libraries/packages/application_menu
TERMINAL_USER_INTERFACE_DIR  = ../libraries/packages/azarch

TEST_BIN    = test_applications
TEST_PKGS   = glib-2.0
TEST_CFLAGS = -O2 -Wall -Wextra -std=c11 -I$(APP_DIR) $(shell pkg-config --cflags $(TEST_PKGS))
TEST_LIBS   = $(shell pkg-config --libs $(TEST_PKGS))

# The terminal user interface model test: pure libc, no pkg-config libs (the model.c under test forks tools at
# RUNTIME for status, but the tested paths -- the tree, the filter, the wallpaper path --
# never do). _POSIX_C_SOURCE matches model.c's own feature-test level.
TERMINAL_USER_INTERFACE_TEST_BIN    = test_terminal_user_interface_model
TERMINAL_USER_INTERFACE_TEST_CFLAGS = -O2 -Wall -Wextra -std=c11 -D_POSIX_C_SOURCE=200809L -I$(TERMINAL_USER_INTERFACE_DIR)

# The ACTION-layer test: exercises the SHIPPING action.c (capture + sudo credential). It forks
# real subprocesses (sh/timeout) but never authenticates sudo (it forces the failing path), so
# it stays deterministic and needs no privileges.
ACT_TEST_BIN    = test_terminal_user_interface_action

$(TEST_BIN): test_applications.c $(APP_DIR)/applications.c $(APP_DIR)/applications.h
	$(CC) $(TEST_CFLAGS) test_applications.c $(APP_DIR)/applications.c -o $@ $(TEST_LIBS)

$(TERMINAL_USER_INTERFACE_TEST_BIN): test_terminal_user_interface_model.c $(TERMINAL_USER_INTERFACE_DIR)/model.c $(TERMINAL_USER_INTERFACE_DIR)/terminal_user_interface.h
	$(CC) $(TERMINAL_USER_INTERFACE_TEST_CFLAGS) test_terminal_user_interface_model.c $(TERMINAL_USER_INTERFACE_DIR)/model.c -o $@

$(ACT_TEST_BIN): test_terminal_user_interface_action.c $(TERMINAL_USER_INTERFACE_DIR)/action.c $(TERMINAL_USER_INTERFACE_DIR)/action.h
	$(CC) $(TERMINAL_USER_INTERFACE_TEST_CFLAGS) test_terminal_user_interface_action.c $(TERMINAL_USER_INTERFACE_DIR)/action.c -o $@

test: $(TEST_BIN) $(TERMINAL_USER_INTERFACE_TEST_BIN) $(ACT_TEST_BIN)
	./$(TEST_BIN)
	./$(TERMINAL_USER_INTERFACE_TEST_BIN)
	./$(ACT_TEST_BIN)

clean:
	rm -f $(TEST_BIN) $(TERMINAL_USER_INTERFACE_TEST_BIN) $(ACT_TEST_BIN)

.PHONY: test clean
