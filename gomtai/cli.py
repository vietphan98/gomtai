"""Dòng lệnh: gomtai get <links...> | gomtai web."""
import argparse
import sys
import time

from .core import Manager


def _bar(t, width=24):
    p = t.progress
    if p is None:
        return f"[{'?' * width}]"
    n = int(p * width)
    return "[" + "#" * n + "-" * (width - n) + f"] {p * 100:5.1f}%"


def cmd_get(a):
    links = list(a.links)
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            links += f.read().splitlines()
    if not a.links and not a.file and not sys.stdin.isatty():
        links += sys.stdin.read().splitlines()
    m = Manager(a.dest, workers=a.workers)
    m.add_many("\n".join(links))
    if not m.tasks:
        print("Không có liên kết nào.")
        return 1
    lines = 0
    while True:
        done = m.wait(timeout=0.3)
        if lines:
            sys.stdout.write(f"\x1b[{lines}F")
        ts = list(m.tasks.values())
        for t in ts:
            sys.stdout.write(f"\x1b[2K{t.filename[:30]:30} {_bar(t)} {t.status}\n")
        lines = len(ts)
        sys.stdout.flush()
        if done:
            break
    bad = [t for t in m.tasks.values() if t.status == "error"]
    for t in bad:
        print(f"LỖI {t.url}: {t.error}")
    for t in m.tasks.values():
        if t.final_path:
            print(f"-> {t.final_path}")
    return 1 if bad else 0


def cmd_web(a):
    from .web import create_app
    m = Manager(a.dest, workers=a.workers)
    print(f"Mở http://{a.host}:{a.port}")
    create_app(m).run(host=a.host, port=a.port)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="gomtai", description="Trình quản lý tải file.")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get", help="tải các liên kết")
    g.add_argument("links", nargs="*")
    g.add_argument("-f", "--file", help="file chứa liên kết, mỗi dòng một cái")
    for s in (g, w := sub.add_parser("web", help="chạy giao diện web")):
        s.add_argument("-d", "--dest", default="downloads")
        s.add_argument("-w", "--workers", type=int, default=3)
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8800)
    g.set_defaults(fn=cmd_get)
    w.set_defaults(fn=cmd_web)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
