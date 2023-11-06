import enum
import dataclasses
import typing as _t

NodePosition: _t.TypeAlias = int
NodeState = enum.Enum("NodeState", "FREE RESERVED BLOCKED")
GridtT: _t.TypeAlias = list[list[NodeState]]
TimeT: _t.TypeAlias = int
AgentIdT: _t.TypeAlias = int


@dataclasses.dataclass(frozen=True, order=True)
class Node:
    position_x: NodePosition
    position_y: NodePosition


@dataclasses.dataclass(frozen=True, order=True)
class NodeWithTime(Node):
    time_step: TimeT

    @classmethod
    def from_node(
        cls: _t.Type["NodeWithTime"], node: Node, time_step: TimeT
    ) -> "NodeWithTime":
        return cls(node.position_x, node.position_y, time_step)

    def to_node(self) -> Node:
        return Node(self.position_x, self.position_y)


@dataclasses.dataclass(frozen=True)
class Agent:
    agent_id: AgentIdT
    position: Node
    goal: Node


@dataclasses.dataclass
class Environment:
    x_dim: int
    y_dim: int
    grid: GridtT
    agents: list[Agent]


ReservationTableKeyT: _t.TypeAlias = tuple[Node, Node, TimeT]
ReservationTableT: _t.TypeAlias = dict[ReservationTableKeyT, Agent]


@enum.unique
class Heuristic(enum.Enum):
    MANHATTAN_DISTANCE = enum.auto()


@dataclasses.dataclass(frozen=True, order=True)
class PriorityQueueItem:
    f_score: float
    node: NodeWithTime | Node
