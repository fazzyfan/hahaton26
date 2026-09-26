from src.models.entities import Engineer, Job, JobRecord
from src.optimizer.scheduling import is_compatible as is_compatible_worktype


class CompatibilityService:
    """
    Определяет, может ли бригада выполнять заявку.

    Единый источник допуска — `allowed_work_types` (официальные типы
    работ из конфигурации, Data Contract v1.2). Тестовые навыки
    ELECTRIC/NETWORK/MECHANIC (поле `qualifications`) заменены типами
    работ и в выборе не участвуют.

    Работает и с каноническими `JobRecord`, и с legacy-моделью `Job`
    (в этом случае используется поле `work_type`, если оно есть).
    """

    def is_compatible(self, job: Job | JobRecord, engineer: Engineer) -> bool:
        """Возвращает True, если бригада подходит для заявки."""
        if isinstance(job, JobRecord):
            return is_compatible_worktype(job, engineer)

        # Legacy Job: допуск проверяется по типу работы, если он задан;
        # иначе совместимости нет (навыки ELECTRIC/NETWORK/MECHANIC
        # больше не являются источником допуска).
        work_type = getattr(job, "work_type", None)

        if work_type is None:
            return False

        if (
            engineer.allowed_work_types
            and work_type not in engineer.allowed_work_types
        ):
            return False

        return True

    def get_compatible_engineers(
        self,
        job: Job | JobRecord,
        engineers: list[Engineer],
    ) -> list[Engineer]:
        """Возвращает всех инженеров, подходящих для заявки."""

        return [
            engineer
            for engineer in engineers
            if self.is_compatible(job, engineer)
        ]