import argparse
import json
import sys
from pathlib import Path

from geolint.core.batch import BatchProcessor
from geolint.core.crs import get_crs_info, infer_crs
from geolint.core.geometry import process_geometries
from geolint.core.io import save_dataset, FORMAT_EXTENSIONS
from geolint.core.report import (
    generate_batch_report,
    generate_report,
    save_report,
)
from geolint.core.transform import reproject_dataset
from geolint.core.validation import run_multilayer_validation, run_validation


def _parse_pairs(items):
    """Parse repeatable 'LAYER_A:LAYER_B' rule arguments into (a, b) tuples."""
    pairs = []
    for item in (items or []):
        if ":" not in item:
            raise ValueError(f"expected LAYER_A:LAYER_B, got: {item}")
        a, b = item.split(":", 1)
        pairs.append((a.strip(), b.strip()))
    return pairs


def _multilayer_requested(args: argparse.Namespace, input_path: Path) -> bool:
    """True when multi-layer validation is explicitly requested or auto-detected."""
    if (args.against or args.must_not_overlap or args.must_be_covered_by
            or args.coverage_gaps or args.coverage_gaps_all or args.layer):
        return True
    if input_path.suffix.lower() in (".gpkg", ".sqlite", ".gdb"):
        try:
            from geolint.core.validation import list_layers
            return len(list_layers(input_path)) > 1
        except Exception:
            return False
    return False


def _print_findings(findings: list, suppressed: int = 0) -> None:
    if not findings:
        msg = "No findings."
        if suppressed:
            msg += f" ({suppressed} suppressed by baseline)"
        print(f"\n{msg}")
        return
    counts = {'error': 0, 'warning': 0, 'info': 0}
    for f in findings:
        counts[f.get('severity', 'warning')] = counts.get(f.get('severity', 'warning'), 0) + 1
    print(
        f"\nFindings: {counts['error']} error, {counts['warning']} warning, "
        f"{counts['info']} info"
        + (f" ({suppressed} suppressed)" if suppressed else "")
    )
    for f in findings:
        print(f"  [{f.get('severity', 'warning'):7s}] {f.get('check_id')}: {f.get('message')}")


def _print_conformance(conformance: dict) -> None:
    if not conformance or conformance.get("error"):
        return
    status = "CONFORMANT" if conformance.get("conformant") else "NON-CONFORMANT"
    print(f"\nConformance [{conformance.get('profile')}]: {status}")
    for res in conformance.get("checks", {}).values():
        print(f"  [{res['status']:4s}] {res['title']}: {res['message']}")


def _print_multilayer(report: dict) -> None:
    inter = report.get("inter_layer", {})
    print("Multi-layer validation completed.")
    print(f"  Layers ({inter.get('layer_count', 0)}): {', '.join(inter.get('layers', []))}")

    alignment = inter.get("crs_alignment", {})
    if alignment.get("aligned"):
        print(f"  CRS alignment: OK (target {alignment.get('target_crs')})")
    else:
        print(f"  CRS alignment: BLOCKED - {alignment.get('reason')}")
        print("  (inter-layer checks skipped; fix CRS or use --crs-policy align)")

    checks = inter.get("checks", {})
    for name, res in (checks.get("coverage_gaps") or {}).items():
        if res.get("error"):
            print(f"  coverage gaps [{name}]: error - {res['error']}")
        elif res.get("applicable"):
            print(f"  coverage gaps [{name}]: {res.get('gap_count', 0)}")
    for res in (checks.get("must_not_overlap") or []):
        label = f"{res.get('layer_a')} x {res.get('layer_b')}"
        if res.get("error"):
            print(f"  overlap [{label}]: error - {res['error']}")
        else:
            print(f"  overlap [{label}]: {res.get('overlap_pair_count', 0)} pairs")
    for res in (checks.get("must_be_covered_by") or []):
        label = f"{res.get('layer_a')} in {res.get('layer_b')}"
        if res.get("error"):
            print(f"  covered-by [{label}]: error - {res['error']}")
        else:
            print(f"  covered-by [{label}]: {res.get('uncovered_count', 0)} uncovered")


def _cmd_validate(args: argparse.Namespace) -> int:
    from geolint.core.validation import is_remote

    remote = is_remote(args.input)
    input_path = Path(args.input)
    if not remote and not input_path.exists():
        print(f"Error: input not found: {input_path}")
        return 1

    if not remote and _multilayer_requested(args, input_path):
        return _cmd_validate_multilayer(args, input_path)

    try:
        from geolint.core.config import load_config
        from geolint.core.findings import apply_baseline, exit_code, load_baseline, write_baseline

        config = load_config(Path(args.config) if args.config else None)

        source = args.input if remote else input_path
        report, gdf = run_validation(source, profile=args.profile, config=config)
        crs_info = get_crs_info(gdf) if (not gdf.empty and gdf.crs is not None) else None
        full_report = generate_report(report, crs_info=crs_info)

        findings = report.get("findings", [])

        # Write a baseline of the current findings, then exit. A hard load error
        # must still fail rather than silently writing an empty baseline.
        if args.write_baseline:
            if full_report.get("errors") or report.get("validation", {}).get("status") == "error":
                print(report["errors"][0] if report.get("errors")
                      else "Cannot write baseline: dataset failed to load")
                return 1
            write_baseline(args.write_baseline, findings)
            print(f"Baseline written to {args.write_baseline} ({len(findings)} findings)")
            return 0

        suppressed = 0
        if args.baseline:
            findings, suppressed = apply_baseline(findings, load_baseline(args.baseline))

        if args.json:
            print(json.dumps(full_report, indent=2, default=str))
        else:
            print("Validation completed.")
            print(report)
            if args.profile:
                _print_conformance(full_report.get("conformance", {}))
            _print_findings(findings, suppressed)
        if args.report:
            out = Path(args.report)
            save_report(full_report, out)
            print(f"Report written to {out}")

        # CI-native outputs.
        if args.sarif:
            from geolint.core.sarif import to_sarif
            sarif = to_sarif(findings, args.input)
            sarif_path = Path(args.sarif)
            sarif_path.parent.mkdir(parents=True, exist_ok=True)
            with open(sarif_path, "w", encoding="utf-8") as fh:
                json.dump(sarif, fh, indent=2)
            print(f"SARIF written to {sarif_path}")
        if args.error_layer and not gdf.empty:
            from geolint.core.error_layer import write_error_layer
            written = write_error_layer(gdf, report, args.error_layer)
            print(f"Error layer written to {written}")

        # Exit-code policy: hard errors always fail (legacy); severity gating
        # engages only when a config file is present or --strict is set.
        if full_report.get("errors") or report.get("validation", {}).get("status") == "error":
            return 1
        nonconformant = (
            args.profile
            and full_report.get("conformance", {}).get("conformant") is False
        )
        if args.fail_on_nonconformance and nonconformant:
            return 1
        gate = (config.source is not None) or args.strict
        if gate:
            return exit_code(findings, strict=args.strict)
        return 0
    except Exception as exc:
        print(f"Validation failed: {exc}")
        return 1


def _cmd_validate_multilayer(args: argparse.Namespace, input_path: Path) -> int:
    try:
        for extra in (args.against or []):
            if not Path(extra).exists():
                print(f"Error: input not found: {extra}")
                return 1
        coverage_layers = None if args.coverage_gaps_all else (args.coverage_gaps or [])
        inputs = ([str(input_path)] + list(args.against)) if args.against else input_path

        report, _ = run_multilayer_validation(
            inputs,
            layers=args.layer,
            crs_policy=args.crs_policy,
            target_crs=args.target_crs,
            coverage_layers=coverage_layers,
            must_not_overlap=_parse_pairs(args.must_not_overlap),
            must_be_covered_by=_parse_pairs(args.must_be_covered_by),
            force=args.force,
        )

        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            _print_multilayer(report)
        if args.report:
            save_report(report, Path(args.report))
            print(f"Report written to {Path(args.report)}")
        return 0
    except Exception as exc:
        print(f"Validation failed: {exc}")
        return 1


def _cmd_fix(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input not found: {input_path}")
        return 1
    try:
        report, gdf = run_validation(input_path)
        if gdf.empty and report.get("errors"):
            print(report["errors"][0])
            return 1

        if args.assign_crs:
            gdf = gdf.set_crs(args.assign_crs, allow_override=True)

        transform_report = None
        if args.target_crs:
            gdf, transform_report = reproject_dataset(gdf, args.target_crs)
            if transform_report.get("transformed") is False:
                print(f"Reprojection failed: {transform_report.get('error')}")
                return 1

        gdf, geom_report = process_geometries(
            gdf,
            fix_invalid=args.fix_invalid,
            remove_empty=args.remove_empty,
            remove_duplicates=args.remove_duplicates,
            clean_vertices=args.clean_vertices,
            normalize_winding_order=args.normalize_winding,
            do_explode_multipart=args.explode_multipart,
            simplify=(args.simplify is not None),
            simplify_tolerance=(args.simplify if args.simplify is not None else 0.001),
        )

        out_path = save_dataset(gdf, args.output, args.format)

        full_report = generate_report(
            report,
            crs_info=get_crs_info(gdf),
            geometry_report=geom_report,
            transform_report=transform_report,
        )

        if args.json:
            print(json.dumps(full_report, indent=2, default=str))
        else:
            print(f"Features written: {len(gdf)}")
            print(f"Output path: {out_path}")
            print("Geometry operations performed:")
            operations = geom_report.get("operations", [])
            if operations:
                for op in operations:
                    print(f"  - {op}")
            else:
                print("  (none)")

        if args.report:
            save_report(full_report, Path(args.report))
            print(f"Report written to {Path(args.report)}")

        return 0
    except Exception as exc:
        print(f"Fix failed: {exc}")
        return 1


def _cmd_info(args: argparse.Namespace) -> int:
    if getattr(args, "list_profiles", False):
        from geolint.core.profiles import list_profiles
        profiles = list_profiles()
        if args.json:
            print(json.dumps(profiles, indent=2))
        else:
            print("Available conformance profiles:")
            for p in profiles:
                print(f"  {p['name']:12s} {p['title']} ({p['check_count']} checks)")
        return 0

    if not args.input:
        print("Error: input is required (or use --list-profiles)")
        return 1

    from geolint.core.validation import is_remote
    remote = is_remote(args.input)
    input_path = Path(args.input)
    if not remote and not input_path.exists():
        print(f"Error: input not found: {input_path}")
        return 1

    # Fast path: count + bbox via DuckDB without materialising a GeoDataFrame.
    if getattr(args, "fast", False):
        from geolint.core.duckdb_backend import can_handle, quick_stats
        if can_handle(args.input):
            stats = quick_stats(args.input)
            if args.json:
                print(json.dumps(stats, indent=2, default=str))
            else:
                print("Fast info (DuckDB):")
                print(f"  Feature count: {stats['feature_count']}")
                print(f"  Bounds:        {stats['bbox']}")
            return 0
        print("Fast engine unavailable (needs duckdb + a .parquet input); using full read.")

    source = args.input if remote else input_path
    try:
        report, gdf = run_validation(source)
        if gdf.empty and report.get("errors"):
            print(report["errors"][0])
            return 1

        geometry_types = (
            sorted(set(gdf.geom_type.dropna().unique())) if not gdf.empty else []
        )
        info = {
            "file_name": report.get("file_name"),
            "feature_count": len(gdf),
            "column_count": len(gdf.columns),
            "geometry_types": geometry_types,
            "bounds": list(gdf.total_bounds) if not gdf.empty else None,
            "crs": get_crs_info(gdf),
        }

        suggestions = None
        if args.infer_crs:
            suggestions = infer_crs(gdf)
            info["crs_suggestions"] = suggestions

        if args.json:
            print(json.dumps(info, indent=2, default=str))
        else:
            print("File information:")
            print(f"  File name:     {info['file_name']}")
            print(f"  Feature count: {info['feature_count']}")
            print(f"  Column count:  {info['column_count']}")
            print(f"  Geometry types: {', '.join(geometry_types) if geometry_types else '(none)'}")
            print(f"  Bounds:        {info['bounds']}")
            print(f"  CRS:           {info['crs']}")
            if args.infer_crs:
                if suggestions:
                    print("  CRS suggestions:")
                    for s in suggestions:
                        epsg = s.get("epsg")
                        name = s.get("name")
                        confidence = s.get("confidence", 0)
                        print(
                            f"    EPSG:{epsg} - {name} ({confidence * 100}% confidence)"
                        )
                else:
                    print("  CRS already present; nothing to infer.")

        return 0
    except Exception as exc:
        print(f"Info failed: {exc}")
        return 1


def _cmd_batch(args: argparse.Namespace) -> int:
    try:
        processor = BatchProcessor()
        individual_reports = []
        for p in args.inputs:
            path = Path(p)
            if not path.exists():
                print(f"Error: input not found: {path}")
                return 1
            report, gdf = run_validation(path)
            processor.add_dataset(gdf, path.name)
            crs_info = (
                get_crs_info(gdf)
                if (not gdf.empty and gdf.crs is not None)
                else None
            )
            individual_reports.append(generate_report(report, crs_info=crs_info))

        results = processor.process_batch(
            unify_crs=args.unify_crs,
            target_crs=args.target_crs,
            crs_strategy=args.crs_strategy,
            fix_geometries=args.fix_geometries,
            merge_datasets=args.merge,
        )

        if not results.get("success"):
            print(f"Batch processing failed: {results.get('error', 'Unknown error')}")
            return 1

        outdir = Path(args.output)
        outdir.mkdir(parents=True, exist_ok=True)
        ext = FORMAT_EXTENSIONS[args.format]
        written = []

        if (
            args.merge
            and results.get("final_dataset") is not None
            and not results["final_dataset"].empty
        ):
            written.append(
                save_dataset(
                    results["final_dataset"], outdir / f"merged{ext}", args.format
                )
            )
        else:
            for ds in processor.datasets:
                if ds["gdf"].empty:
                    continue
                stem = Path(ds["name"]).stem
                written.append(
                    save_dataset(ds["gdf"], outdir / f"{stem}{ext}", args.format)
                )

        if args.report:
            batch_report = generate_batch_report(results, individual_reports)
            save_report(batch_report, Path(args.report))

        print("Batch processing succeeded.")
        for w in written:
            print(f"  Written: {w}")
        return 0
    except Exception as exc:
        print(f"Batch processing failed: {exc}")
        return 1


def _cmd_web(args: argparse.Namespace) -> int:
    import importlib.util

    if importlib.util.find_spec("streamlit") is None:
        print(
            "The web UI requires extra dependencies that are not installed.\n"
            'Install them with:  pip install "geolint[web]"'
        )
        return 1
    try:
        import subprocess
        import sys as _sys

        script = str(Path(__file__).resolve().parents[1] / "web" / "app.py")
        return subprocess.call([_sys.executable, "-m", "streamlit", "run", script])
    except Exception as exc:
        print(f"Failed to launch web app: {exc}")
        return 1


def _cmd_shell(args: argparse.Namespace) -> int:
    from geolint.interactive.repl import run_repl
    return run_repl(getattr(args, "input", None))


def _cmd_wizard(args: argparse.Namespace) -> int:
    from geolint.interactive.wizard import run_wizard
    return run_wizard(getattr(args, "input", None))


def precommit_app() -> None:
    """
    Validate many files at once (pre-commit friendly).

    Pre-commit passes the staged filenames as positional args. Each file is
    validated independently; the process exits non-zero if any file has an
    error-severity finding (or a warning when --strict) or fails to load.
    """
    parser = argparse.ArgumentParser(
        prog="geolint-precommit",
        description="Validate multiple geospatial files (for pre-commit / CI)",
    )
    parser.add_argument("files", nargs="*", help="Files to validate")
    parser.add_argument("--strict", action="store_true", default=False)
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--profile", default=None,
        choices=["rfc7946", "geopackage", "geoparquet"],
    )
    parsed = parser.parse_args()

    from geolint.core.config import load_config
    from geolint.core.findings import exit_code

    config = load_config(Path(parsed.config) if parsed.config else None)
    overall = 0
    for fp in parsed.files:
        path = Path(fp)
        if not path.exists():
            continue
        try:
            report, _ = run_validation(path, profile=parsed.profile, config=config)
        except Exception as exc:  # noqa: BLE001
            print(f"{fp}: validation failed: {exc}")
            overall = 1
            continue
        findings = report.get("findings", [])
        print(f"{fp}: {len(findings)} finding(s)")
        for f in findings:
            print(f"  [{f['severity']:7s}] {f['check_id']}: {f['message']}")
        if report.get("validation", {}).get("status") == "error":
            overall = 1
        gate = (config.source is not None) or parsed.strict
        if gate and exit_code(findings, strict=parsed.strict) == 1:
            overall = 1
    sys.exit(overall)


def app() -> None:
    parser = argparse.ArgumentParser(
        prog="geolint",
        description="GeoLint - Geospatial data linting and validation",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    p_validate = subparsers.add_parser("validate", help="Validate a geospatial file")
    p_validate.add_argument("input", help="Path to input file (.zip/.gpkg/.geojson)")
    p_validate.add_argument("--report", help="Optional path to write text report")
    p_validate.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report to stdout",
    )
    p_validate.add_argument(
        "--profile",
        choices=["rfc7946", "geopackage", "geoparquet"],
        default=None,
        help="Check conformance against a target spec profile",
    )
    p_validate.add_argument(
        "--fail-on-nonconformance",
        action="store_true",
        default=False,
        help="Exit non-zero when a --profile check fails (for CI gates)",
    )
    p_validate.add_argument(
        "--config",
        default=None,
        help="Path to a geolint config (geolint.toml/.geolint.yml); else auto-discovered",
    )
    p_validate.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat warning-severity findings as failures (exit non-zero)",
    )
    p_validate.add_argument(
        "--baseline",
        default=None,
        help="Suppress findings listed in this baseline file",
    )
    p_validate.add_argument(
        "--write-baseline",
        default=None,
        metavar="PATH",
        help="Write current findings to a baseline file and exit",
    )
    p_validate.add_argument(
        "--sarif",
        default=None,
        metavar="PATH",
        help="Write findings as SARIF 2.1.0 (for GitHub code scanning)",
    )
    p_validate.add_argument(
        "--error-layer",
        default=None,
        metavar="PATH",
        help="Write flagged features as a GeoJSON error layer for QGIS triage",
    )
    # Multi-layer / inter-layer options (additive; trigger multi-layer mode).
    p_validate.add_argument(
        "--layer",
        action="append",
        default=None,
        help="Select a GeoPackage layer (repeatable)",
    )
    p_validate.add_argument(
        "--against",
        action="append",
        default=None,
        help="Additional layer/file for inter-layer checks (repeatable)",
    )
    p_validate.add_argument(
        "--must-not-overlap",
        action="append",
        default=None,
        metavar="A:B",
        help="Assert layer A does not overlap layer B (repeatable)",
    )
    p_validate.add_argument(
        "--must-be-covered-by",
        action="append",
        default=None,
        metavar="A:B",
        help="Assert layer A is covered by layer B (repeatable)",
    )
    p_validate.add_argument(
        "--coverage-gaps",
        action="append",
        default=None,
        metavar="LAYER",
        help="Check a layer for coverage gaps (repeatable)",
    )
    p_validate.add_argument(
        "--coverage-gaps-all",
        action="store_true",
        default=False,
        help="Check every polygon layer for coverage gaps",
    )
    p_validate.add_argument(
        "--crs-policy",
        choices=["error", "align"],
        default="error",
        help="How to handle differing CRS across layers (default: error)",
    )
    p_validate.add_argument(
        "--target-crs",
        default=None,
        help="Target CRS for --crs-policy align (e.g. EPSG:3857)",
    )
    p_validate.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Run checks past the feature-count safety caps",
    )
    p_validate.set_defaults(func=_cmd_validate)

    p_fix = subparsers.add_parser(
        "fix", help="Repair, transform, and export a single geospatial file"
    )
    p_fix.add_argument("input", help="Path to input file (.zip/.gpkg/.geojson)")
    p_fix.add_argument("--output", "-o", required=True, help="Path to output file")
    p_fix.add_argument(
        "--format",
        "-f",
        choices=["gpkg", "geojson", "shp", "parquet"],
        default=None,
        help="Output format (default: inferred from output extension)",
    )
    p_fix.add_argument(
        "--assign-crs",
        help="Assign CRS without reprojecting (e.g. EPSG:4326)",
    )
    p_fix.add_argument("--target-crs", help="Reproject to this CRS (e.g. EPSG:3857)")
    p_fix.add_argument(
        "--no-fix-invalid",
        action="store_false",
        dest="fix_invalid",
        default=True,
        help="Do not fix invalid geometries",
    )
    p_fix.add_argument(
        "--no-remove-empty",
        action="store_false",
        dest="remove_empty",
        default=True,
        help="Do not remove empty geometries",
    )
    p_fix.add_argument(
        "--remove-duplicates",
        action="store_true",
        default=False,
        help="Remove duplicate geometries",
    )
    p_fix.add_argument(
        "--clean-vertices",
        action="store_true",
        default=False,
        help="Clean redundant vertices",
    )
    p_fix.add_argument(
        "--normalize-winding",
        action="store_true",
        default=False,
        help="Normalize polygon winding order",
    )
    p_fix.add_argument(
        "--explode-multipart",
        action="store_true",
        default=False,
        help="Explode multipart geometries into single parts",
    )
    p_fix.add_argument(
        "--simplify",
        type=float,
        default=None,
        help="Simplify geometries with the given tolerance",
    )
    p_fix.add_argument("--report", help="Optional path to write JSON report")
    p_fix.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report to stdout",
    )
    p_fix.set_defaults(func=_cmd_fix)

    p_info = subparsers.add_parser(
        "info", help="Inspect a geospatial file and report its properties"
    )
    p_info.add_argument(
        "input", nargs="?", default=None,
        help="Path to input file (.zip/.gpkg/.geojson)",
    )
    p_info.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )
    p_info.add_argument(
        "--infer-crs",
        action="store_true",
        help="Suggest a CRS if none is present",
    )
    p_info.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available conformance profiles and exit",
    )
    p_info.add_argument(
        "--fast",
        action="store_true",
        help="Use the DuckDB backend for a quick count/bbox (Parquet only)",
    )
    p_info.set_defaults(func=_cmd_info)

    p_batch = subparsers.add_parser("batch", help="Batch process and export multiple files")
    p_batch.add_argument("inputs", nargs="+", help="Paths to input files")
    p_batch.add_argument("--output", "-o", required=True, help="Output directory")
    p_batch.add_argument(
        "--no-unify-crs",
        action="store_false",
        dest="unify_crs",
        default=True,
        help="Do not unify CRS across datasets",
    )
    p_batch.add_argument("--target-crs", default="EPSG:4326")
    p_batch.add_argument(
        "--crs-strategy",
        choices=["manual", "use_most_common", "auto_detect"],
        default="auto_detect",
    )
    p_batch.add_argument(
        "--no-fix-geometries",
        action="store_false",
        dest="fix_geometries",
        default=True,
        help="Do not fix geometries",
    )
    p_batch.add_argument("--merge", action="store_true", default=False)
    p_batch.add_argument(
        "--format",
        "-f",
        choices=["gpkg", "geojson", "shp", "parquet"],
        default="gpkg",
        help="Output format (default: gpkg)",
    )
    p_batch.add_argument("--report", help="Optional path to write JSON batch report")
    p_batch.set_defaults(func=_cmd_batch)

    p_web = subparsers.add_parser("web", help="Launch the Streamlit web UI")
    p_web.set_defaults(func=_cmd_web)

    p_shell = subparsers.add_parser("shell", help="Start the interactive REPL shell")
    p_shell.add_argument("input", nargs="?", help="Optional file to load on startup")
    p_shell.set_defaults(func=_cmd_shell)

    p_wizard = subparsers.add_parser("wizard", help="Run the guided interactive wizard")
    p_wizard.add_argument("input", nargs="?", help="Optional file to load on startup")
    p_wizard.set_defaults(func=_cmd_wizard)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        from geolint.interactive.repl import run_repl
        sys.exit(run_repl())
    sys.exit(args.func(args))


if __name__ == "__main__":
    app()
