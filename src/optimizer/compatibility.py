from src.models.entities import Engineer, Job


class CompatibilityService:
    """Определяет, может ли инженер выполнять заявку."""

    def is_compatible(
        self,
        job: Job,
        engineer: Engineer,
    ) -> bool:
        """Возвращает True, если инженер подходит для заявки."""

        return job.required_skill in engineer.qualifications
    def get_compatible_engineers(
        self,
        job: Job,
        engineers: list[Engineer],
    ) -> list[Engineer]:
        """Возвращает всех инженеров, подходящих для заявки."""

        return [
            engineer
            for engineer in engineers
            if self.is_compatible(job, engineer)
        ]