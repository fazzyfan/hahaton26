from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from src.services.import_pipeline import load_input_directory
from src.services.planning import build_plan, check_plan


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


def _print_import_summary(bundle) -> list:
    fatal = []

    for report in bundle.reports:
        print(
            f"{report.filename}: rows={report.rows_total} "
            f"jobs={report.jobs_imported} "
            f"empty_skipped={report.skipped_empty} "
            f"office_skipped={report.skipped_office} "
            f"errors={report.error_count}"
        )

    for error in bundle.errors:
        print(
            f"  [{error.code}] file={error.file} row={error.row} "
            f"field={error.field} can_skip={error.can_skip} "
            f"message={error.message}"
        )

        if not error.can_skip:
            fatal.append(error)

    return fatal


def _print_plan_summary(bundle, plan) -> None:
    work_types = Counter(job.work_type for job in bundle.jobs)
    gigabit_count = sum(
        1 for job in bundle.jobs if job.gigabit_connection
    )
    used_engineers = {
        assignment.engineer_id for assignment in plan.assignments
    }
    total_travel_min = sum(route.total_travel_min for route in plan.routes)
    issues = check_plan(bundle, plan)

    print(f"Imported: {len(bundle.jobs)}")
    print(f"CONNECTION: {work_types.get('CONNECTION', 0)}")
    print(f"LOCAL_WORK: {work_types.get('LOCAL_WORK', 0)}")
    print(f"EMERGENCY: {work_types.get('EMERGENCY', 0)}")
    print(f"ADD_ORDER: {work_types.get('ADD_ORDER', 0)}")
    print(f"Gigabit: {gigabit_count}")
    print(f"Assigned: {len(plan.assignments)}")
    print(f"Unassigned: {len(plan.unassigned)}")
    print(f"Routes: {len(plan.routes)}")
    print(f"Used engineers: {len(used_engineers)}")
    print(f"Unused engineers: {len(bundle.engineers) - len(used_engineers)}")
    print(f"Total travel time: {total_travel_min}")
    print(f"Validator issues: {len(issues)}")
    print(f"Plan status: {plan.status}")


def run_plan(input_dir: Path, output: Path) -> int:
    bundle = load_input_directory(input_dir)

    fatal = _print_import_summary(bundle)

    if fatal:
        print("planning aborted: fatal import error(s) detected")
        return 1

    if not bundle.jobs and bundle.reports:
        # Пустой VALID-план при наличии файлов сохранять нельзя.
        print("planning aborted: no jobs imported")
        return 1

    plan = build_plan(bundle)

    _print_plan_summary(bundle, plan)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        plan.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"plan saved: {output}")

    return 0


def main(argv: list[str] | None = None) -> int:
    # Кириллица в именах файлов и сообщениях должна печататься без сбоев
    # на консолях с локальной кодировкой (cp1252 и т.п.).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        return run_plan(args.input_dir, args.output)

    parser.error(f"unknown command: {args.command}")

    return 2


if __name__ == "__main__":
    raise SystemExit(main())