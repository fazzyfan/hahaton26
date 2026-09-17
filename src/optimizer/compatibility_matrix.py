from src.models.entities import Engineer, Job
from src.optimizer.compatibility import CompatibilityService


class CompatibilityMatrix:
    """Строит список допустимых инженеров для каждой заявки."""

    def __init__(self):
        self.compatibility_service = CompatibilityService()

    def build(
        self,
        jobs: list[Job],
        engineers: list[Engineer],
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}

        for job in jobs:
            compatible_engineers = (
                self.compatibility_service.get_compatible_engineers(
                    job,
                    engineers,
                )
            )

            result[job.id] = [
                engineer.id
                for engineer in compatible_engineers
            ]

        return result