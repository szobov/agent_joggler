import random
from unittest.mock import Mock

import pytest

from src.internal_types import (
    AgentPath,
    Coordinate2D,
    Coordinate2DWithTime,
    Map,
    MapConfiguration,
    MapObject,
    MapObjectType,
    PlannerTask,
)
from src.message_transport import MessageTopic
from src.orders.order_planner import Order, OrderPlanner, OrderType


@pytest.fixture
def map() -> Map:
    configuration = MapConfiguration(width_units=5, height_units=5)
    return Map(
        configuration=configuration,
        objects=[
            MapObject(
                coordinates=Coordinate2D(x=5, y=5),
                object_type=MapObjectType.STACK,
                object_id=0,
            ),
            MapObject(
                coordinates=Coordinate2D(x=1, y=1),
                object_type=MapObjectType.AGENT,
                object_id=1,
            ),
            MapObject(
                coordinates=Coordinate2D(x=5, y=1),
                object_type=MapObjectType.PICKUP_STATION,
                object_id=2,
            ),
        ],
    )


def test_ok(map: Map):
    random.seed(41)
    order_planner = OrderPlanner(map)
    message_bus = Mock()
    agent_to_order = {}
    pickup_orders_generator, orders = order_planner._iterate(
        message_bus=message_bus,
        agent_to_order=agent_to_order,
        pickup_orders_generator=None,
    )
    assert pickup_orders_generator is not None
    assert orders == [
        Order(
            planner_task=PlannerTask(
                order_id=0, agent_id=1, goal=Coordinate2D(x=5, y=5)
            ),
            pallet_id=0,
            order_type=OrderType.FREEUP,
        )
    ]
    order_planner._send_orders(
        orders=orders, message_bus=message_bus, agent_to_order=agent_to_order
    )
    assert agent_to_order == {1: orders[0]}

    def mocked_get_message(topic, wait):
        assert topic == MessageTopic.AGENT_PATH
        assert wait
        return AgentPath(
            agent_id=1,
            path=[
                Coordinate2DWithTime(x=1, y=1, time_step=0),
                Coordinate2DWithTime(x=5, y=5, time_step=1),
            ],
        )

    message_bus.get_message.side_effect = mocked_get_message

    pickup_orders_generator, orders = order_planner._iterate(
        message_bus=message_bus,
        agent_to_order=agent_to_order,
        pickup_orders_generator=pickup_orders_generator,
    )
    assert orders == [
        Order(
            planner_task=PlannerTask(
                order_id=0, agent_id=1, goal=Coordinate2D(x=5, y=5)
            ),
            pallet_id=1,
            order_type=OrderType.PICKUP,
        ),
    ]

    pickup_orders_generator, orders = order_planner._iterate(
        message_bus=message_bus,
        agent_to_order=agent_to_order,
        pickup_orders_generator=pickup_orders_generator,
    )
    assert pickup_orders_generator is None
    assert orders == []
