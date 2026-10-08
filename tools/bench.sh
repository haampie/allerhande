#!/bin/sh
# Benchmark bin/recipe on the server itself.
#
#   tools/bench.sh                                  # process cost only
#   HOST=example.com tools/bench.sh                 # ... plus HTTPS through local nginx
#   HOST=example.com SCHEME=http PORT=80 tools/bench.sh
#
# Environment: RECIPE (default bin/recipe), N requests per test (default 2000),
# C concurrent clients for the throughput test (default: number of CPUs).
# Needs cc and curl; nothing is installed.
set -eu

RECIPE=${RECIPE:-bin/recipe}
N=${N:-2000}
C=${C:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}
HOST=${HOST:-}
SCHEME=${SCHEME:-https}
PORT=${PORT:-443}

[ -x "$RECIPE" ] || { echo "not executable: $RECIPE (run make first, or set RECIPE)" >&2; exit 1; }
RECIPE=$(cd "$(dirname "$RECIPE")" && pwd)/$(basename "$RECIPE")

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Prints "min / median / mean / p99 / max" of the numbers (seconds) on stdin, in us or ms.
stats() {
    sort -n | awk -v unit="$1" '
        { v[NR] = $1 * (unit == "ms" ? 1e3 : 1e6); s += v[NR] }
        END {
            p = int(NR * 0.99); if (p < 1) p = 1
            printf "min %.2f  median %.2f  mean %.2f  p99 %.2f  max %.2f %s\n",
                   v[1], v[int((NR + 1) / 2)], s / NR, v[p], v[NR], unit
        }'
}

echo "== $(uname -srm), $C CPUs, N=$N"
file "$RECIPE" 2>/dev/null | sed 's/^[^:]*: /binary: /' | cut -c1-110 || true

# 1. fork + exec + wait, as fcgiwrap does it, against an empty program as a floor.
cat > "$TMP/spawn.c" <<'EOF'
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static double now(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
int main(int argc, char **argv)
{
    int i, n = atoi(argv[2]), st, devnull = open("/dev/null", O_WRONLY);
    for (i = -100; i < n; i++) {  /* first 100 are warm-up */
        double t = now();
        pid_t pid = fork();
        if (pid == 0) {
            dup2(devnull, 1);
            execl(argv[1], argv[1], (char *)NULL);
            _exit(127);
        }
        waitpid(pid, &st, 0);
        if (st != 0) { fprintf(stderr, "%s failed\n", argv[1]); return 1; }
        if (i >= 0) printf("%.9f\n", now() - t);
    }
    return 0;
}
EOF
echo 'int main(void) { return 0; }' > "$TMP/empty.c"
cc -O2 -o "$TMP/spawn" "$TMP/spawn.c" 2>/dev/null || cc -O2 -o "$TMP/spawn" "$TMP/spawn.c" -lrt
cc -O2 -static -o "$TMP/empty" "$TMP/empty.c" 2>/dev/null || cc -O2 -o "$TMP/empty" "$TMP/empty.c"

echo
echo "== process: fork + exec + wait, output to /dev/null"
printf '  empty program  '; "$TMP/spawn" "$TMP/empty" "$N" | stats us
printf '  recipe         '; "$TMP/spawn" "$RECIPE" "$N" | stats us

[ -n "$HOST" ] || { echo; echo "(set HOST=<server_name> to also benchmark through nginx)"; exit 0; }

# 2. Sequential requests over one keep-alive connection to the local nginx.
URL="$SCHEME://$HOST:$PORT/recipe"
CURL="curl -sS -k --resolve $HOST:$PORT:127.0.0.1"
i=0
: > "$TMP/curl.cfg"
while [ $i -lt "$N" ]; do
    printf 'url = "%s"\noutput = "/dev/null"\n' "$URL" >> "$TMP/curl.cfg"
    i=$((i + 1))
done

echo
echo "== nginx: $URL via 127.0.0.1, one connection, sequential"
code=$($CURL -o /dev/null -w '%{http_code}' "$URL")
[ "$code" = 200 ] || { echo "  got HTTP $code, expected 200" >&2; exit 1; }
printf '  request        '; $CURL -K "$TMP/curl.cfg" -w '%{time_total}\n' | stats ms

# 3. Throughput: C clients, each with its own keep-alive connection.
echo
echo "== nginx: $C concurrent clients x $N requests"
start=$(date +%s.%N)
j=0
while [ $j -lt "$C" ]; do
    $CURL -K "$TMP/curl.cfg" -w '%{http_code}\n' > "$TMP/codes.$j" &
    j=$((j + 1))
done
wait
end=$(date +%s.%N)
total=$((N * C))
ok=$(cat "$TMP"/codes.* | grep -c '^200$' || true)
awk -v t="$total" -v ok="$ok" -v s="$start" -v e="$end" \
    'BEGIN { printf "  %d requests (%d OK) in %.2f s = %.0f req/s\n", t, ok, e - s, t / (e - s) }'
