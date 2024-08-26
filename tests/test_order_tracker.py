import pytest

from src.internal_types import Agent, Coordinate2D, Order, Orders, OrderType, TimeT
from src.path_planning.order_tracker import OrderTracker


@pytest.fixture
def setup_agents():
    agent_1 = Agent(agent_id=1, position=Coordinate2D(x=0, y=0))
    agent_2 = Agent(agent_id=2, position=Coordinate2D(x=1, y=1))
    return agent_1, agent_2


@pytest.fixture
def setup_orders():
    order_1 = Order(
        order_id=1,
        order_type=OrderType.PICKUP,
        goal=Coordinate2D(x=2, y=2),
        pallet_id=1,
    )
    order_2 = Order(
        order_id=2,
        order_type=OrderType.DELIVERY,
        goal=Coordinate2D(x=3, y=3),
        pallet_id=1,
    )
    order_3 = Order(
        order_id=3,
        order_type=OrderType.PICKUP,
        goal=Coordinate2D(x=4, y=4),
        pallet_id=2,
    )
    orders = Orders(orders=[order_1, order_2, order_3])
    return orders


@pytest.fixture
def setup_order_tracker():
    return OrderTracker()


def test_add_orders(setup_order_tracker, setup_orders):
    order_tracker = setup_order_tracker
    orders = setup_orders

    order_tracker.add_orders(orders)
    assert len(order_tracker.not_assigned_orders) == len(orders.orders)


def test_assign_order(setup_order_tracker, setup_agents, setup_orders):
    order_tracker = setup_order_tracker
    orders = setup_orders
    agent_1, _ = setup_agents

    order_tracker.add_orders(orders)
    goal = order_tracker.assign_order(agent_1)

    assert goal == orders.orders[0].goal
    assert agent_1 in order_tracker.assigned_order


def test_assign_order_no_orders(setup_order_tracker, setup_agents):
    order_tracker = setup_order_tracker
    agent_1, _ = setup_agents

    goal = order_tracker.assign_order(agent_1)

    assert goal == agent_1.position
    assert agent_1 not in order_tracker.assigned_order


def test_iterate_finished_orders(setup_order_tracker, setup_agents, setup_orders):
    order_tracker = setup_order_tracker
    orders = setup_orders
    agent_1, _ = setup_agents

    order_tracker.add_orders(orders)
    order_tracker.assign_order(agent_1)
    order_tracker.agent_finished_task(agent_1, 5)

    finished_orders = list(order_tracker.iterate_finished_orders(agent_1, 10))

    assert len(finished_orders) == 1
    assert finished_orders[0] == orders.orders[0]


def test_validate_finished_tasks(setup_order_tracker, setup_agents, setup_orders):
    order_tracker = setup_order_tracker
    orders = setup_orders
    agent_1, _ = setup_agents

    order_tracker.add_orders(orders)
    order_tracker.assign_order(agent_1)
    order_tracker.agent_finished_task(agent_1, 5)

    order_tracker.validate_finished_tasks(6, agent_1)
    assert len(order_tracker.not_assigned_orders) == 2


def test_agent_finished_task(setup_order_tracker, setup_agents, setup_orders):
    order_tracker = setup_order_tracker
    orders = setup_orders
    agent_1, _ = setup_agents

    order_tracker.add_orders(orders)
    order_tracker.assign_order(agent_1)

    order_tracker.agent_finished_task(agent_1, 5)

    assert agent_1 not in order_tracker.assigned_order
    assert len(order_tracker.finished_orders[agent_1]) == 1
    assert order_tracker.finished_orders[agent_1][0][1] == orders.orders[0]
