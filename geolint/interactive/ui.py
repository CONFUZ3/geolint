"""
Rich rendering helpers shared by the GeoLint REPL and wizard.

All output goes through the module-level :data:`console`. Functions here take
the plain dicts/lists returned by :class:`geolint.interactive.session.GeoLintSession`
and render them; they hold no state of their own.
"""

import sys
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def _make_console() -> Console:
    """
    Build the shared console, forcing UTF-8 output where possible.

    rich renders box-drawing, block and check-mark glyphs; on Windows consoles
    whose default code page is not UTF-8 (cp1252), writing those would raise
    UnicodeEncodeError. Reconfiguring the streams to UTF-8 keeps the polished
    output working in terminals, pipes and redirects alike.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return Console()


console = _make_console()

TAGLINE = "the linter & auto-formatter for maps"


# --------------------------------------------------------------------- chrome
def banner() -> None:
    """Print the session banner."""
    console.print(
        Panel.fit(
            f"[bold cyan]GeoLint[/]  ·  interactive session\n[dim]{TAGLINE}[/]",
            border_style="cyan",
        )
    )


def success(message: str) -> None:
    console.print(f"[green]✔[/] {message}")


def warn(message: str) -> None:
    console.print(f"[yellow]⚠[/] {message}")


def error(message: str) -> None:
    console.print(f"[red]✗[/] {message}")


def info(message: str) -> None:
    console.print(f"[cyan]ℹ[/] {message}")


def hint(message: str) -> None:
    console.print(f"[dim]{message}[/]")


def status(message: str):
    """Return a spinner context manager: ``with ui.status('...'):``."""
    return console.status(f"[cyan]{message}[/]", spinner="dots")


# --------------------------------------------------------------------- health
def health_color(score: Optional[float]) -> str:
    if score is None:
        return "white"
    if score >= 80:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def render_health(score: Optional[float]) -> None:
    """Render the health score as a colored bar panel."""
    if score is None:
        console.print("[dim]health: n/a[/]")
        return
    color = health_color(score)
    bar_len = 24
    filled = int(round(score / 100 * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)
    console.print(
        Panel.fit(
            f"[{color}]{bar}[/]  [bold {color}]{score:.0f}[/]/100",
            title="health score",
            border_style=color,
        )
    )


# -------------------------------------------------------------------- summary
def _crs_label(crs: Optional[str], epsg: Optional[Any]) -> str:
    label = crs or "—"
    if epsg:
        label += f" (EPSG:{epsg})"
    return label


def render_summary(summary: Dict[str, Any]) -> None:
    """Compact state view shown after load and by ``status``."""
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="dim")
    table.add_column()
    table.add_row("source", str(summary.get("source") or "—"))
    table.add_row("features", f"{summary.get('feature_count', 0):,}")
    table.add_row("CRS", _crs_label(summary.get("crs"), summary.get("epsg")))
    console.print(table)
    render_health(summary.get("health_score"))
    ops = summary.get("operations")
    if ops:
        console.print("[dim]operations:[/] " + " → ".join(ops))


def render_info(info_dict: Dict[str, Any]) -> None:
    """Detailed structural view (the ``info`` command)."""
    table = Table(show_header=False, box=None)
    table.add_column(style="dim")
    table.add_column()
    table.add_row("source", str(info_dict.get("source") or "—"))
    table.add_row("features", f"{info_dict.get('feature_count', 0):,}")
    table.add_row("columns", str(info_dict.get("column_count", 0)))
    geometry_types = info_dict.get("geometry_types") or []
    table.add_row("geometry", ", ".join(geometry_types) if geometry_types else "—")
    table.add_row("bounds", _fmt_bounds(info_dict.get("bounds")))
    crs = info_dict.get("crs") or {}
    table.add_row("CRS", _crs_label(crs.get("crs"), crs.get("epsg")))
    if crs.get("name"):
        table.add_row("CRS name", str(crs["name"]))
    if crs.get("units"):
        table.add_row("units", str(crs["units"]))
    console.print(table)


def _fmt_bounds(bounds: Optional[List[float]]) -> str:
    if not bounds:
        return "—"
    minx, miny, maxx, maxy = bounds
    return f"x [{minx:.4f}, {maxx:.4f}]  y [{miny:.4f}, {maxy:.4f}]"


# ----------------------------------------------------------------- validation
def _checks_rows(checks: Dict[str, Any]) -> List[tuple]:
    """Flatten the nested checks dict into (category, name, value, ok) rows."""
    rows: List[tuple] = []

    topology = checks.get("topology", {}) or {}
    dup = topology.get("duplicate_geometries") or {}
    if "duplicate_count" in dup:
        count = dup["duplicate_count"]
        rows.append(("topology", "duplicate geometries", count, count == 0))
    overlaps = topology.get("overlapping_polygons") or {}
    if "overlap_pair_count" in overlaps and not overlaps.get("skipped"):
        count = overlaps["overlap_pair_count"]
        rows.append(("topology", "overlapping polygons", count, count == 0))
    slivers = topology.get("slivers") or {}
    if "zero_area_polygons" in slivers or "zero_length_lines" in slivers:
        count = (slivers.get("zero_area_polygons", 0) or 0) + (
            slivers.get("zero_length_lines", 0) or 0
        )
        rows.append(("topology", "slivers / zero-area", count, count == 0))
    dup_verts = topology.get("duplicate_vertices") or {}
    if "features_with_duplicate_vertices" in dup_verts:
        count = dup_verts["features_with_duplicate_vertices"]
        rows.append(("topology", "duplicate vertices", count, count == 0))

    attributes = checks.get("attributes", {}) or {}
    id_uniq = attributes.get("id_uniqueness") or {}
    if "duplicate_count" in id_uniq:
        count = id_uniq["duplicate_count"]
        rows.append(("attributes", "ID duplicates", count, count == 0))
    null_attrs = attributes.get("null_attributes") or {}
    if "fully_null_columns" in null_attrs:
        count = len(null_attrs.get("fully_null_columns") or [])
        rows.append(("attributes", "fully-null columns", count, count == 0))
    field_names = attributes.get("shapefile_field_names") or {}
    if field_names and "error" not in field_names:
        count = (
            len(field_names.get("long_names") or [])
            + len(field_names.get("truncation_collisions") or [])
            + len(field_names.get("non_ascii_names") or [])
        )
        rows.append(("attributes", "shapefile-unsafe names", count, count == 0))

    coordinates = checks.get("coordinates", {}) or {}
    winding = coordinates.get("winding_order") or {}
    if "non_compliant_count" in winding:
        count = winding["non_compliant_count"]
        rows.append(("coordinates", "wrong winding", count, count == 0))
    coord_range = coordinates.get("coordinate_range") or {}
    if "out_of_range_count" in coord_range:
        count = coord_range["out_of_range_count"]
        rows.append(("coordinates", "out-of-range coords", count, count == 0))

    return rows


def render_validation(report: Dict[str, Any]) -> None:
    """Render the data-quality table, geometry stats, warnings and health."""
    geom = report.get("geometry_validation", {}) or {}
    geom_table = Table(title="geometry", box=None, show_header=False)
    geom_table.add_column(style="dim")
    geom_table.add_column(justify="right")
    geom_table.add_row("valid", str(geom.get("valid_count", 0)))
    geom_table.add_row("invalid", str(geom.get("invalid_count", 0)))
    geom_table.add_row("empty", str(geom.get("empty_count", 0)))
    geom_table.add_row("mixed types", "yes" if geom.get("mixed_types") else "no")
    console.print(geom_table)

    rows = _checks_rows(report.get("checks", {}) or {})
    if rows:
        checks_table = Table(title="data quality checks")
        checks_table.add_column("category", style="dim")
        checks_table.add_column("check")
        checks_table.add_column("count", justify="right")
        checks_table.add_column("status", justify="center")
        for category, name, value, ok in rows:
            badge = "[green]✔[/]" if ok else "[red]✗[/]"
            checks_table.add_row(category, name, str(value), badge)
        console.print(checks_table)

    warnings = report.get("warnings") or []
    if warnings:
        console.print("[yellow]warnings:[/]")
        for message in warnings:
            console.print(f"  [yellow]⚠[/] {message}")

    render_health(report.get("health_score"))


# ------------------------------------------------------------ crs suggestions
def render_crs_suggestions(suggestions: List[Dict[str, Any]]) -> None:
    """Render inferred CRS candidates, or a note if there are none."""
    if not suggestions:
        info("CRS already present (or none could be inferred); nothing to suggest.")
        return
    table = Table(title="CRS suggestions")
    table.add_column("EPSG")
    table.add_column("name")
    table.add_column("confidence", justify="right")
    for suggestion in suggestions:
        confidence = suggestion.get("confidence", 0) * 100
        table.add_row(
            f"EPSG:{suggestion.get('epsg')}",
            str(suggestion.get("name")),
            f"{confidence:.0f}%",
        )
    console.print(table)
