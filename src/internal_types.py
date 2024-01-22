import enum
import dataclasses
import typing as _t

import structlog


logger = structlog.getLogger(__name__)


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
    agents_paths: _t.DefaultDict[Agent, _t.Sequence[NodeWithTime]] = dataclasses.field(
        default_factory=lambda: _t.DefaultDict(list)
    )

    def is_node_occupied(
        self,
        node: Node | NodeWithTime,
        time_step: TimeT,
        agent: _t.Optional[Agent] = None,
    ) -> bool:
        if isinstance(node, NodeWithTime):
            node = node.to_node()
        assert isinstance(node, Node)
        key = (node, node, time_step)
        if not agent:
            return key in self._reservation_table
        return key in self._reservation_table and self._reservation_table[key] != agent

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

    def cleanup_blocked_node(
        self, blocked_node: Node, time_step: TimeT, blocked_agent: Agent
    ):
        key = (blocked_node, blocked_node, time_step)
        blocked_by_agent = self._reservation_table.get(key)
        assert blocked_by_agent is not None
        assert blocked_by_agent.agent_id != blocked_agent.agent_id

        last_blocked_node_index = -1
        dropped_index = 0
        for dropped_index, blocked_by_agent_node in enumerate(
            reversed(self.agents_paths[blocked_by_agent])
        ):
            if blocked_by_agent_node.to_node() != blocked_node:
                if last_blocked_node_index != -1:
                    break
                continue
            if blocked_by_agent_node.time_step < time_step:
                break
            last_blocked_node_index = dropped_index

        blocked_by_agent_path = self.agents_paths[blocked_by_agent]
        updated_blocked_by_agent_path = blocked_by_agent_path[
            : len(blocked_by_agent_path) - dropped_index
        ]
        blocked_by_agent_to_drop = blocked_by_agent_path[
            len(blocked_by_agent_path) - dropped_index :
        ]

        # TODO: I must cleanup all parts of the path in reservation table. N1 -> N2, N1 <- N2,
        for prev_node, next_node in zip(
            blocked_by_agent_to_drop, blocked_by_agent_to_drop[1:]
        ):
            for wait_time_step in range(prev_node.time_step, next_node.time_step):
                self._reservation_table.pop(
                    (prev_node.to_node(), prev_node.to_node(), wait_time_step)
                )
            if prev_node.to_node() == next_node.to_node():
                self._reservation_table.pop(
                    (prev_node.to_node(), prev_node.to_node(), next_node.time_step)
                )
            else:
                self._reservation_table.pop(
                    (prev_node.to_node(), next_node.to_node(), next_node.time_step)
                )
                self._reservation_table.pop(
                    (next_node.to_node(), prev_node.to_node(), next_node.time_step)
                )

        last_node = blocked_by_agent_to_drop[-1]
        last_node_key = (last_node.to_node(), last_node.to_node(), last_node.time_step)
        if (
            last_node_key in self._reservation_table
            and self._reservation_table[last_node_key] == blocked_by_agent
        ):
            self._reservation_table.pop(last_node_key)
        self.agents_paths[blocked_by_agent] = updated_blocked_by_agent_path


@enum.unique
class Heuristic(enum.Enum):
    MANHATTAN_DISTANCE = enum.auto()
    EUCLIDEAN_DISTANCE = enum.auto()


@dataclasses.dataclass(frozen=True, order=True)
class PriorityQueueItem:
    f_score: float
    node: NodeWithTime | Node
