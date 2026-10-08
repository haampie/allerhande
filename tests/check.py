#!/usr/bin/env python3
"""Check the compiled model against the source JSON and validate recipe output,
both as a CGI program and as a FastCGI server.

Usage: check.py markov-2.json bin/recipe [runs]
"""

import collections
import multiprocessing.pool
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

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


HEADER = b"Content-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\n\r\n"


def check_outputs(markov, starts, label, responses):
    """Validate an iterable of raw responses (CGI headers + recipe)."""
    seen_starts = collections.Counter()
    outputs = set()
    lengths = []
    full = 0
    for raw in responses:
        assert raw.startswith(HEADER), raw[:100]
        text = raw[len(HEADER):].decode("utf-8")
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
    runs = len(lengths)
    print("%s ok: %d runs, %d distinct, %d distinct start pairs" % (label, runs, len(outputs),
          len(seen_starts)))
    print("  words after start pair min/avg/max: %d/%.0f/%d, ending in a full sentence: %.1f%%"
          % (min(lengths), sum(lengths) / len(lengths), max(lengths), 100.0 * full / runs))
    print("  most common starts:", ", ".join(" ".join(k) for k, _ in seen_starts.most_common(6)))


def fcgi_record(rtype, rid, content=b"", padding=0):
    return struct.pack(">BBHHBB", 1, rtype, rid, len(content), padding, 0) + content + \
        b"\0" * padding


def fcgi_params(params):
    out = b""
    for k, v in params:
        for n in (len(k), len(v)):
            out += struct.pack(">B", n) if n < 128 else struct.pack(">I", n | 0x80000000)
        out += k + v
    return out


def fcgi_request(sock_path, rid=1, params=(), body=b"", chunked=False):
    """One FastCGI request as nginx sends it; returns the STDOUT payload."""
    req = fcgi_record(1, rid, struct.pack(">HB5x", 1, 0))  # BEGIN_REQUEST, RESPONDER
    p = fcgi_params(params)
    for i in range(0, len(p), 65535):
        req += fcgi_record(4, rid, p[i:i + 65535], padding=3)
    req += fcgi_record(4, rid)
    for i in range(0, len(body), 65535):
        req += fcgi_record(5, rid, body[i:i + 65535])
    req += fcgi_record(5, rid)

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(sock_path)
    if chunked:  # dribble the request in to exercise partial reads
        for i in range(0, len(req), 7):
            s.sendall(req[i:i + 7])
    else:
        s.sendall(req)
    data = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()

    stdout = b""
    ended = False
    while data:
        version, rtype, r, clen, plen, _ = struct.unpack(">BBHHBB", data[:8])
        assert version == 1 and r == rid, (version, r)
        content = data[8:8 + clen]
        data = data[8 + clen + plen:]
        if rtype == 6:
            stdout += content
        elif rtype == 3:
            assert struct.unpack(">IB3x", content) == (0, 0)
            ended = True
            assert not data
        else:
            raise AssertionError("unexpected record type %d" % rtype)
    assert ended
    return stdout


def check_fastcgi(markov, starts, exe, runs):
    tmp = tempfile.mkdtemp()
    sock_path = os.path.join(tmp, "recipe.sock")
    server = subprocess.Popen([exe, "--listen", sock_path])
    try:
        for _ in range(100):
            if os.path.exists(sock_path):
                break
            time.sleep(0.05)
        params = [(b"REQUEST_METHOD", b"GET"), (b"SCRIPT_NAME", b"/recipe")]
        check_outputs(markov, starts, "fastcgi sequential",
                      (fcgi_request(sock_path, rid=1 + i % 3, params=params) for i in range(runs)))

        odd = [
            fcgi_request(sock_path, params=params, chunked=True),
            fcgi_request(sock_path, params=params + [(b"HTTP_X_BIG", b"x" * 200000)]),
            fcgi_request(sock_path, params=[(b"REQUEST_METHOD", b"POST")], body=b"y" * 300000),
        ]
        check_outputs(markov, starts, "fastcgi chunked/large params/POST body", odd)

        pool = multiprocessing.pool.ThreadPool(16)
        check_outputs(markov, starts, "fastcgi 16 concurrent clients",
                      pool.map(lambda i: fcgi_request(sock_path, params=params), range(runs)))
        pool.close()
        assert server.poll() is None, "server exited"
    finally:
        server.terminate()
        server.wait()
        shutil.rmtree(tmp)


def main():
    json_path, exe = sys.argv[1:3]
    runs = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
    markov = compile_markov.load(json_path)
    starts = check_model(markov, compile_markov.build(markov))
    check_outputs(markov, starts, "cgi", (subprocess.check_output([exe]) for _ in range(runs)))
    check_fastcgi(markov, starts, exe, runs)


if __name__ == "__main__":
    main()
