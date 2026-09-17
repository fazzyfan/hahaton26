from src.optimizer.solver import SimpleOptimizer


def test_simple_optimizer_returns_route():
    optimizer = SimpleOptimizer()

    locations = [
        "DEPOT",
        "LOC-A",
        "LOC-B",
        "LOC-C",
    ]

    route = optimizer.solve(locations)

    assert route
    assert route[0] == "DEPOT"
    assert route[-1] == "DEPOT"

    assert set(route) == set(locations)