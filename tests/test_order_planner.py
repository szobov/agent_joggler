from unittest.mock import Mock

import pytest

from src.environment.generator import Map
from src.internal_types import Coordinate2D, MapObject, MapObjectType, Order
from src.message_transport import MessageTopic
from src.orders.order_planner import OrderPlanner, Pallet, Stack, get_process


@pytest.fixture
def mock_map():
    map_objects = [
        MapObject(
            coordinates=Coordinate2D(x=1, y=1),
            object_type=MapObjectType.STACK,
            object_id=1,
        ),
        MapObject(
            coordinates=Coordinate2D(x=2, y=2),
            object_type=MapObjectType.PICKUP_STATION,
            object_id=2,
        ),
        MapObject(
            coordinates=Coordinate2D(x=0, y=0),
            object_type=MapObjectType.AGENT,
            object_id=3,
        ),
    ]
    return Map(configuration=None, objects=map_objects)


def test_stack_operations():
    stack = Stack(
        map_object=Mock(),
        _pallets=[Pallet(object_id=1), Pallet(object_id=2)],
    )

    stack.add_pallet(Pallet(object_id=3))
    assert len(stack.pallets) == 3
    assert stack.pallets[3].object_id == 3

    bottom_pallet = stack.get_bottom_pallet()
    assert bottom_pallet.object_id == 1
    assert len(stack.pallets) == 2


def test_order_planner_initialization(mock_map):
    order_planner = OrderPlanner(map=mock_map)

    assert len(order_planner._stacks) == 1
    assert len(order_planner._agents) == 1
    assert len(order_planner._pickup_stations) == 1


@pytest.mark.skip
def test_order_planner_generate_orders(mock_map):
    order_planner = OrderPlanner(map=mock_map)
    orders = order_planner._generate_orders()

    assert len(orders) > 0
    assert all(isinstance(order, Order) for order in orders)


def test_order_planner_refill_stacks(mock_map):
    order_planner = OrderPlanner(map=mock_map)

    initial_stack = next(iter(order_planner._stacks.values()))
    initial_pallet_count = len(initial_stack.pallets)

    order_planner._refill_stacks()
    assert len(initial_stack.pallets) >= initial_pallet_count


def test_get_process():
    process = get_process()
    assert process.name == "order_planner"
    assert MessageTopic.MAP in process.subsribe_topics
    assert MessageTopic.ORDERS in process.publish_topics
