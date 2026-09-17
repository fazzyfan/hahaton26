from src.matrix.database import MatrixDatabase


def create_demo_database(db_path: str = "data/demo.sqlite") -> None:
    """Создаёт и заполняет демонстрационную матрицу."""

    database = MatrixDatabase(db_path)
    database.create_tables()

    locations = [
        ("DEPOT", "Диспетчерский центр", 55.7558, 37.6173),
        ("LOC-A", "Объект A", 55.7600, 37.6200),
        ("LOC-B", "Объект B", 55.7500, 37.6250),
        ("LOC-C", "Объект C", 55.7450, 37.6100),
        ("LOC-D", "Объект D", 55.7650, 37.6050),
        ("LOC-E", "Объект E", 55.7550, 37.6350),
    ]

    for location in locations:
        database.add_location(*location)

    travels = [
        # DEPOT → объекты
        ("DEPOT", "LOC-A", "CAR", 15, 8.5, "demo-v1"),
        ("DEPOT", "LOC-B", "CAR", 20, 10.2, "demo-v1"),
        ("DEPOT", "LOC-C", "CAR", 18, 9.1, "demo-v1"),
        ("DEPOT", "LOC-D", "CAR", 12, 6.7, "demo-v1"),
        ("DEPOT", "LOC-E", "CAR", 22, 11.5, "demo-v1"),

        # Обратные направления
        ("LOC-A", "DEPOT", "CAR", 17, 8.5, "demo-v1"),
        ("LOC-B", "DEPOT", "CAR", 18, 10.2, "demo-v1"),
        ("LOC-C", "DEPOT", "CAR", 20, 9.1, "demo-v1"),
        ("LOC-D", "DEPOT", "CAR", 14, 6.7, "demo-v1"),
        ("LOC-E", "DEPOT", "CAR", 21, 11.5, "demo-v1"),

        # Между объектами
        ("LOC-A", "LOC-B", "CAR", 10, 5.2, "demo-v1"),
        ("LOC-B", "LOC-A", "CAR", 12, 5.2, "demo-v1"),

        ("LOC-A", "LOC-C", "CAR", 14, 7.0, "demo-v1"),
        ("LOC-C", "LOC-A", "CAR", 13, 7.0, "demo-v1"),

        ("LOC-A", "LOC-D", "CAR", 9, 4.5, "demo-v1"),
        ("LOC-D", "LOC-A", "CAR", 11, 4.5, "demo-v1"),

        ("LOC-A", "LOC-E", "CAR", 16, 8.0, "demo-v1"),
        ("LOC-E", "LOC-A", "CAR", 15, 8.0, "demo-v1"),

        ("LOC-B", "LOC-C", "CAR", 13, 6.5, "demo-v1"),
        ("LOC-C", "LOC-B", "CAR", 12, 6.5, "demo-v1"),

        ("LOC-B", "LOC-D", "CAR", 16, 8.0, "demo-v1"),
        ("LOC-D", "LOC-B", "CAR", 15, 8.0, "demo-v1"),

        ("LOC-B", "LOC-E", "CAR", 9, 4.8, "demo-v1"),
        ("LOC-E", "LOC-B", "CAR", 10, 4.8, "demo-v1"),

        ("LOC-C", "LOC-D", "CAR", 12, 6.0, "demo-v1"),
        ("LOC-D", "LOC-C", "CAR", 11, 6.0, "demo-v1"),

        ("LOC-C", "LOC-E", "CAR", 18, 9.0, "demo-v1"),
        ("LOC-E", "LOC-C", "CAR", 17, 9.0, "demo-v1"),

        ("LOC-D", "LOC-E", "CAR", 20, 10.0, "demo-v1"),
        ("LOC-E", "LOC-D", "CAR", 19, 10.0, "demo-v1"),
    ]

    for travel in travels:
        database.add_travel(*travel)