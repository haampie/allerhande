# Allerhande recipe generator

Generates dinner recipes using a Markov chain and a lot of recipes.

Working example: https://kookboek.harmenstoppels.nl/

## How it works

- `storage/markov-2.json` is an order-2 Markov chain: `{"w1 w2": {"w3": probability}}`.
- `tools/compile_markov.py` turns it into `src/markov_data.h`, which holds flat lookup tables. Next
  states are precomputed and probabilities stored as cumulative 32-bit thresholds, so generating
  needs no hashing or string comparison.
- `src/recipe.c` has the tables compiled in. For each request: pick a sentence-opening word pair
  (weighted by how often it occurs in the corpus), walk the chain for 150 words, keep going until
  the sentence ends (300 words max), and return plain text.
- It runs as a FastCGI server behind nginx, started by systemd. Every request is handled in a fresh
  child process that writes one recipe and exits, so no request state survives. The parent only
  accepts connections; it holds the tables in (huge-page) memory that children inherit without
  page faults. Run without arguments, the same binary acts as a one-shot CGI program.

Generating a recipe takes about 13 µs; forking the child for it is the main per-request cost.

## Build

Needs a C99 compiler and Python ≥ 3.5 for the code generator.

    make          # bin/recipe
    make check    # verify the tables against the JSON, then test CGI and FastCGI output

## Deploy (nginx + systemd)

1. Build with `make`.
2. Create a user for the service:
   `useradd --system --no-create-home --shell /usr/sbin/nologin kookboek`.
3. Copy `deploy/kookboek.socket` and `deploy/kookboek.service` to `/etc/systemd/system/`. Set
   `ExecStart` to your checkout's `bin/recipe`. If nginx doesn't run as `www-data`, change
   `SocketGroup`.
4. Run `systemctl daemon-reload && systemctl enable --now kookboek.socket`. systemd starts the
   service on the first request and restarts it if it ever exits.
5. Copy `deploy/nginx-kookboek.conf` into your nginx sites. Set `server_name` and `root`, and add
   your TLS settings. Then run `nginx -t` and reload nginx.

After a rebuild, run `systemctl restart kookboek.service`.

To benchmark on the server, run `HOST=<server_name> tools/bench.sh`. It compares `/recipe` with a
static file through the local nginx.
