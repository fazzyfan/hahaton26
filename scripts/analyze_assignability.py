"""Анализ теоретической выполнимости заявок при свободных бригадах."""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.optimizer.travel import TravelMatrix
from src.services.import_pipeline import load_input_directory


def main() -> None:
    bundle = load_input_directory("data/input")
    travel = TravelMatrix(bundle.travel_matrix)

    theoretically = 0
    infeasible = []

    for job in bundle.jobs:
        feasible = False

        for engineer in bundle.engineers:
            if (
                engineer.service_districts
                and job.service_zone not in engineer.service_districts
            ):
                continue
            if (
                engineer.allowed_work_types
                and job.work_type not in engineer.allowed_work_types
            ):
                continue
            if job.required_equipment and not set(
                job.required_equipment
            ).issubset(set(engineer.equipment_ids)):
                continue

            travel_min = travel.travel_min(
                engineer.start_location_id,
                job.location_id,
                engineer.transport_type,
            )

            if travel_min is None:
                continue

            earliest_arrival = engineer.shift_start + timedelta(
                minutes=travel_min
            )
            earliest_start = max(earliest_arrival, job.window_start)
            latest_start = job.window_end

            if (
                earliest_start <= latest_start
                and earliest_start
                + timedelta(minutes=job.service_duration_min)
                <= engineer.shift_end
            ):
                feasible = True
                break

        if feasible:
            theoretically += 1
        else:
            infeasible.append((job.id, job.window_start, job.window_end))

    print(
        f"theoretically assignable (ignoring capacity): "
        f"{theoretically} of {len(bundle.jobs)}"
    )
    print(f"infeasible examples: {len(infeasible)}")
    for item in infeasible[:10]:
        print(" ", item)


if __name__ == "__main__":
    main()