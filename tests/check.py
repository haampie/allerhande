#!/usr/bin/env python3
"""Check the compiled model against the source JSON and validate recipe output.

Usage: check.py markov-2.json bin/recipe [runs]
"""

import collections
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import compile_markov  # noqa: E402

UINT32_MAX = 0xFFFFFFFF
NONE = 0xFFFFFFFF
SENTENCE_END = 0x80000000


def ends_sentence(w):
    return w.endswith(".") or w.endswith("!")


def check_model(markov, model):
    blob = model["blob"]
    words = []
    for off, lf in model["words"]:
        w = blob[off:off + (lf & ~SENTENCE_END)].decode("utf-8")
        assert bool(lf & SENTENCE_END) == ends_sentence(w)
        words.append(w)
    assert len(set(words)) == len(words)

    keys = list(markov)
    assert len(model["states"]) == len(keys)
    for key, (first, count) in zip(keys, model["states"]):
        w2 = key.split(" ")[1]
        prev = 0
        got = set()
        for t, wid, nxt in model["transitions"][first:first + count]:
            assert t >= prev
            prev = t
            w3 = words[wid]
            got.add(w3)
            nk = w2 + " " + w3
            assert (nxt == NONE) == (nk not in markov)
            assert nxt == NONE or keys[nxt] == nk
        assert prev == UINT32_MAX
        assert got == set(markov[key])

    starts = set()
    prev = 0
    for t, a, b, st in model["starts"]:
        assert t >= prev
        prev = t
        assert keys[st] == words[a] + " " + words[b]
        assert not ends_sentence(words[a]) and not ends_sentence(words[b])
        starts.add((words[a], words[b]))
    assert prev == UINT32_MAX
    print("model ok: %d states, %d transitions, %d start pairs"
          % (len(keys), len(model["transitions"]), len(starts)))
    return starts


def check_outputs(markov, starts, exe, runs):
    header = b"Content-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\n\r\n"
    seen_starts = collections.Counter()
    outputs = set()
    lengths = []
    full = 0
    for _ in range(runs):
        raw = subprocess.check_output([exe])
        assert raw.startswith(header), raw[:100]
        text = raw[len(header):].decode("utf-8")
        outputs.add(text)
        ws = text.split(" ")
        assert (ws[0], ws[1]) in starts
        seen_starts[(ws[0], ws[1])] += 1
        for a, b, c in zip(ws, ws[1:], ws[2:]):
            assert c in markov[a + " " + b], (a, b, c)
        n = len(ws) - 2
        lengths.append(n)
        full += ends_sentence(ws[-1])
        dead_end = (ws[-2] + " " + ws[-1]) not in markov
        assert n <= 300
        if n < 150:
            assert dead_end, text
        elif n > 150:
            assert not any(ends_sentence(w) for w in ws[152:-1])
            assert ends_sentence(ws[-1]) or n == 300 or dead_end, text
    print("outputs ok: %d runs, %d distinct, %d distinct start pairs" % (runs, len(outputs),
          len(seen_starts)))
    print("words after start pair min/avg/max: %d/%.0f/%d, ending in a full sentence: %.1f%%"
          % (min(lengths), sum(lengths) / len(lengths), max(lengths), 100.0 * full / runs))
    print("most common starts:", ", ".join(" ".join(k) for k, _ in seen_starts.most_common(8)))



def main():
    json_path, exe = sys.argv[1:3]
    runs = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
    markov = compile_markov.load(json_path)
    starts = check_model(markov, compile_markov.build(markov))
    check_outputs(markov, starts, exe, runs)


if __name__ == "__main__":
    main()
