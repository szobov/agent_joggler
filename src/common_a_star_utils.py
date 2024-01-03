import heapq
import math
import typing as _t
import dataclasses

from .internal_types import (
    Environment,
    Heuristic,
    Node,
    NodeState,
    NodeWithTime,
    PriorityQueueItem,
)


def heuristic(heuristic_type: Heuristic, left: Node, right: Node) -> float:
    match heuristic_type:
        case Heuristic.MANHATTAN_DISTANCE:
            dx = abs(left.position_x - right.position_x)
            dy = abs(left.position_y - right.position_y)
            return dx + dy
        case Heuristic.EUCLIDEAN_DISTANCE:
            dx = left.position_x - right.position_x
            dy = left.position_y - right.position_y
            return round(math.sqrt(dx * dx + dy * dy), ndigits=5)
        case _:
            raise NotImplementedError(f"{heuristic_type=}")


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


def _cast_to_node(node: Node | NodeWithTime) -> Node:
    if isinstance(node, NodeWithTime):
        return node.to_node()
    return node


@dataclasses.dataclass
class OpenSet:
    item_queue: list[PriorityQueueItem] = dataclasses.field(default_factory=list)
    item_map: dict[Node, PriorityQueueItem] = dataclasses.field(default_factory=dict)

    def add(self, item: PriorityQueueItem) -> None:
        if _cast_to_node(item.node) in self.item_map:
            return
        heapq.heappush(self.item_queue, item)
        self.item_map[_cast_to_node(item.node)] = item

    def upsert(self, item: PriorityQueueItem) -> None:
        if _cast_to_node(item.node) not in self.item_map:
            self.add(item)
            return
        old_item = self.item_map[_cast_to_node(item.node)]
        if item.f_score >= old_item.f_score:
            return
        self.item_map.pop(_cast_to_node(old_item.node))
        self.add(item)

    def __contains__(self, item: _t.Any) -> bool:
        return item in self.item_map

    def pop(self) -> PriorityQueueItem:
        item = heapq.heappop(self.item_queue)
        while (
            _cast_to_node(item.node) in self.item_map
            and item.f_score != self.item_map[_cast_to_node(item.node)].f_score
        ):
            item = heapq.heappop(self.item_queue)
        if _cast_to_node(item.node) in self.item_map:
            self.item_map.pop(_cast_to_node(item.node))
        return item

    def __len__(self) -> int:
        return len(self.item_map)
