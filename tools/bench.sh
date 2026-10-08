#!/bin/sh
# Benchmark /recipe through the local nginx, run on the server itself.
#
#   HOST=example.com tools/bench.sh
#   HOST=example.com SCHEME=http PORT=80 tools/bench.sh
#
# Compares /recipe with a static file of similar size (favicon.ico) over one
# keep-alive connection, and subtracts curl's own CPU time: on a small machine
# the client competes with the server for the same CPU.
#
# Environment: N requests per test (default 2000), C concurrent clients for the
# throughput test (default: number of CPUs). Needs curl; nothing is installed.
set -eu

HOST=${HOST:?set HOST to the nginx server_name}
N=${N:-2000}
C=${C:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}
SCHEME=${SCHEME:-https}
PORT=${PORT:-443}
STATIC=${STATIC:-favicon.ico}

CURL="curl -sS -k --resolve $HOST:$PORT:127.0.0.1"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "== $(uname -srm), $(getconf _NPROCESSORS_ONLN 2>/dev/null || echo "?") CPUs, N=$N, C=$C, $SCHEME://$HOST:$PORT via 127.0.0.1"

for path in "$STATIC" recipe; do
    code=$($CURL -o /dev/null -w '%{http_code}' "$SCHEME://$HOST:$PORT/$path")
    [ "$code" = 200 ] || { echo "/$path: got HTTP $code, expected 200" >&2; exit 1; }
    i=0
    while [ $i -lt "$N" ]; do
        printf 'url = "%s"\noutput = "/dev/null"\n' "$SCHEME://$HOST:$PORT/$path"
        i=$((i + 1))
    done > "$TMP/$path.cfg"
done

# Sequential: wall time per request, minus curl's CPU time (from `times`).
echo
echo "== sequential, one connection"
for path in "$STATIC" recipe; do
    (
        start=$(date +%s.%N)
        $CURL -K "$TMP/$path.cfg"
        end=$(date +%s.%N)
        echo "$start $end"
        times
    ) | awk -v n="$N" -v path="/$path" '
        function secs(t) { split(t, a, "m"); sub("s", "", a[2]); return a[1] * 60 + a[2] }
        NR == 1 { wall = $2 - $1 }
        NR == 3 { client = secs($1) + secs($2) }
        END {
            printf "  %-14s %7.0f us/request, of which curl %5.0f us => server %5.0f us (%5.0f req/s server-only)\n",
                   path, wall / n * 1e6, client / n * 1e6, (wall - client) / n * 1e6, n / (wall - client)
        }'
done

# Throughput: C clients, each with its own keep-alive connection.
echo
echo "== /recipe, $C concurrent clients x $N requests (curl shares the CPUs)"
start=$(date +%s.%N)
j=0
while [ $j -lt "$C" ]; do
    $CURL -K "$TMP/recipe.cfg" -w '%{http_code}\n' > "$TMP/codes.$j" &
    j=$((j + 1))
done
wait
end=$(date +%s.%N)
total=$((N * C))
ok=$(cat "$TMP"/codes.* | grep -c '^200$' || true)
awk -v t="$total" -v ok="$ok" -v s="$start" -v e="$end" \
    'BEGIN { printf "  %d requests (%d OK) in %.2f s = %.0f req/s\n", t, ok, e - s, t / (e - s) }'
