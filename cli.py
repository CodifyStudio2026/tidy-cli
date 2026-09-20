"""Command line interface for tidy."""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import __version__, journal, organizer, ui
from . import dupes as dupes_mod
from . import stats as stats_mod

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


# ---------------------------------------------------------------- helpers

def parse_size(text: str) -> int:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)b?\s*", text, re.I)
    if not m:
        raise argparse.ArgumentTypeError(f"invalid size: {text!r} (try 500KB, 10MB, 2GB)")
    power = "kmgt".index(m.group(2).lower()) + 1 if m.group(2) else 0
    return int(float(m.group(1)) * 1024 ** power)


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _print_plan(root: Path, moves: list[organizer.Move], mode: str, limit: int = 12) -> None:
    groups: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for m in moves:
        g = groups[_rel(m.dst.parent, root)]
        g[0] += 1
        g[1] += _size_of(m.src)
    print(ui.bold(f"Plan for {root}") + ui.dim(f"  (sorting by {mode})"))
    width = max(len(name) for name in groups)
    for name, (count, size) in sorted(groups.items()):
        print(f"  {ui.cyan(name.ljust(width))}  {_files(count):>9}  {ui.human_size(size):>10}")
    print(ui.dim("\nPreview:"))
    for m in moves[:limit]:
        print(f"  {m.src.name}  {ui.arrow()}  {ui.dim(_rel(m.dst, root))}")
    if len(moves) > limit:
        print(ui.dim(f"  ... and {len(moves) - limit} more"))


def _files(n: int) -> str:
    return f"{n} file" + ("" if n == 1 else "s")


def _log(msg: str) -> None:
    print(f"{ui.dim(datetime.now().strftime('%H:%M:%S'))}  {msg}", flush=True)


# ---------------------------------------------------------------- commands

def cmd_organize(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    moves = organizer.plan(root, args.mode, include_hidden=args.include_hidden)
    if not moves:
        print(ui.dim("Nothing to organize: no loose files found."))
        return EXIT_OK
    _print_plan(root, moves, args.mode)
    if args.dry_run:
        print(ui.dim("\nDry run: nothing was moved."))
        return EXIT_OK
    if not args.yes and not ui.confirm(f"\nMove {len(moves)} files?"):
        print("Cancelled. Nothing was moved. (Use --yes to skip this question.)")
        return EXIT_FAIL
    done, errors = organizer.execute(moves)
    if done:
        journal.record("organize", root, done)
    print(ui.green(f"\nMoved {len(done)} files."))
    for m, exc in errors:
        print(ui.red(f"  failed: {m.src.name}: {exc}"))
    if done:
        print(ui.dim("Changed your mind? Run: tidy undo"))
    return EXIT_FAIL if errors else EXIT_OK


def cmd_undo(args: argparse.Namespace) -> int:
    runs = journal.load()
    if not runs:
        print(ui.dim("Nothing to undo."))
        return EXIT_OK
    run = runs[-1] if args.id is None else next((r for r in runs if r.get("id") == args.id), None)
    if run is None:
        print(ui.red(f"No run with id {args.id}. See: tidy history"), file=sys.stderr)
        return EXIT_USAGE
    moves = [organizer.Move(Path(m["src"]), Path(m["dst"])) for m in run["moves"]]
    restored, skipped = organizer.undo(moves)
    journal.remove(run["id"])
    print(ui.green(f"Restored {len(restored)} of {len(moves)} files") + ui.dim(f"  (run #{run['id']}, {run['kind']})"))
    for m, why in skipped:
        print(ui.yellow(f"  skipped {m.dst.name}: {why}"))
    return EXIT_FAIL if skipped else EXIT_OK


def cmd_history(args: argparse.Namespace) -> int:
    runs = journal.load()
    if not runs:
        print(ui.dim("No history yet."))
        return EXIT_OK
    for r in reversed(runs):
        print(f"#{r['id']:<3} {r['time']}  {r['kind']:<9} {_files(len(r['moves'])):>10}  {ui.dim(r['root'])}")
    return EXIT_OK


def cmd_dupes(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a folder: {root}")
    dest = Path(args.move_to).expanduser().resolve() if args.move_to else None
    print(ui.dim(f"Scanning {root} ..."))
    result = dupes_mod.find_duplicates(root, args.min_size, args.include_hidden, exclude=[dest] if dest else [])
    if not result.groups:
        print(ui.green(f"No duplicates found among {result.scanned} files."))
        return EXIT_OK

    for g in result.groups[: args.top]:
        print(f"\n{ui.bold(ui.human_size(g.size))} x {len(g.paths)}   {ui.dim('wastes ' + ui.human_size(g.wasted))}")
        print(f"  {ui.green('keep')}  {_rel(g.keep, root)}")
        for p in g.extras:
            print(f"  {ui.yellow('dupe')}  {_rel(p, root)}")
    if len(result.groups) > args.top:
        print(ui.dim(f"\n... {len(result.groups) - args.top} more groups (use --top to show more)"))
    print(ui.bold(f"\n{result.extra_files} redundant {'file' if result.extra_files == 1 else 'files'} in {len(result.groups)} {'group' if len(result.groups) == 1 else 'groups'}, "
                  f"{ui.human_size(result.wasted)} wasted."))

    extras = [p for g in result.groups for p in g.extras]
    if dest:
        if not args.yes and not ui.confirm(f"Move {len(extras)} duplicates to {dest}?"):
            print("Cancelled. Nothing was moved.")
            return EXIT_FAIL
        moves = dupes_mod.quarantine(extras, dest, root)
        journal.record("dupes", root, moves)
        print(ui.green(f"Moved {len(moves)} duplicates to {dest}.") + ui.dim("  Undo with: tidy undo"))
    elif args.delete:
        print(ui.red("Deleting is permanent and cannot be undone."))
        if not args.yes and not ui.confirm(f"Delete {len(extras)} files?"):
            print("Cancelled. Nothing was deleted.")
            return EXIT_FAIL
        removed, errors = dupes_mod.delete(extras)
        print(ui.green(f"Deleted {removed} files, freed {ui.human_size(result.wasted)}."))
        for p, exc in errors:
            print(ui.red(f"  failed: {p}: {exc}"))
        return EXIT_FAIL if errors else EXIT_OK
    else:
        print(ui.dim("Report only. Add --move-to DIR (undoable) or --delete to clean up."))
    return EXIT_OK


def cmd_stats(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a folder: {root}")
    s = stats_mod.scan(root, args.top, args.include_hidden)
    print(ui.bold(str(root)))
    print(f"{s.files:,} {'file' if s.files == 1 else 'files'}, {ui.human_size(s.bytes)}\n")
    if not s.files:
        return EXIT_OK
    width = max(len(n) for n in s.by_category)
    for name, (count, size) in sorted(s.by_category.items(), key=lambda kv: kv[1][1], reverse=True):
        share = size / s.bytes if s.bytes else 0
        print(f"  {ui.cyan(name.ljust(width))}  {ui.bar(share)}  {_files(count):>10}  "
              f"{ui.human_size(size):>10}  {share:>4.0%}")
    if s.largest:
        print(ui.bold("\nLargest files"))
        for size, path in s.largest:
            print(f"  {ui.human_size(size):>10}  {_rel(path, root)}")
    return EXIT_OK


def cmd_watch(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a folder: {root}")
    print(ui.bold(f"Watching {root}") + ui.dim(f"  (sorting by {args.mode}, Ctrl+C to stop)"))
    try:
        while True:
            moves = organizer.plan(root, args.mode, min_age=args.settle, include_hidden=args.include_hidden)
            if moves:
                done, errors = organizer.execute(moves)
                if done:
                    journal.record("watch", root, done)
                for m in done:
                    _log(f"{m.src.name}  {ui.arrow()}  {ui.dim(_rel(m.dst, root))}")
                for m, exc in errors:
                    _log(ui.red(f"failed: {m.src.name}: {exc}"))
            if args.once:
                return EXIT_OK
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(ui.dim("\nStopped."))
        return EXIT_OK


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tidy",
        description="Organize messy folders, find duplicates, see where your space went. Every move can be undone.",
    )
    p.add_argument("--version", action="version", version=f"tidy {__version__}")
    p.add_argument("--no-color", action="store_true", help="turn off colored output")
    sub = p.add_subparsers(dest="command", metavar="<command>", required=True)

    def add(name: str, func, help_: str, with_path: bool = True) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_, description=help_)
        if with_path:
            sp.add_argument("path", nargs="?", default=".", help="folder to work on (default: current folder)")
        sp.set_defaults(func=func)
        return sp

    org = add("organize", cmd_organize, "sort loose files into folders")
    org.add_argument("-m", "--mode", choices=organizer.MODES, default="type",
                     help="type: Images/Documents/...  date: 2026/09  ext: pdf/jpg/...  (default: type)")
    org.add_argument("-n", "--dry-run", action="store_true", help="show the plan, move nothing")
    org.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    org.add_argument("--include-hidden", action="store_true", help="also move dotfiles")

    add("undo", cmd_undo, "revert the last change (or a specific run)", with_path=False) \
        .add_argument("--id", type=int, help="run id from `tidy history` (default: latest)")
    add("history", cmd_history, "list past runs", with_path=False)

    dup = add("dupes", cmd_dupes, "find files with identical content")
    dup.add_argument("--min-size", type=parse_size, default=1, metavar="SIZE", help="ignore smaller files, e.g. 100KB")
    dup.add_argument("--top", type=int, default=20, help="groups to display (default: 20)")
    dup.add_argument("--include-hidden", action="store_true")
    dup.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    action = dup.add_mutually_exclusive_group()
    action.add_argument("--move-to", metavar="DIR", help="move duplicates to DIR (undoable)")
    action.add_argument("--delete", action="store_true", help="delete duplicates permanently")

    st = add("stats", cmd_stats, "show disk usage by file type and the largest files")
    st.add_argument("--top", type=int, default=10, help="how many large files to list (default: 10)")
    st.add_argument("--include-hidden", action="store_true")

    w = add("watch", cmd_watch, "keep a folder tidy automatically (e.g. Downloads)")
    w.add_argument("-m", "--mode", choices=organizer.MODES, default="type")
    w.add_argument("--interval", type=float, default=5.0, help="seconds between checks (default: 5)")
    w.add_argument("--settle", type=float, default=10.0,
                   help="only move files untouched for this many seconds (default: 10)")
    w.add_argument("--include-hidden", action="store_true")
    w.add_argument("--once", action="store_true", help="run a single pass and exit")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_color:
        ui.set_color(False)
    try:
        return args.func(args)
    except NotADirectoryError as exc:
        print(ui.red(f"error: {exc}"), file=sys.stderr)
        return EXIT_USAGE
    except PermissionError as exc:
        print(ui.red(f"error: permission denied: {exc.filename}"), file=sys.stderr)
        return EXIT_FAIL
    except BrokenPipeError:  # e.g. `tidy stats | head`
        try:
            sys.stdout.close()
        except Exception:
            pass
        return EXIT_OK
    except KeyboardInterrupt:
        print(ui.dim("\nInterrupted."), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
