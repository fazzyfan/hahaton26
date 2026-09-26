import sqlite3
from pathlib import Path


class MatrixDatabase:
    """Работает с SQLite-базой матрицы поездок."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        """Открывает соединение с базой данных."""

        return sqlite3.connect(self.db_path)

    def create_tables(self) -> None:
        """Создаёт таблицы, если их ещё нет."""

        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS locations (
                    location_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS travel_matrix (
                    origin_location_id TEXT NOT NULL,
                    destination_location_id TEXT NOT NULL,
                    transport_type TEXT NOT NULL,
                    travel_min INTEGER NOT NULL,
                    distance_km REAL NOT NULL,
                    matrix_version TEXT NOT NULL,

                    PRIMARY KEY (
                        origin_location_id,
                        destination_location_id,
                        transport_type
                    ),

                    FOREIGN KEY (origin_location_id)
                        REFERENCES locations(location_id),

                    FOREIGN KEY (destination_location_id)
                        REFERENCES locations(location_id)
                )
                """
            )
    def add_location(
        self,
        location_id: str,
        name: str,
        latitude: float,
        longitude: float,
    ) -> None:
        """Добавляет точку в базу данных."""

        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO locations (
                    location_id,
                    name,
                    latitude,
                    longitude
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    location_id,
                    name,
                    latitude,
                    longitude,
                ),
            )

    def add_travel(
        self,
        origin_location_id: str,
        destination_location_id: str,
        transport_type: str,
        travel_min: int,
        distance_km: float,
        matrix_version: str,
    ) -> None:
        """
        Добавляет поездку между двумя точками.

        Повторная вставка того же ключа (origin, destination,
        transport_type) приводит к sqlite3.IntegrityError: молчаливая
        перезапись значений запрещена.
        """

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO travel_matrix (
                    origin_location_id,
                    destination_location_id,
                    transport_type,
                    travel_min,
                    distance_km,
                    matrix_version
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    origin_location_id,
                    destination_location_id,
                    transport_type,
                    travel_min,
                    distance_km,
                    matrix_version,
                ),
            )
    def get_travel(
        self,
        origin_location_id: str,
        destination_location_id: str,
        transport_type: str,
    ) -> tuple[int, float, str] | None:
        """Возвращает время, расстояние и версию матрицы."""

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    travel_min,
                    distance_km,
                    matrix_version
                FROM travel_matrix
                WHERE origin_location_id = ?
                  AND destination_location_id = ?
                  AND transport_type = ?
                """,
                (
                    origin_location_id,
                    destination_location_id,
                    transport_type,
                ),
            ).fetchone()

        if row is None:
            return None

        return row[0], row[1], row[2]