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
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input not found: {input_path}")
        return 1

    if _multilayer_requested(args, input_path):
        return _cmd_validate_multilayer(args, input_path)

    try:
        report, gdf = run_validation(input_path, profile=args.profile)
        crs_info = get_crs_info(gdf) if (not gdf.empty and gdf.crs is not None) else None
        full_report = generate_report(report, crs_info=crs_info)
        if args.json:
            print(json.dumps(full_report, indent=2, default=str))
        else:
            print("Validation completed.")
            print(report)
            if args.profile:
                _print_conformance(full_report.get("conformance", {}))
        if args.report:
            out = Path(args.report)
            save_report(full_report, out)
            print(f"Report written to {out}")

        nonconformant = (
            args.profile
            and full_report.get("conformance", {}).get("conformant") is False
        )
        if args.fail_on_nonconformance and nonconformant:
            return 1
        if full_report.get("errors") or report.get("validation", {}).get("status") == "error":
            return 1
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

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input not found: {input_path}")
        return 1
    try:
        report, gdf = run_validation(input_path)
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
