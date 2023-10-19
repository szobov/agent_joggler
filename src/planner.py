import math
import dataclasses
import heapq
import typing as _t

from .internal_types import (
    Agent,
    Environment,
    Heuristic,
    Node,
    NodeState,
    ReservationTableT,
    PriorityQueueItem,
)


def heuristic(heuristic_type: Heuristic, left: Node, right: Node) -> float:
    match heuristic_type:
        case Heuristic.MANHATTAN_DISTANCE:
            dx = abs(left.position_x - right.position_x)
            dy = abs(left.position_y - right.position_y)
            return dx + dy
        case Heuristic.TRUE_DISTANCE:
            dx = left.position_x - right.position_x
            dy = left.position_y - right.position_y
            return round(math.sqrt(dx * dx + dy * dy), ndigits=5)
        case _:
            return 0.0


# Try first: create a graph from evironment?
def make_reservation_table() -> ReservationTableT:
    return {}


# https://en.wikipedia.org/wiki/A*_search_algorithm
def reconstruct_path(
    came_from_node_list: _t.Any, current_node: _t.Any
) -> _t.Sequence[Node]:
    total_path = [current_node]
    while current_node in came_from_node_list.keys():
        current_node = came_from_node_list.pop(current_node)
        total_path.append(current_node)
    return list(reversed(total_path))


def get_neighbors(env: Environment, node: Node) -> _t.Iterator[Node]:
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        neighbor_position_x = node.position_x + dx
        if neighbor_position_x >= env.x_dim or neighbor_position_x < 0:
            continue
        neighbor_position_y = node.position_y + dy
        if neighbor_position_y >= env.y_dim or neighbor_position_y < 0:
            continue
        state = env.grid[neighbor_position_x][neighbor_position_y]
        if state == NodeState.BLOCKED:
            continue
        if state == NodeState.RESERVED:
            ...
        yield Node(neighbor_position_x, neighbor_position_y)


def edge_cost(env: Environment, node_from: Node, node_to: Node) -> float:
    del env, node_from, node_to
    return 1.0


@dataclasses.dataclass
class OpenSet:
    item_queue: list[PriorityQueueItem] = dataclasses.field(default_factory=list)
    item_set: set[Node] = dataclasses.field(default_factory=set)

    def add(self, item: PriorityQueueItem) -> None:
        if item.node in self.item_set:
            return
        heapq.heappush(self.item_queue, item)
        self.item_set.add(item.node)

    def pop(self) -> PriorityQueueItem:
        item = heapq.heappop(self.item_queue)
        self.item_set.remove(item.node)
        return item

    def __len__(self) -> int:
        return len(self.item_queue)


def a_star_search(env: Environment) -> dict[Agent, _t.Sequence[Node]]:
    agent_path: dict[Agent, _t.Sequence[Node]] = {}
    for agent in env.agents:
        open_set = OpenSet()
        came_from: dict[Node, Node] = dict()
        # For node n, gScore[n] is the cost of the cheapest path
        # from start to n currently known.
        g_score = dict()
        g_score[agent.position] = 0

        # For node n, fScore[n] := gScore[n] + h(n).
        # fScore[n] represents our current best guess as to
        # how short a path from start to finish can be if it goes through n.
        f_score = dict()
        f_score[agent.position] = heuristic(
            Heuristic.MANHATTAN_DISTANCE, agent.position, agent.goal
        )

        open_set.add(PriorityQueueItem(f_score[agent.position], agent.position))

        while len(open_set):
            current_node = open_set.pop()
            if current_node.node == agent.goal:
                path = reconstruct_path(came_from, current_node.node)
                agent_path[agent] = path
                break
            for neighbor_node in get_neighbors(env, current_node.node):
                # d(current,neighbor) is the weight of the edge from
                # current to neighbor tentative_g_score is the distance
                # from start to the neighbor through current
                tentative_g_score = g_score[current_node.node] + edge_cost(
                    env, current_node.node, neighbor_node
                )

                if tentative_g_score >= g_score.get(neighbor_node, float("inf")):
                    continue
                came_from[neighbor_node] = current_node.node
                g_score[neighbor_node] = tentative_g_score
                node_f_score = tentative_g_score + heuristic(
                    Heuristic.MANHATTAN_DISTANCE, neighbor_node, agent.goal
                )
                f_score[neighbor_node] = node_f_score

                open_set.add(
                    PriorityQueueItem(node=neighbor_node, f_score=node_f_score)
                )
        else:
            raise RuntimeError("Path was not found")
    return agent_path


def main():
    ...


if __name__ == "__main__":
    main()
