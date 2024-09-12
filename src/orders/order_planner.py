from collections.abc import Sequence
import itertools
import random
from dataclasses import InitVar, dataclass, field
from typing import Iterator, cast
from collections import OrderedDict

from structlog import get_logger

from src.message_transport import MessageBus, MessageBusProtocol, MessageTopic
from src.environment.generator import Map, MapObject, MapObjectType
from src.internal_types import (
    AgentIdT,
    GeneralObjectIdT,
    OrderIdT,
    OrderType,
    Orders,
    Order,
)
from src.runner import Process, ProcessFinishPolicy

logger = get_logger(__name__)


@dataclass(frozen=True)
class Pallet:
    object_id: GeneralObjectIdT


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
    _number_of_orders: int = field(init=False)

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
        self._number_of_orders = len(self._agents) * 4

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

    def _generate_orders(self) -> list[Order]:
        target_stack = random.choice(
            list(filter(lambda s: len(s.pallets), self._stacks.values()))
        )
        target_pallet = random.choice(list(target_stack.pallets.values()))
        order_sequence: list[Order] = []

        logger.info(
            "chose a pallet",
            target_stack=target_stack,
            target_pallet=target_pallet,
        )

        current_pallet = None
        while current_pallet != target_pallet:
            order_id = next(self._next_order_id_generator)
            current_pallet = target_stack.get_bottom_pallet()
            log = logger.bind(current_pallet=current_pallet)

            order_type = OrderType.PICKUP
            if current_pallet != target_pallet:
                order_type = OrderType.FREEUP

            log.debug(
                "creating an order",
                order_id=order_id,
                order_type=order_type,
            )
            order_sequence.append(
                Order(
                    order_id=order_id,
                    order_type=order_type,
                    goal=target_stack.map_object.coordinates,
                    pallet_id=current_pallet.object_id,
                )
            )
            if order_type == OrderType.FREEUP:
                # FIXME: suddenly, quadratic asymptotic complexity
                freeup_delivery_stack = next(
                    filter(
                        lambda s: (
                            (len(s.pallets) < self._max_stask_size)
                            and (
                                s.map_object.coordinates
                                != target_stack.map_object.coordinates
                            )
                        ),
                        random.sample(list(self._stacks.values()), len(self._stacks)),
                    ),
                    None,
                )

                assert freeup_delivery_stack is not None, "No free stacks"
                order_sequence.append(
                    Order(
                        order_id=next(self._next_order_id_generator),
                        order_type=order_type,
                        goal=freeup_delivery_stack.map_object.coordinates,
                        pallet_id=current_pallet.object_id,
                    )
                )
        order_type = OrderType.DELIVERY
        pickup_station = random.choice(self._pickup_stations)
        order_sequence.append(
            Order(
                order_id=next(self._next_order_id_generator),
                goal=pickup_station.coordinates,
                order_type=order_type,
                pallet_id=target_pallet.object_id,
            )
        )

        return order_sequence

    def _iterate(
        self,
        message_bus: MessageBusProtocol,
        orders: OrderedDict[OrderIdT, Order],
    ) -> Sequence[Order]:
        if orders:
            finished_order = message_bus.get_message(
                MessageTopic.ORDER_FINISHED, wait=True
            )
            assert finished_order
            assert finished_order.order_id in orders, f"{finished_order=}, {orders=}"
            order = orders[finished_order.order_id]
            logger.info("got finished", finished_order=finished_order, order=order)

            del orders[order.order_id]
        new_orders = []
        while len(orders) < self._number_of_orders:
            next_batch = self._generate_orders()
            for order in next_batch:
                orders[order.order_id] = order
            new_orders.extend(next_batch)

        return new_orders

    def _refill_stacks(self):
        for stack in filter(
            lambda s: len(s.pallets) < self._max_stask_size // 2, self._stacks.values()
        ):
            for _ in range(random.randint(1, 2)):
                stack.add_pallet(Pallet(next(self._next_pallet_id_generator)))

    def _send_orders(
        self,
        message_bus: MessageBusProtocol,
        orders: Sequence[Order],
    ):
        message_bus.send_message(MessageTopic.ORDERS, Orders(orders=list(orders)))

    def start(self, message_bus: MessageBusProtocol):
        orders: OrderedDict[OrderIdT, Order] = OrderedDict()
        while not message_bus.get_message(MessageTopic.GLOBAL_STOP, wait=False):
            new_orders = self._iterate(message_bus, orders)
            if len(new_orders) == 0:
                continue
            logger.info("send new orders", orders=new_orders)
            self._send_orders(
                orders=new_orders,
                message_bus=message_bus,
            )
            self._refill_stacks()


def get_message_bus() -> MessageBusProtocol:
    message_bus = MessageBus()

    message_bus.subscribe(MessageTopic.MAP)
    message_bus.subscribe(MessageTopic.AGENT_PATH)

    message_bus.prepare_publisher(MessageTopic.ORDERS)

    return cast(MessageBusProtocol, message_bus)


def main(message_bus: MessageBusProtocol):
    map = message_bus.get_message(MessageTopic.MAP, wait=True)
    assert map
    order_planner = OrderPlanner(map)
    order_planner.start(message_bus)


def get_process() -> Process:
    return Process(
        name="order_planner",
        subsribe_topics=(MessageTopic.MAP, MessageTopic.ORDER_FINISHED),
        publish_topics=(MessageTopic.ORDERS,),
        process_function=main,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )
