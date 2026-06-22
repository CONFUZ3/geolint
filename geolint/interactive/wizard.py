"""
Guided wizard for GeoLint.

Walks the user through a fixed five-step flow — load, validate, set CRS, apply
geometry fixes and save — built on top of the UI-agnostic
:class:`~geolint.interactive.session.GeoLintSession` and the shared rendering
helpers in :mod:`geolint.interactive.ui`.

All prompting goes through small input helpers (:func:`_ask`, :func:`_confirm`,
:func:`_choose`) that use prompt_toolkit when attached to a TTY and fall back to
builtin ``input()`` otherwise, so the whole flow can be driven from piped input
in tests.
"""

import sys
from typing import List, Optional

from geolint.interactive import ui
from geolint.interactive.session import GeoLintSession, SessionError


# --------------------------------------------------------------- input helpers
def _ask(message: str, default: Optional[str] = None, completer=None) -> str:
    """
    Prompt for a line of text.

    Uses prompt_toolkit's ``prompt()`` (imported lazily) when stdin is a TTY so
    completion and editing work; otherwise falls back to builtin ``input()`` for
    scripting. The result is stripped; an empty answer returns ``default`` when
    one was given.
    """
    suffix = f" [{default}]" if default else ""
    prompt_text = f"{message}{suffix}: "

    if sys.stdin.isatty():
        from prompt_toolkit import prompt as pt_prompt

        answer = pt_prompt(prompt_text, completer=completer)
    else:
        answer = input(prompt_text)

    answer = answer.strip()
    if not answer and default is not None:
        return default
    return answer


def _confirm(message: str, default: bool = True) -> bool:
    """Yes/no prompt built on :func:`_ask` (empty answer uses ``default``)."""
    hint = "Y/n" if default else "y/N"
    answer = _ask(f"{message} ({hint})").strip().lower()
    if not answer:
        return default
    if answer in ("y", "yes"):
        return True
    if answer in ("n", "no"):
        return False
    # Anything unrecognised falls back to the default rather than looping.
    return default


def _choose(message: str, options: List[str], default_index: int = 0) -> int:
    """
    Print a numbered menu and return the chosen index.

    Re-asks on invalid input. An empty answer selects ``default_index``.
    """
    while True:
        ui.console.print(f"[bold]{message}[/]")
        for i, option in enumerate(options, start=1):
            marker = " [dim](default)[/]" if i - 1 == default_index else ""
            ui.console.print(f"  [cyan]{i}[/]) {option}{marker}")
        answer = _ask("Choice", default=str(default_index + 1))
        try:
            index = int(answer) - 1
        except ValueError:
            ui.warn("Please enter a number.")
            continue
        if 0 <= index < len(options):
            return index
        ui.warn(f"Please enter a number between 1 and {len(options)}.")


# --------------------------------------------------------------- wizard steps
def _path_completer():
    """Return a PathCompleter when on a TTY, else None (scripting fallback)."""
    if not sys.stdin.isatty():
        return None
    from prompt_toolkit.completion import PathCompleter

    return PathCompleter()


def _step_load(session: GeoLintSession, initial_path: Optional[str]) -> bool:
    """Step 1/5 — load a dataset. Returns True on success, False to abort."""
    ui.console.rule("Step 1/5 — Load")
    for _ in range(3):
        path = _ask("File path", default=initial_path, completer=_path_completer())
        if not path:
            ui.error("A file path is required.")
            continue
        try:
            with ui.status("Loading..."):
                summary = session.load(path)
        except SessionError as exc:
            ui.error(str(exc))
            continue
        ui.render_summary(summary)
        return True
    ui.error("Could not load a dataset.")
    return False


def _step_validate(session: GeoLintSession) -> bool:
    """Step 2/5 — validate. Returns True to continue, False to stop."""
    ui.console.rule("Step 2/5 — Validate")
    with ui.status("Validating..."):
        report = session.validate()
    ui.render_validation(report)
    if not _confirm("Continue?", default=True):
        ui.info("Stopped.")
        return False
    return True


def _step_crs(session: GeoLintSession) -> None:
    """Step 3/5 — set or reproject the CRS. Never aborts the wizard."""
    ui.console.rule("Step 3/5 — CRS")
    if session.gdf.crs is None:
        ui.warn("No CRS set.")
        ui.render_crs_suggestions(session.infer_crs())
        crs = _ask("Assign which CRS (e.g. EPSG:4326), blank to skip")
        if crs:
            try:
                with ui.status("Assigning CRS..."):
                    session.assign_crs(crs)
                ui.success(f"Assigned CRS {crs}")
            except SessionError as exc:
                ui.error(str(exc))
        return

    choice = _choose(
        "Target CRS",
        [
            "Keep current",
            "EPSG:4326 (WGS84)",
            "EPSG:3857 (Web Mercator)",
            "Custom EPSG",
        ],
    )
    if choice == 0:
        return
    if choice == 1:
        target = "EPSG:4326"
    elif choice == 2:
        target = "EPSG:3857"
    else:
        code = _ask("Custom EPSG code (e.g. 32633)")
        if not code:
            ui.info("No CRS entered; keeping current.")
            return
        target = code if code.upper().startswith("EPSG:") else f"EPSG:{code}"

    try:
        with ui.status("Reprojecting..."):
            report = session.reproject(target)
        ui.success(f"Reprojected -> EPSG:{report['target_crs']['epsg']}")
    except SessionError as exc:
        ui.error(str(exc))


def _step_fixes(session: GeoLintSession) -> None:
    """Step 4/5 — apply geometry fixes chosen by the user."""
    ui.console.rule("Step 4/5 — Fixes")
    before = session.health_score()

    kwargs = {
        "fix_invalid": _confirm("Fix invalid geometries?", default=True),
        "remove_empty": _confirm("Remove empty geometries?", default=True),
        "remove_duplicates": _confirm("Remove duplicate geometries?", default=False),
        "clean_vertices": _confirm("Clean redundant vertices?", default=False),
        "normalize_winding_order": _confirm("Normalize winding order?", default=False),
        "do_explode_multipart": _confirm("Explode multipart?", default=False),
    }
    if _confirm("Simplify geometries?", default=False):
        kwargs["simplify"] = True
        kwargs["simplify_tolerance"] = float(_ask("Tolerance", default="0.001"))

    with ui.status("Applying fixes..."):
        session.fix(**kwargs)
    after = session.health_score()
    ui.success(f"Applied fixes — health {before} -> {after}")


def _step_save(session: GeoLintSession) -> None:
    """Step 5/5 — write the cleaned dataset to disk."""
    ui.console.rule("Step 5/5 — Save")
    for attempt in range(2):
        out = _ask("Output path", default="cleaned.gpkg", completer=_path_completer())
        fmt_idx = _choose(
            "Output format",
            ["Infer from extension", "gpkg", "geojson", "shp", "parquet"],
        )
        fmt = None if fmt_idx == 0 else ["", "gpkg", "geojson", "shp", "parquet"][fmt_idx]
        try:
            with ui.status("Saving..."):
                path = session.save(out, fmt)
            ui.success(f"Wrote {path}")
            return
        except SessionError as exc:
            ui.error(str(exc))
            if attempt == 0:
                ui.hint("Let's try again.")


# ------------------------------------------------------------------ entrypoint
def run_wizard(initial_path: Optional[str] = None) -> int:
    """Run the guided flow. Returns 0 on success, 1 on abort/cancel."""
    session = GeoLintSession()
    ui.banner()

    try:
        if not _step_load(session, initial_path):
            return 1
        if not _step_validate(session):
            return 1
        _step_crs(session)
        _step_fixes(session)
        _step_save(session)

        ui.console.rule("Done")
        ui.render_summary(session.summary())
        return 0
    except (KeyboardInterrupt, EOFError):
        ui.warn("Wizard cancelled.")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(run_wizard())
