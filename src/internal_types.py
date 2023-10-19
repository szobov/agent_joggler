import enum
import dataclasses
import typing as _t

NodePosition: _t.TypeAlias = int
NodeState = enum.Enum("NodeState", "FREE RESERVED BLOCKED")
GridtT: _t.TypeAlias = list[list[NodeState]]
TimeT: _t.TypeAlias = int


@dataclasses.dataclass(frozen=True, order=True)
class Node:
    position_x: NodePosition
    position_y: NodePosition


@dataclasses.dataclass(frozen=True)
class NodeWithState(Node):
    state: NodeState


@dataclasses.dataclass(frozen=True)
class Agent:
    agent_id: int
    position: Node
    goal: Node


@dataclasses.dataclass
class Environment:
    x_dim: int
    y_dim: int
    grid: GridtT
    agents: list[Agent]


ReservationTableKeyT: _t.TypeAlias = tuple[NodePosition, NodePosition, TimeT]
ReservationTableT: _t.TypeAlias = dict[ReservationTableKeyT, NodeState]


@enum.unique
class Heuristic(enum.Enum):
    MANHATTAN_DISTANCE = enum.auto()
    TRUE_DISTANCE = enum.auto()


@dataclasses.dataclass(frozen=True, order=True)
class PriorityQueueItem:
    f_score: float
    node: Node
