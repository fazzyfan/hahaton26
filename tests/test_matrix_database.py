from src.matrix.database import MatrixDatabase


def test_create_matrix_database(tmp_path):
    db_path = tmp_path / "test.sqlite"

    database = MatrixDatabase(db_path)
    database.create_tables()

    assert db_path.exists()


def test_create_tables_twice(tmp_path):
    db_path = tmp_path / "test.sqlite"

    database = MatrixDatabase(db_path)

    database.create_tables()
    database.create_tables()

    assert db_path.exists()