# Az'arch bare-`azarch` TERMINAL UI (C port) build.
# Produces a single binary: azarch. Pure libc + raw ANSI/termios (no ncurses, no
# GTK) so it is tiny and starts instantly. Image previews shell out to `kitten icat`
# at runtime -- no compile-time dep on kitty.
CC      ?= gcc
CFLAGS  += -O2 -Wall -Wextra -std=c11
LDFLAGS +=

OBJS = main.o render.o model.o preview.o action.o
BIN  = azarch

# Repo-root tests dir (single home for tests). `make test` delegates there, matching the
# application_menu Makefile; this Makefile stays the source of truth for BUILDING the
# binary (build_terminal_user_interface() copies these C sources + this Makefile into a scratch dir and runs
# `make $(BIN)`), which is unaffected.
TESTS_DIR = ../../../tests

$(BIN): $(OBJS)
	$(CC) $(OBJS) -o $@ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

test:
	$(MAKE) -C $(TESTS_DIR) test

clean:
	rm -f $(OBJS) $(BIN)

.PHONY: clean test
