from collections.abc import Sequence
import enum
import itertools
import random
from dataclasses import InitVar, dataclass, field
from typing import Generator, Iterator, cast
from collections import OrderedDict

from structlog import get_logger

from src.message_transport import MessageBus, MessageBusProtocol, MessageTopic
from src.environment.generator import Map, MapObject, MapObjectType
from src.internal_types import (
    AgentIdT,
    GeneralObjectIdT,
    PlannerTasks,
    PlannerTask,
)
from src.runner import Process, ProcessFinishPolicy

logger = get_logger(__name__)


@dataclass(frozen=True)
class Pallet:
    object_id: GeneralObjectIdT


@enum.unique
class OrderType(enum.Enum):
    FREEUP = enum.auto()
    PICKUP = enum.auto()
    DELIVERY = enum.auto()


@dataclass(frozen=True)
class Order:
    planner_task: PlannerTask
    pallet_id: GeneralObjectIdT
    order_type: OrderType


@dataclass
class Stack:
    map_object: MapObject

    pallets: OrderedDict[GeneralObjectIdT, Pallet] = field(init=False)

    _pallets: InitVar[list[Pallet]]

    def __post_init__(self, _pallets: list[Pallet]):
        self.pallets = OrderedDict(((pallet.object_id, pallet) for pallet in _pallets))

    def add_pallet(self, pallet: Pallet):
        self.pallets[pallet.object_id] = pallet

    def get_bottom_pallet(
        self,
    ) -> Pallet:
        return self.pallets.popitem(last=False)[1]


@dataclass
class OrderPlanner:
    map: Map

    _max_stask_size: int = 8
    _stacks: dict[GeneralObjectIdT, Stack] = field(init=False)
    _pickup_stations: list[MapObject] = field(init=False)
    _agents: dict[AgentIdT, MapObject] = field(init=False)

    _next_order_id_generator: Iterator[GeneralObjectIdT] = field(
        init=False, default_factory=itertools.count
    )
    _next_pallet_id_generator: Iterator[GeneralObjectIdT] = field(
        init=False, default_factory=itertools.count
    )

    def __post_init__(self):
        map_stacks = filter(
            lambda object: object.object_type == MapObjectType.STACK, self.map.objects
        )
        self._stacks = {
            map_stack.object_id: Stack(
                map_object=map_stack,
                _pallets=[
                    Pallet(object_id=next(self._next_pallet_id_generator))
                    for _ in range(random.randint(1, self._max_stask_size // 2))
                ],
            )
            for map_stack in map_stacks
        }
        assert len(self._stacks) > 0

        self._agents = {
            agent.object_id: agent
            for agent in filter(
                lambda object: object.object_type == MapObjectType.AGENT,
                self.map.objects,
            )
        }
        assert len(self._agents) > 0
        self._pickup_stations = list(
            filter(
                lambda object: object.object_type == MapObjectType.PICKUP_STATION,
                self.map.objects,
            )
        )
        assert len(self._pickup_stations) > 0
        logger.debug(
            "generator is initialized",
            agents=self._agents,
            stacks=self._stacks,
            pickup_stations=self._pickup_stations,
        )

    def _generate_pickup_order(self) -> Generator[list[Order], set[AgentIdT], None]:
        target_stack = random.choice(
            list(filter(lambda s: len(s.pallets), self._stacks.values()))
        )
        target_pallet = random.choice(list(target_stack.pallets.values()))
        order_id = next(self._next_order_id_generator)
        order_sequence: list[Order] = []

        logger.info(
            "chose a pallet",
            target_stack=target_stack,
            target_pallet=target_pallet,
        )
        free_agents = []
        current_pallet = None
        while current_pallet != target_pallet:
            current_pallet = target_stack.get_bottom_pallet()
            log = logger.bind(current_pallet=current_pallet)
            if len(free_agents) == 0:
                log.debug("no free agents")
                free_agents = yield order_sequence
                log.debug("resume with new agents", free_agents=free_agents)
                order_sequence = []

            order_type = OrderType.PICKUP
            if current_pallet != target_pallet:
                order_type = OrderType.FREEUP
            agent_id = free_agents.pop()
            log.debug(
                "creating an order",
                order_id=order_id,
                agent_id=agent_id,
                order_type=order_type,
            )
            order_sequence.append(
                Order(
                    planner_task=PlannerTask(
                        order_id=order_id,
                        agent_id=agent_id,
                        goal=target_stack.map_object.coordinates,
                    ),
                    pallet_id=current_pallet.object_id,
                    order_type=order_type,
                )
            )
        yield order_sequence

    def _generate_delivery_order(
        self,
        agent_id: GeneralObjectIdT,
        pallet_id: GeneralObjectIdT,
        previous_order: Order,
    ) -> Order:
        target = None
        if previous_order.order_type == OrderType.PICKUP:
            target = random.choice(self._pickup_stations)
        else:
            # FIXME: suddenly, quadratic asymptotic complexity
            target_stack = next(
                filter(
                    lambda s: (
                        (len(s.pallets) < self._max_stask_size)
                        and (
                            s.map_object.coordinates != previous_order.planner_task.goal
                        )
                    ),
                    random.sample(list(self._stacks.values()), len(self._stacks)),
                ),
                None,
            )
            assert target_stack is not None, "No free stacks"
            target = target_stack.map_object

        return Order(
            planner_task=PlannerTask(
                order_id=next(self._next_order_id_generator),
                agent_id=agent_id,
                goal=target.coordinates,
            ),
            pallet_id=pallet_id,
            order_type=OrderType.DELIVERY,
        )

    def _process_finished_order(
        self, agent_id: AgentIdT, order: Order, agent_to_order: dict[AgentIdT, Order]
    ) -> list[Order]:
        logger.info("processing finished order", agent_id=agent_id, order=order)
        new_orders = []
        match order.order_type:
            case OrderType.DELIVERY:
                del agent_to_order[agent_id]
            case OrderType.PICKUP:
                new_orders.append(
                    self._generate_delivery_order(
                        agent_id=agent_id,
                        pallet_id=order.pallet_id,
                        previous_order=order,
                    )
                )
            case OrderType.FREEUP:
                new_orders.append(
                    self._generate_delivery_order(
                        agent_id=agent_id,
                        pallet_id=order.pallet_id,
                        previous_order=order,
                    )
                )
        logger.info("new orders", agent_id=agent_id, new_orders=new_orders)
        return new_orders

    def _iterate(
        self,
        message_bus: MessageBusProtocol,
        agent_to_order: dict[AgentIdT, Order],
        pickup_orders_generator: Generator[list[Order], set[AgentIdT], None] | None,
    ) -> tuple[Generator[list[Order], set[AgentIdT], None] | None, Sequence[Order]]:
        new_orders = []
        if agent_to_order:
            agent_path = message_bus.get_message(MessageTopic.AGENT_PATH, wait=True)
            assert agent_path
            logger.info(
                "got new agent_path",
                agent_path=agent_path,
                order=agent_to_order.get(agent_path.agent_id),
            )

            if agent_path.agent_id in agent_to_order and any(
                map(
                    lambda x: x.to_node()
                    == agent_to_order[agent_path.agent_id].planner_task.goal,
                    agent_path.path,
                ),
            ):
                finished_order = agent_to_order[agent_path.agent_id]
                new_orders.extend(
                    self._process_finished_order(
                        agent_path.agent_id, finished_order, agent_to_order
                    )
                )
        free_agents = self._agents.keys() - agent_to_order.keys()
        if not free_agents:
            return pickup_orders_generator, new_orders

        while free_agents:
            if pickup_orders_generator is None:
                pickup_orders_generator = self._generate_pickup_order()
                next(pickup_orders_generator)
            try:
                new_orders.extend(pickup_orders_generator.send(free_agents))
            except StopIteration:
                pickup_orders_generator = None
        return pickup_orders_generator, new_orders

    def _refill_stacks(self):
        for stack in filter(
            lambda s: len(s.pallets) < self._max_stask_size // 2, self._stacks.values()
        ):
            for _ in range(random.randint(1, 2)):
                stack.add_pallet(Pallet(next(self._next_pallet_id_generator)))

    def _send_orders(
        self,
        message_bus: MessageBusProtocol,
        agent_to_order: dict[AgentIdT, Order],
        orders: Sequence[Order],
    ):
        planner_tasks = []
        for order in orders:
            agent_to_order[order.planner_task.agent_id] = order
            planner_tasks.append(order.planner_task)
        message_bus.send_message(
            MessageTopic.PLANNER_TASKS, PlannerTasks(tasks=planner_tasks)
        )

    def start(self, message_bus: MessageBusProtocol):
        agent_to_order: dict[AgentIdT, Order] = {}
        pickup_orders_generator = None
        while not message_bus.get_message(MessageTopic.GLOBAL_STOP, wait=False):
            pickup_orders_generator, orders = self._iterate(
                message_bus, agent_to_order, pickup_orders_generator
            )
            if len(orders) == 0:
                continue
            logger.info("send new orders", orders=orders)
            self._send_orders(
                orders=orders, message_bus=message_bus, agent_to_order=agent_to_order
            )
            self._refill_stacks()


def get_message_bus() -> MessageBusProtocol:
    message_bus = MessageBus()

    message_bus.subscribe(MessageTopic.MAP)
    message_bus.subscribe(MessageTopic.AGENT_PATH)

    message_bus.prepare_publisher(MessageTopic.PLANNER_TASKS)

    return cast(MessageBusProtocol, message_bus)


def main(message_bus: MessageBusProtocol):
    map = message_bus.get_message(MessageTopic.MAP, wait=True)
    assert map
    order_planner = OrderPlanner(map)
    order_planner.start(message_bus)


def get_process() -> Process:
    return Process(
        name="order_planner",
        subsribe_topics=(MessageTopic.MAP, MessageTopic.AGENT_PATH),
        publish_topics=(MessageTopic.PLANNER_TASKS,),
        process_function=main,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )
