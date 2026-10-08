# Allerhande recipe generator

Generates dinner recipes using a Markov chain and a lot of recipes.

Working example: https://kookboek.harmenstoppels.nl/

## How it works

- `storage/markov-2.json` is an order-2 Markov chain: `{"w1 w2": {"w3": probability}}`.
- `tools/compile_markov.py` turns it into `src/markov_data.h`, which holds flat lookup tables. Next
  states are precomputed and probabilities stored as cumulative 32-bit thresholds, so generating
  needs no hashing or string comparison.
- `src/recipe.c` is a C99 CGI program with the tables compiled in. Each request runs it once: pick a
  sentence-opening word pair (weighted by how often it occurs in the corpus), walk the chain for 150
  words, keep going until the sentence ends (300 words max), print plain text, exit. No state
  survives between requests.

Generating a recipe takes about 13 µs. Per request, fork+exec dominates: about 160 µs for the static
binary on Linux, against about 80 µs for an empty static program.

## Build

Needs a C99 compiler and Python ≥ 3.5 for the code generator.

    make                    # bin/recipe
    make LDFLAGS=-static    # recommended for deployment: no dynamic loader on every exec
    make check              # verify the tables against the JSON and sanity-check 2000 outputs

## Deploy (nginx + fcgiwrap)

nginx can't run programs itself. fcgiwrap is a small FastCGI bridge that forks and execs
`bin/recipe` for each request, and keeps no state of its own.

1. Install fcgiwrap from your distribution's packages.
2. Build with `make LDFLAGS=-static`.
3. Copy `deploy/nginx-kookboek.conf` into your nginx sites. Set `server_name`, `root` and the
   `SCRIPT_FILENAME` path to your checkout, and add your TLS settings.
4. Run `nginx -t`, reload nginx, and request `/recipe`.

fcgiwrap waits for each child it starts, so run about one worker per CPU core (`fcgiwrap -c N`).
It only needs to execute `bin/recipe` and doesn't need write access to anything.
