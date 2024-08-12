import typing as _t

from .internal_types import (
    Environment,
    Heuristic,
    Coordinate2D,
    Coordinate2DWithTime,
    PriorityQueueItem,
)
from .common_a_star_utils import (
    heuristic,
    get_neighbors,
    edge_cost,
    OpenSet,
)


def initialize_reverse_resumable_a_star(
    env: Environment, initial_node: Coordinate2D, goal_node: Coordinate2D
) -> _t.Generator[float | None, Coordinate2D, None]:
    open_set = OpenSet()
    # For node n, gScore[n] is the cost of the cheapest path
    # from start to n currently known.
    g_score = dict()
    g_score[initial_node] = 0

    # For node n, fScore[n] := gScore[n] + h(n).
    # fScore[n] represents our current best guess as to
    # how short a path from start to finish can be if it goes through n.
    f_score = dict()
    f_score[initial_node] = heuristic(
        Heuristic.MANHATTAN_DISTANCE, initial_node, goal_node
    )

    open_set.add(
        PriorityQueueItem(
            f_score[initial_node],
            initial_node,
        )
    )
    return resume_reverse_a_star(env, open_set, g_score)


def resume_reverse_a_star(
    env: Environment,
    open_set: OpenSet,
    g_score: dict[Coordinate2D, float],
) -> _t.Generator[float | None, Coordinate2D, None]:
    closed_set: set[Coordinate2D] = set()
    while True:
        search_node: Coordinate2D = yield
        assert isinstance(search_node, Coordinate2D)

        if search_node in closed_set:
            yield g_score[search_node]
            continue

        while len(open_set):
            current_node_with_priority = open_set.pop()
            current_node = current_node_with_priority.node
            if current_node in closed_set:
                continue
            else:
                closed_set.add(current_node)
            if current_node == search_node:
                yield g_score[current_node]
                break
            for neighbor_node in get_neighbors(env, current_node):
                # d(current,neighbor) is the weight of the edge from
                # current to neighbor tentative_g_score is the distance
                # from start to the neighbor through current
                tentative_g_score = g_score[current_node] + edge_cost(
                    env, current_node, neighbor_node
                )
                neighbor_node_g_score = g_score.get(neighbor_node, float("inf"))
                if neighbor_node_g_score > tentative_g_score:
                    g_score[neighbor_node] = tentative_g_score
                node_f_score = tentative_g_score + heuristic(
                    Heuristic.MANHATTAN_DISTANCE, neighbor_node, search_node
                )
                open_set.upsert(
                    PriorityQueueItem(
                        node=neighbor_node,
                        f_score=node_f_score,
                    )
                )
        else:
            yield float("inf")


# TODO: likely it makes sense to use a clojure and provide a similar interface as Manhattan
# distance heuristic, so we can call it `abstract_distance`
def resume_rra(
    rra: _t.Generator[float | None, Coordinate2D, None], node: Coordinate2D
) -> float:
    if isinstance(node, Coordinate2DWithTime):
        node = node.to_node()
    next(rra)
    g_score = rra.send(node)
    assert g_score is not None
    return g_score
