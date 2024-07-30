import enum
import dataclasses
import typing as _t

import structlog
from dataclasses_avroschema.schema_generator import AvroModel


logger = structlog.getLogger(__name__)


NodePosition: _t.TypeAlias = int
NodeState = enum.Enum("NodeState", "FREE BLOCKED")
GridtT: _t.TypeAlias = list[list[NodeState]]
TimeT: _t.TypeAlias = int
AgentIdT: _t.TypeAlias = int
OrderIdT: _t.TypeAlias = int

GeneralObjectIdT: _t.TypeAlias = int


@dataclasses.dataclass(frozen=True, order=True)
class Coordinate2D(AvroModel):
    x: int
    y: int


@dataclasses.dataclass(frozen=True, order=True)
class Coordinate2DWithTime(Coordinate2D):
    time_step: TimeT

    @classmethod
    def from_node(
        cls: _t.Type["Coordinate2DWithTime"], node: Coordinate2D, time_step: TimeT
    ) -> "Coordinate2DWithTime":
        return cls(node.x, node.y, time_step)

    def to_node(self) -> Coordinate2D:
        return Coordinate2D(self.x, self.y)


@enum.unique
class OrderType(enum.Enum):
    FREEUP = "freeup"
    PICKUP = "pickup"
    DELIVERY = "delivery"


@dataclasses.dataclass(frozen=True)
class Agent:
    agent_id: AgentIdT
    position: Coordinate2D


@dataclasses.dataclass(frozen=True)
class Order(AvroModel):
    order_id: OrderIdT
    order_type: OrderType
    goal: Coordinate2D
    pallet_id: GeneralObjectIdT


@dataclasses.dataclass(frozen=True)
class OrderFinished(AvroModel):
    order_id: OrderIdT
    agent_id: AgentIdT


@dataclasses.dataclass(frozen=True)
class Orders(AvroModel):
    orders: list[Order]


@dataclasses.dataclass(frozen=True)
class GlobalStop(AvroModel): ...


@dataclasses.dataclass(frozen=True)
class ProcessStarted(AvroModel):
    process_name: str


@dataclasses.dataclass(frozen=True)
class GlobalStart(AvroModel):
    process_name: str


@dataclasses.dataclass
class Environment:
    x_dim: int
    y_dim: int
    grid: GridtT
    agents: list[Agent]


@enum.unique
class MapObjectType(enum.Enum):
    PICKUP_STATION = "pickup_station"
    STACK = "stack"
    MAINTENANCE_AREA = "mintenance_area"
    PILLAR = "pillar"
    AGENT = "agent"


@dataclasses.dataclass(frozen=True, order=True)
class MapObject(AvroModel):
    coordinates: Coordinate2D
    object_type: MapObjectType
    object_id: int


@dataclasses.dataclass(frozen=True)
class MapConfiguration(AvroModel):
    width_units: int
    height_units: int

    object_sizes: dict[str, Coordinate2D] = dataclasses.field(default_factory=dict)
    object_numbers: dict[str, int] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Map(AvroModel):
    configuration: MapConfiguration
    objects: list[MapObject] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class AgentPath(AvroModel):
    agent_id: AgentIdT
    path: list[Coordinate2DWithTime]


ReservationTableKeyT: _t.TypeAlias = tuple[Coordinate2D, Coordinate2D, TimeT]
ReservationTableMapT: _t.TypeAlias = dict[ReservationTableKeyT, Agent]


@dataclasses.dataclass
class ReservationTable:
    time_window: TimeT
    _reservation_table: ReservationTableMapT = dataclasses.field(default_factory=dict)
    agents_paths: _t.DefaultDict[Agent, _t.Sequence[Coordinate2DWithTime]] = (
        dataclasses.field(default_factory=lambda: _t.DefaultDict(list))
    )

    def is_node_occupied(
        self,
        node: Coordinate2D | Coordinate2DWithTime,
        time_step: TimeT,
        agent: _t.Optional[Agent] = None,
    ) -> bool:
        if isinstance(node, Coordinate2DWithTime):
            node = node.to_node()
        assert isinstance(node, Coordinate2D)
        key = (node, node, time_step)
        if not agent:
            return key in self._reservation_table
        return key in self._reservation_table and self._reservation_table[key] != agent

    def is_edge_occupied(
        self,
        node_from: Coordinate2D | Coordinate2DWithTime,
        node_to: Coordinate2D | Coordinate2DWithTime,
        time_step: TimeT,
    ) -> bool:
        if isinstance(node_from, Coordinate2DWithTime):
            node_from = node_from.to_node()
        if isinstance(node_to, Coordinate2DWithTime):
            node_to = node_to.to_node()
        return (node_from, node_to, time_step) in self._reservation_table

    def reserve_node(
        self,
        node: Coordinate2D | Coordinate2DWithTime,
        time_step: TimeT,
        agent: Agent,
    ):
        self._reserve_edge(node, node, time_step, agent)

    def reserve_edge(
        self,
        node_from: Coordinate2D | Coordinate2DWithTime,
        node_to: Coordinate2D | Coordinate2DWithTime,
        time_step: TimeT,
        agent: Agent,
    ):
        self._reserve_edge(node_from, node_to, time_step, agent)
        self._reserve_edge(node_to, node_from, time_step, agent)

    def _reserve_edge(
        self,
        node_from: Coordinate2D | Coordinate2DWithTime,
        node_to: Coordinate2D | Coordinate2DWithTime,
        time_step: TimeT,
        agent: Agent,
    ):
        if isinstance(node_from, Coordinate2DWithTime):
            node_from = node_from.to_node()
        if isinstance(node_to, Coordinate2DWithTime):
            node_to = node_to.to_node()
        key = (node_from, node_to, time_step)
        if self.is_edge_occupied(node_from, node_to, time_step):
            if self._reservation_table[key] == agent:
                return
            assert (
                key not in self._reservation_table
            ), f"{key=}, {self._reservation_table[key]=},  {self._reservation_table=}, {agent=}"
        self._reservation_table[key] = agent

    def _cleanup_path(self, path: _t.Sequence[Coordinate2DWithTime]):
        for prev_node, next_node in zip(path, path[1:]):
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

    def cleanup_blocked_node(
        self, blocked_node: Coordinate2D, time_step: TimeT, blocked_agent: Agent
    ) -> tuple[Agent, TimeT]:
        key = (blocked_node, blocked_node, time_step)
        blocked_by_agent = self._reservation_table.get(key)
        assert blocked_by_agent is not None
        assert blocked_by_agent.agent_id != blocked_agent.agent_id

        last_blocked_node_index = -1
        dropped_index = 0
        for dropped_index, blocked_by_agent_node in enumerate(
            reversed(self.agents_paths[blocked_by_agent])
        ):
            # FIXME: there is should be time_step instead of dropped_index
            assert (
                dropped_index < self.time_window
            ), "We're not expecting rebuilding path longer that time_window"
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
        self._cleanup_path(blocked_by_agent_to_drop)

        last_node = blocked_by_agent_to_drop[-1]
        last_node_key = (last_node.to_node(), last_node.to_node(), last_node.time_step)
        if (
            last_node_key in self._reservation_table
            and self._reservation_table[last_node_key] == blocked_by_agent
        ):
            self._reservation_table.pop(last_node_key)
        self.agents_paths[blocked_by_agent] = updated_blocked_by_agent_path
        return blocked_by_agent, blocked_by_agent_to_drop[0].time_step


@enum.unique
class Heuristic(enum.Enum):
    MANHATTAN_DISTANCE = enum.auto()
    EUCLIDEAN_DISTANCE = enum.auto()


@dataclasses.dataclass(frozen=True, order=True)
class PriorityQueueItem:
    f_score: float
    node: Coordinate2DWithTime | Coordinate2D
