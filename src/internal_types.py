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
ReservationTableMapT: _t.TypeAlias = dict[ReservationTableKeyT, Agent]


@dataclasses.dataclass
class ReservationTable:
    _reservation_table: ReservationTableMapT = dataclasses.field(default_factory=dict)
    _initialy_reserved_nodes: dict[Node, Agent] = dataclasses.field(
        default_factory=dict
    )
    agents: dataclasses.InitVar[_t.Sequence[Agent]] = []

    def __post_init__(self, agents: _t.Sequence[Agent]):
        self._initialy_reserved_nodes = {agent.position: agent for agent in agents}

    def free_initialy_reserved_node(self, node: Node):
        self._initialy_reserved_nodes.pop(node)

    def is_node_occupied(
        self,
        node: Node | NodeWithTime,
        time_step: TimeT,
        agent: _t.Optional[Agent] = None,
    ) -> bool:
        if isinstance(node, NodeWithTime):
            node = node.to_node()
        if node in self._initialy_reserved_nodes:
            return True
        assert isinstance(node, Node)
        key = (node, node, time_step)
        if not agent:
            return key in self._reservation_table
        return key in self._reservation_table and self._reservation_table[key] != agent

    def is_node_initially_reserved(self, node: Node | NodeWithTime) -> bool:
        if isinstance(node, NodeWithTime):
            node = node.to_node()
        return node in self._initialy_reserved_nodes

    def is_edge_occupied(
        self,
        node_from: Node | NodeWithTime,
        node_to: Node | NodeWithTime,
        time_step: TimeT,
    ) -> bool:
        if isinstance(node_from, NodeWithTime):
            node_from = node_from.to_node()
        if isinstance(node_to, NodeWithTime):
            node_to = node_to.to_node()
        return (node_from, node_to, time_step) in self._reservation_table

    def reserve_node(
        self,
        node: Node | NodeWithTime,
        time_step: TimeT,
        agent: Agent,
    ):
        if node in self._initialy_reserved_nodes:
            if self._initialy_reserved_nodes[node] == agent:
                self._initialy_reserved_nodes.pop(node)
            assert (
                self._initialy_reserved_nodes[node] == agent
            ), f"Node is initially reserved by agent, that not moved yet"
        self._reserve_edge(node, node, time_step, agent)

    def reserve_edge(
        self,
        node_from: Node | NodeWithTime,
        node_to: Node | NodeWithTime,
        time_step: TimeT,
        agent: Agent,
    ):
        self._reserve_edge(node_from, node_to, time_step, agent)
        self._reserve_edge(node_to, node_from, time_step, agent)

    def _reserve_edge(
        self,
        node_from: Node | NodeWithTime,
        node_to: Node | NodeWithTime,
        time_step: TimeT,
        agent: Agent,
    ):
        if isinstance(node_from, NodeWithTime):
            node_from = node_from.to_node()
        if isinstance(node_to, NodeWithTime):
            node_to = node_to.to_node()
        key = (node_from, node_to, time_step)
        if self.is_edge_occupied(node_from, node_to, time_step):
            if self._reservation_table[key] == agent:
                return
            assert (
                key not in self._reservation_table
            ), f"{key=}, {self._reservation_table=}, {agent=}"
        self._reservation_table[key] = agent


@enum.unique
class Heuristic(enum.Enum):
    MANHATTAN_DISTANCE = enum.auto()
    EUCLIDEAN_DISTANCE = enum.auto()


@dataclasses.dataclass(frozen=True, order=True)
class PriorityQueueItem:
    f_score: float
    node: NodeWithTime | Node
