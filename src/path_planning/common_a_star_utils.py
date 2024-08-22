import heapq
import math
import typing as _t
import dataclasses

from ..internal_types import (
    Environment,
    Heuristic,
    Coordinate2D,
    NodeState,
    Coordinate2DWithTime,
    PriorityQueueItem,
)


def heuristic(
    heuristic_type: Heuristic, left: Coordinate2D, right: Coordinate2D
) -> float:
    match heuristic_type:
        case Heuristic.MANHATTAN_DISTANCE:
            dx = abs(left.x - right.x)
            dy = abs(left.y - right.y)
            return dx + dy
        case Heuristic.EUCLIDEAN_DISTANCE:
            dx = left.x - right.x
            dy = left.y - right.y
            return round(math.sqrt(dx * dx + dy * dy), ndigits=5)
        case _:
            raise NotImplementedError(f"{heuristic_type=}")


def get_neighbors(env: Environment, node: Coordinate2D) -> _t.Iterator[Coordinate2D]:
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)):
        neighbor_x = node.x + dx
        if neighbor_x >= env.x_dim or neighbor_x < 0:
            continue
        neighbor_y = node.y + dy
        if neighbor_y >= env.y_dim or neighbor_y < 0:
            continue
        state = env.grid[neighbor_x][neighbor_y]
        if state == NodeState.BLOCKED:
            continue
        yield Coordinate2D(neighbor_x, neighbor_y)


def edge_cost(
    env: Environment, node_from: Coordinate2D, node_to: Coordinate2D
) -> float:
    del env, node_from, node_to
    return 1.0


def _cast_to_coordinate2d(node: Coordinate2D | Coordinate2DWithTime) -> Coordinate2D:
    if isinstance(node, Coordinate2DWithTime):
        return node.to_node()
    return node


@dataclasses.dataclass
class OpenSet:
    item_queue: list[PriorityQueueItem] = dataclasses.field(default_factory=list)
    item_map: dict[Coordinate2D, PriorityQueueItem] = dataclasses.field(
        default_factory=dict
    )

    def add(self, item: PriorityQueueItem) -> None:
        if _cast_to_coordinate2d(item.node) in self.item_map:
            return
        heapq.heappush(self.item_queue, item)
        self.item_map[_cast_to_coordinate2d(item.node)] = item

    def upsert(self, item: PriorityQueueItem) -> None:
        if _cast_to_coordinate2d(item.node) not in self.item_map:
            self.add(item)
            return
        old_item = self.item_map[_cast_to_coordinate2d(item.node)]
        if item.f_score >= old_item.f_score:
            return
        self.item_map.pop(_cast_to_coordinate2d(old_item.node))
        self.add(item)

    def __contains__(self, item: _t.Any) -> bool:
        return item in self.item_map

    def pop(self) -> PriorityQueueItem:
        item = heapq.heappop(self.item_queue)
        while (
            _cast_to_coordinate2d(item.node) in self.item_map
            and item.f_score != self.item_map[_cast_to_coordinate2d(item.node)].f_score
        ):
            item = heapq.heappop(self.item_queue)
        if _cast_to_coordinate2d(item.node) in self.item_map:
            self.item_map.pop(_cast_to_coordinate2d(item.node))
        return item

    def __len__(self) -> int:
        return len(self.item_map)
