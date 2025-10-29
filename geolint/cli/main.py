import argparse
import sys
from pathlib import Path

from geolint.core.batch import BatchProcessor
from geolint.core.report import generate_report
from geolint.core.validation import run_validation


def _cmd_validate(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input not found: {input_path}")
        return 1
    try:
        report, gdf = run_validation(input_path)
        print("Validation completed.")
        print(report)
        if args.report:
            out = Path(args.report)
            out.write_text(str(report))
            print(f"Report written to {out}")
        return 0
    except Exception as exc:
        print(f"Validation failed: {exc}")
        return 1


def _cmd_batch(args: argparse.Namespace) -> int:
    processor = BatchProcessor()
    try:
        for p in args.inputs:
            path = Path(p)
            report, gdf = run_validation(path)
            processor.add_dataset(gdf, path.name)
        results = processor.process_batch(
            unify_crs=args.unify_crs,
            target_crs=args.target_crs,
            crs_strategy=args.crs_strategy,
            fix_geometries=args.fix_geometries,
            merge_datasets=args.merge,
        )
        if results.get("success"):
            print("Batch processing succeeded.")
            print({k: v for k, v in results.items() if k != "final_dataset"})
            return 0
        print(f"Batch processing failed: {results.get('error', 'Unknown error')}")
        return 1
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


def app() -> None:
    parser = argparse.ArgumentParser(
        prog="geolint",
        description="GeoLint - Geospatial data linting and validation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_validate = subparsers.add_parser("validate", help="Validate a geospatial file")
    p_validate.add_argument("input", help="Path to input file (.zip/.gpkg/.geojson)")
    p_validate.add_argument("--report", help="Optional path to write text report")
    p_validate.set_defaults(func=_cmd_validate)

    p_batch = subparsers.add_parser("batch", help="Batch validate/process multiple files")
    p_batch.add_argument("inputs", nargs="+", help="Paths to input files")
    p_batch.add_argument("--unify-crs", action="store_true", default=True)
    p_batch.add_argument("--target-crs", default="EPSG:4326")
    p_batch.add_argument(
        "--crs-strategy",
        choices=["manual", "use_most_common", "auto_detect"],
        default="auto_detect",
    )
    p_batch.add_argument("--fix-geometries", action="store_true", default=True)
    p_batch.add_argument("--merge", action="store_true", default=False)
    p_batch.set_defaults(func=_cmd_batch)

    p_web = subparsers.add_parser("web", help="Launch the Streamlit web UI")
    p_web.set_defaults(func=_cmd_web)

    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    app()
