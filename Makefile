# Az'arch -- top-level convenience Makefile.
#
# The heavy lifting lives elsewhere (ISO build: compile.sh / the compiler package;
# Python unit tests: `bash tests.sh` / pytest). This Makefile is just a thin front door
# for the C application-menu daemon and its tests, so `make test` from the repo root does
# the obvious thing.
#
#   make test        headless C unit tests for the application-menu daemon
#                    (delegates to tests/Makefile -> test_apps.c + the shipping apps.c).
#   make menu        build the daemon binary in its package dir.
#   make clean       remove C build artifacts + the compiled test binary.
#
# For the Python suite use `bash tests.sh` (self-bootstrapping venv + pytest).
MENU_DIR = libraries/packages/application_menu

test:
	$(MAKE) -C tests test

menu:
	$(MAKE) -C $(MENU_DIR)

clean:
	$(MAKE) -C $(MENU_DIR) clean

.PHONY: test menu clean
