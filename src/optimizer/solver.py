from ortools.constraint_solver import pywrapcp, routing_enums_pb2


class SimpleOptimizer:
    """Самая простая версия оптимизатора."""

    def solve(self, locations: list[str]) -> list[str]:
        """Строит простой маршрут через переданные точки."""

        manager = pywrapcp.RoutingIndexManager(
            len(locations),
            1,
            0,
        )

        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)

            return abs(from_node - to_node)

        transit_callback_index = routing.RegisterTransitCallback(
            distance_callback
        )

        routing.SetArcCostEvaluatorOfAllVehicles(
            transit_callback_index
        )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()

        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )

        solution = routing.SolveWithParameters(search_parameters)

        if solution is None:
            return []

        route = []

        index = routing.Start(0)

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(locations[node])

            index = solution.Value(
                routing.NextVar(index)
            )

        route.append(locations[manager.IndexToNode(index)])

        return route