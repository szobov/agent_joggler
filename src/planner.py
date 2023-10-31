import math
import dataclasses
import heapq
import typing as _t

from .internal_types import (
    Agent,
    Environment,
    Heuristic,
    Node,
    NodeWithTime,
    TimeT,
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


def make_reservation_table() -> ReservationTableT:
    return {}


# https://en.wikipedia.org/wiki/A*_search_algorithm
def reconstruct_path(
    came_from_node_map: dict[NodeWithTime, NodeWithTime], current_node: NodeWithTime
) -> _t.Sequence[NodeWithTime]:
    total_path = [current_node]
    while current_node in came_from_node_map.keys():
        current_node = came_from_node_map.pop(current_node)
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


def reserve_nodes(
    reservation_table: ReservationTableT,
    agent: Agent,
    node_from: NodeWithTime,
    node_to: NodeWithTime,
    time_step: TimeT,
) -> None:
    key = (node_from.to_node(), node_to.to_node(), time_step)
    assert key not in reservation_table, f"{key=}, {reservation_table=}, {agent=}"
    reservation_table[key] = agent


def follow_path(
    path: _t.Sequence[NodeWithTime], reservation_table: ReservationTableT, agent: Agent
):
    for prev_node, next_node in zip(path, path[1:]):
        assert (
            prev_node.time_step != next_node.time_step
        ), f"{prev_node.time_step} != {next_node.time_step}"

        for wait_time_step in range(prev_node.time_step, next_node.time_step):
            reserve_nodes(
                reservation_table,
                agent,
                prev_node,
                prev_node,
                wait_time_step,
            )
        reserve_nodes(
            reservation_table,
            agent,
            prev_node,
            next_node,
            next_node.time_step,
        )
        reserve_nodes(
            reservation_table,
            agent,
            next_node,
            prev_node,
            next_node.time_step,
        )
    last_node = path[-1]
    reserve_nodes(
        reservation_table,
        agent,
        last_node,
        last_node,
        last_node.time_step,
    )


def time_expand_path(path: _t.Sequence[NodeWithTime]) -> _t.Sequence[Node]:
    expanded_path: list[Node] = []
    for prev_node, next_node in zip(path, path[1:]):
        for _ in range(prev_node.time_step, next_node.time_step):
            expanded_path.append(prev_node.to_node())
    expanded_path.append(path[-1].to_node())
    return expanded_path


def _need_wait(
    time_step: TimeT,
    reservation_table: ReservationTableT,
    curr_node: Node,
    next_node: Node,
) -> bool:
    is_next_node_occupied = (
        next_node,
        next_node,
        time_step,
    ) in reservation_table
    is_edge_occpuied = (
        curr_node,
        next_node,
        time_step,
    ) in reservation_table
    return is_edge_occpuied or is_next_node_occupied


def a_star_search(env: Environment) -> dict[Agent, _t.Sequence[Node]]:
    agents_paths: dict[Agent, _t.Sequence[Node]] = {}
    reservation_table = make_reservation_table()
    for agent in env.agents:
        time_step: TimeT = 0
        open_set = OpenSet()
        came_from: dict[NodeWithTime, NodeWithTime] = dict()
        # For node n, gScore[n] is the cost of the cheapest path
        # from start to n currently known.
        g_score = dict()
        g_score[agent.position] = 0

        # For node n, fScore[n] := gScore[n] + h(n).
        # fScore[n] represents our current best guess as to
        # how short a path from start to finish can be if it goes through n.
        #
        # TODO: should time_step be counted as heuristic?
        f_score = dict()
        f_score[agent.position] = heuristic(
            Heuristic.MANHATTAN_DISTANCE, agent.position, agent.goal
        )

        open_set.add(
            PriorityQueueItem(
                f_score[agent.position],
                NodeWithTime.from_node(agent.position, time_step),
            )
        )

        while len(open_set):
            current_node_with_priority = open_set.pop()
            current_node = current_node_with_priority.node
            if current_node_with_priority.node.to_node() == agent.goal:
                path = reconstruct_path(came_from, current_node)
                follow_path(path, reservation_table, agent)
                agents_paths[agent] = time_expand_path(path)
                break
            for neighbor_node in get_neighbors(env, current_node):
                next_time_step = current_node.time_step + 1

                is_current_node_reserved = False
                while _need_wait(
                    next_time_step,
                    reservation_table,
                    current_node.to_node(),
                    neighbor_node,
                ):
                    if (
                        current_node.to_node(),
                        current_node.to_node(),
                        next_time_step,
                    ) in reservation_table:
                        is_current_node_reserved = True
                        break
                    next_time_step += 1
                if is_current_node_reserved:
                    continue
                wait_time = next_time_step - current_node.time_step
                # d(current,neighbor) is the weight of the edge from
                # current to neighbor tentative_g_score is the distance
                # from start to the neighbor through current
                tentative_g_score = g_score[
                    current_node_with_priority.node.to_node()
                ] + edge_cost(env, current_node_with_priority.node, neighbor_node)
                tentative_g_score_plus_wait_time = tentative_g_score + wait_time

                if tentative_g_score_plus_wait_time >= g_score.get(
                    neighbor_node, float("inf")
                ):
                    continue
                came_from[
                    NodeWithTime.from_node(neighbor_node, next_time_step)
                ] = current_node
                g_score[neighbor_node] = tentative_g_score_plus_wait_time
                node_f_score = tentative_g_score + heuristic(
                    Heuristic.MANHATTAN_DISTANCE, neighbor_node, agent.goal
                )
                f_score[neighbor_node] = node_f_score
                # TODO: backward search:
                # 1. I need to run A* on a map without reservation table and other
                #    agents.
                # 2. It should use Manhattan distance as a heuristic.
                # 3. Should I use agent-wide g_score, f_score and came_from structures?
                # 4. Is came_from == closed_list in the paper?
                open_set.add(
                    PriorityQueueItem(
                        node=NodeWithTime.from_node(neighbor_node, next_time_step),
                        f_score=node_f_score,
                    )
                )
        else:
            raise RuntimeError(
                f"Path was not found. {agents_paths=}. {reservation_table=}"
            )
    return agents_paths


def main():
    ...


if __name__ == "__main__":
    main()
