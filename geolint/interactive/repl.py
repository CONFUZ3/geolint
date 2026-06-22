"""
Interactive REPL shell for GeoLint.

Provides a small command loop on top of the UI-agnostic
:class:`~geolint.interactive.session.GeoLintSession`. The dispatch core,
:func:`handle_line`, is pure (no terminal I/O) so it can be driven directly in
tests and from piped input; :func:`run_repl` wraps it with prompt_toolkit when
attached to a TTY and falls back to plain ``input()`` for scripting.
"""

import argparse
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from geolint.interactive import ui
from geolint.interactive.session import GeoLintSession, SessionError

# Command name -> short help string. Used for /help and tab-completion.
COMMANDS: Dict[str, str] = {
    "load": "load <path>            load and validate a dataset",
    "info": "info                   show structural facts about the dataset",
    "check": "check                  validate the current dataset",
    "validate": "validate               alias for check",
    "infer-crs": "infer-crs              suggest a CRS for the dataset",
    "assign-crs": "assign-crs <crs>       set the CRS without reprojecting",
    "reproject": "reproject <crs>        reproject coordinates to <crs>",
    "fix": "fix [flags]            run geometry fixes (run 'fix --help')",
    "save": "save <path> [--format]  write the dataset to disk ('save --help')",
    "reset": "reset                  revert to the originally loaded dataset",
    "status": "status                 show a compact state summary",
    "health": "health                 show the health score",
    "help": "help                   list available commands",
    "quit": "quit                   exit the session",
    "exit": "exit                   alias for quit",
}

# Aliases mapped to their canonical command for dispatch.
_ALIASES = {
    "validate": "check",
    "?": "help",
    "exit": "quit",
}


class _ArgparseError(ValueError):
    """Raised instead of exiting when an argparse parser hits a bad argument."""


def _strip_quotes(token: str) -> str:
    """Drop a single matching pair of surrounding quotes from a token."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _split_line(line: str) -> List[str]:
    """
    Tokenize a command line, keeping Windows paths intact.

    On Windows the default POSIX ``shlex`` treats backslashes as escapes, which
    would corrupt paths like ``C:\\data\\a.gpkg``. There we split in non-POSIX
    mode (backslashes preserved) and strip any surrounding quotes ourselves, so
    both ``load C:\\data\\a.gpkg`` and ``load "C:\\my data\\a.gpkg"`` work.
    """
    posix = os.name != "nt"
    tokens = shlex.split(line, posix=posix)
    if not posix:
        tokens = [_strip_quotes(token) for token in tokens]
    return tokens


def _wants_help(args: List[str]) -> bool:
    """True if the argument list asks for help (``--help`` / ``-h``)."""
    return "--help" in args or "-h" in args


def _build_fix_parser() -> argparse.ArgumentParser:
    """Parser for ``fix`` flags that raises instead of calling ``sys.exit``."""
    parser = argparse.ArgumentParser(
        prog="fix",
        add_help=False,
        description="Run geometry fixes on the loaded dataset.",
    )
    parser.add_argument(
        "--no-fix-invalid",
        action="store_true",
        help="do not repair invalid geometries (on by default)",
    )
    parser.add_argument(
        "--no-remove-empty",
        action="store_true",
        help="do not drop empty geometries (on by default)",
    )
    parser.add_argument(
        "--remove-duplicates",
        action="store_true",
        help="remove duplicate geometries",
    )
    parser.add_argument(
        "--clean-vertices",
        action="store_true",
        help="remove redundant / collinear vertices",
    )
    parser.add_argument(
        "--normalize-winding",
        action="store_true",
        help="normalize polygon winding order (RFC 7946)",
    )
    parser.add_argument(
        "--explode-multipart",
        action="store_true",
        help="split multipart geometries into single parts",
    )
    parser.add_argument(
        "--simplify",
        type=float,
        default=None,
        metavar="TOL",
        help="simplify geometries with the given tolerance",
    )

    def _raise(message: str) -> None:
        raise _ArgparseError(message)

    parser.error = _raise  # type: ignore[assignment]
    return parser


def _parse_fix_opts(tokens: List[str]) -> Dict[str, Any]:
    """Translate ``fix`` flag tokens into process_geometries kwargs."""
    args = _build_fix_parser().parse_args(tokens)
    opts: Dict[str, Any] = {
        "fix_invalid": not args.no_fix_invalid,
        "remove_empty": not args.no_remove_empty,
        "remove_duplicates": args.remove_duplicates,
        "clean_vertices": args.clean_vertices,
        "normalize_winding_order": args.normalize_winding,
        "do_explode_multipart": args.explode_multipart,
    }
    if args.simplify is not None:
        opts["simplify"] = True
        opts["simplify_tolerance"] = args.simplify
    return opts


def _build_save_parser() -> argparse.ArgumentParser:
    """Parser for ``save`` flags that raises instead of calling ``sys.exit``."""
    parser = argparse.ArgumentParser(
        prog="save",
        add_help=False,
        description="Write the current dataset to disk.",
    )
    parser.add_argument("path", nargs="?", default=None, help="output file path")
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["gpkg", "geojson", "shp", "parquet"],
        default=None,
        help="output format (default: infer from the path extension)",
    )

    def _raise(message: str) -> None:
        raise _ArgparseError(message)

    parser.error = _raise  # type: ignore[assignment]
    return parser


def _print_help() -> None:
    """List the available commands and their help strings."""
    ui.console.print("[bold]commands:[/]")
    for name in COMMANDS:
        if name in _ALIASES:
            continue
        ui.console.print("  " + COMMANDS[name])
    ui.console.print(
        "[dim]aliases: validate=check, ?=help, exit=quit. "
        "A leading '/' is optional on every command.[/]"
    )


def handle_line(session: GeoLintSession, line: str) -> bool:
    """
    Parse and execute a single command line against ``session``.

    Pure dispatch: renders through :mod:`ui`, performs no prompt I/O. Returns
    True to keep the loop running and False to quit. Any SessionError or other
    exception is caught and surfaced via :func:`ui.error`, and the loop is kept
    alive so a bad command can never crash the REPL.
    """
    try:
        tokens = _split_line(line)
    except ValueError as exc:
        ui.error(f"could not parse line: {exc}")
        return True

    if not tokens:
        return True

    cmd = tokens[0].lower()
    if cmd.startswith("/"):
        cmd = cmd[1:]
    cmd = _ALIASES.get(cmd, cmd)
    args = tokens[1:]

    try:
        if cmd == "load":
            if not args:
                ui.error("usage: load <path>")
                return True
            with ui.status("Loading..."):
                result = session.load(args[0])
            ui.render_summary(result)

        elif cmd == "info":
            ui.render_info(session.info())

        elif cmd == "check":
            with ui.status("Validating..."):
                report = session.validate()
            ui.render_validation(report)

        elif cmd == "infer-crs":
            ui.render_crs_suggestions(session.infer_crs())

        elif cmd == "assign-crs":
            if not args:
                ui.error("usage: assign-crs <crs>")
                return True
            session.assign_crs(args[0])
            ui.success(f"Assigned CRS {args[0]}")

        elif cmd == "reproject":
            if not args:
                ui.error("usage: reproject <crs>")
                return True
            with ui.status("Reprojecting..."):
                report = session.reproject(args[0])
            ui.success(f"Reprojected -> EPSG:{report['target_crs']['epsg']}")

        elif cmd == "fix":
            if _wants_help(args):
                ui.console.print(_build_fix_parser().format_help().rstrip())
                return True
            try:
                opts = _parse_fix_opts(args)
            except _ArgparseError as exc:
                ui.error(f"fix: {exc}")
                return True
            with ui.status("Fixing geometries..."):
                report = session.fix(**opts)
            final = report.get("final_count")
            ui.success(f"Applied fixes; {final} feature(s) remain")
            ui.render_health(session.health_score())

        elif cmd == "save":
            if _wants_help(args):
                ui.console.print(_build_save_parser().format_help().rstrip())
                return True
            try:
                parsed = _build_save_parser().parse_args(args)
            except _ArgparseError as exc:
                ui.error(f"save: {exc}")
                return True
            if not parsed.path:
                ui.error("usage: save <path> [--format FMT]")
                return True
            out = session.save(parsed.path, parsed.fmt)
            ui.success(f"Wrote {out}")

        elif cmd == "reset":
            session.reset()
            ui.success("Reverted to originally loaded dataset")

        elif cmd == "status":
            ui.render_summary(session.summary())

        elif cmd == "health":
            ui.render_health(session.health_score())

        elif cmd in ("help", "?"):
            _print_help()

        elif cmd == "quit":
            return False

        else:
            ui.error(f"unknown command: {cmd}. Type /help for commands.")

    except SessionError as exc:
        ui.error(str(exc))
    except Exception as exc:  # never let a bad command crash the loop
        ui.error(str(exc))

    return True


def _make_prompt_session():
    """
    Build a prompt_toolkit PromptSession with history and completion.

    Imports prompt_toolkit lazily so that importing this module never requires
    a terminal. History is persisted to ``~/.geolint_history`` when possible,
    falling back to in-memory history on any failure.
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import NestedCompleter, PathCompleter
    from prompt_toolkit.history import FileHistory, InMemoryHistory

    try:
        history = FileHistory(str(Path.home() / ".geolint_history"))
    except Exception:
        history = InMemoryHistory()

    completion_map: Dict[str, Any] = {name: None for name in COMMANDS}
    completion_map["load"] = PathCompleter()
    completion_map["save"] = PathCompleter()

    return PromptSession(
        history=history,
        auto_suggest=AutoSuggestFromHistory(),
        completer=NestedCompleter.from_nested_dict(completion_map),
    )


def run_repl(initial_path: Optional[str] = None) -> int:
    """Run the interactive REPL loop. Always returns 0 on normal exit."""
    session = GeoLintSession()
    ui.banner()
    ui.hint("Type /help for commands, /quit to exit.")

    if initial_path:
        handle_line(session, "load " + shlex.quote(str(initial_path)))

    interactive = sys.stdin.isatty()
    pt = _make_prompt_session() if interactive else None

    while True:
        try:
            line = pt.prompt("geolint> ") if pt else input("geolint> ")
        except KeyboardInterrupt:  # Ctrl-C: cancel current line, keep going
            continue
        except EOFError:  # Ctrl-D / end of piped input: quit
            break
        if not handle_line(session, line):
            break

    ui.info("bye")
    return 0


if __name__ == "__main__":
    sys.exit(run_repl())
