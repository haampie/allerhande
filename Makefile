# make         bin/recipe, with the model compiled in
# make check   verify the tables and test CGI and FastCGI output
CC ?= cc
PYTHON ?= python3
CFLAGS ?= -O2
WARN = -std=c99 -pedantic-errors -Wall -Wextra

all: bin/recipe

bin/recipe: src/recipe.c src/markov_data.h
	@mkdir -p bin
	$(CC) $(WARN) $(CPPFLAGS) $(CFLAGS) -o $@ src/recipe.c $(LDFLAGS)

src/markov_data.h: storage/markov-2.json tools/compile_markov.py
	$(PYTHON) tools/compile_markov.py storage/markov-2.json $@

check: bin/recipe
	$(PYTHON) tests/check.py storage/markov-2.json bin/recipe

clean:
	rm -rf bin src/markov_data.h

.PHONY: all check clean
