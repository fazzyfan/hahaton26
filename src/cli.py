from __future__ import annotations

import argparse
from pathlib import Path

from src.services.import_pipeline import load_input_directory
from src.services.planning import build_plan


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.cli",
        description="Field engineer route planning",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser(
        "plan",
        help="Build a plan from data/input",
    )
    plan_parser.add_argument("--input-dir", required=True, type=Path)
    plan_parser.add_argument("--output", required=True, type=Path)

    return parser


def run_plan(input_dir: Path, output: Path) -> int:
    bundle = load_input_directory(input_dir)

    for report in bundle.reports:
        print(
            f"{report.filename}: rows={report.rows_total} "
            f"jobs={report.jobs_imported} "
            f"empty_skipped={report.skipped_empty} "
            f"office_skipped={report.skipped_office} "
            f"errors={report.error_count}"
        )

    if bundle.errors:
        print(f"import errors: {len(bundle.errors)}")

    plan = build_plan(bundle)

    print(
        f"assignments: {len(plan.assignments)} "
        f"routes: {len(plan.routes)} "
        f"unassigned: {len(plan.unassigned)} "
        f"status: {plan.status}"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        plan.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"plan saved: {output}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        return run_plan(args.input_dir, args.output)

    parser.error(f"unknown command: {args.command}")

    return 2


if __name__ == "__main__":
    raise SystemExit(main())