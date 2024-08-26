import typing as _t
import pytest
from unittest.mock import Mock
from src.internal_types import (
    Agent,
    Coordinate2D,
    Coordinate2DWithTime,
    Environment,
    ReservationTable,
    Order,
    Orders,
    OrderType,
    NodeState,
)
from src.path_planning.path_planner import (
    space_time_a_star_search,
    _windowed_hierarhical_cooperative_a_start_iteration,
    reconstruct_path,
    follow_path,
    OrderTracker,
)


@pytest.fixture
def setup_environment():
    env = Environment(
        x_dim=5,
        y_dim=5,
        grid=[
            [
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
            ],
            [
                NodeState.FREE,
                NodeState.BLOCKED,
                NodeState.BLOCKED,
                NodeState.BLOCKED,
                NodeState.FREE,
            ],
            [
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
                NodeState.BLOCKED,
                NodeState.FREE,
            ],
            [
                NodeState.FREE,
                NodeState.BLOCKED,
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
            ],
            [
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
                NodeState.FREE,
            ],
        ],
        agents=[],
    )
    return env


@pytest.fixture
def setup_agent():
    return Agent(agent_id=1, position=Coordinate2D(x=0, y=0))


@pytest.fixture
def setup_reservation_table():
    return ReservationTable(time_window=10)


@pytest.fixture
def setup_order_tracker():
    return OrderTracker()


def test_reconstruct_path():
    node_a = Coordinate2DWithTime(x=0, y=0, time_step=0)
    node_b = Coordinate2DWithTime(x=1, y=0, time_step=1)
    node_c = Coordinate2DWithTime(x=2, y=0, time_step=2)

    came_from = {
        node_b: node_a,
        node_c: node_b,
    }

    path = reconstruct_path(came_from, node_c)

    assert path == [node_a, node_b, node_c]


def test_follow_path(setup_reservation_table, setup_agent):
    reservation_table = setup_reservation_table
    agent = setup_agent

    path = [
        Coordinate2DWithTime(x=0, y=0, time_step=0),
        Coordinate2DWithTime(x=1, y=0, time_step=1),
        Coordinate2DWithTime(x=2, y=0, time_step=2),
    ]

    for node in path:
        assert not reservation_table.is_node_occupied(
            node.to_node(), node.time_step, agent
        )

    follow_path(path, reservation_table, agent)

    for node in path:
        assert reservation_table.is_node_occupied(node.to_node(), node.time_step)

    for node in path:
        assert not reservation_table.is_node_occupied(
            node.to_node(), node.time_step, agent
        )


def test_windowed_hierarhical_cooperative_a_start_iteration(
    setup_environment, setup_reservation_table, setup_order_tracker, setup_agent
):
    env = setup_environment
    reservation_table = setup_reservation_table
    order_tracker = setup_order_tracker
    agent = setup_agent

    env.agents.append(agent)

    message_bus = Mock()

    mock_order = Order(
        order_id=1,
        order_type=OrderType.PICKUP,
        goal=Coordinate2D(x=2, y=2),
        pallet_id=1,
    )
    message_bus.get_message.return_value = Orders(orders=[mock_order])

    agent_id_to_goal = {agent.agent_id: Coordinate2D(x=2, y=2)}
    agent_to_space_time_a_star_search = {}
    agent_iteration_index = 0
    agent_path_last_sent_timestep = {agent: 0}
    cleanedup_blocking_agents = set()

    _windowed_hierarhical_cooperative_a_start_iteration(
        message_bus=message_bus,
        time_window=5,
        env=env,
        reservation_table=reservation_table,
        order_tracker=order_tracker,
        agent_id_to_goal=agent_id_to_goal,
        agent_to_space_time_a_star_search=agent_to_space_time_a_star_search,
        agent_iteration_index=agent_iteration_index,
        agent_path_last_sent_timestep=agent_path_last_sent_timestep,
        cleanedup_blocking_agents=cleanedup_blocking_agents,
    )

    assert message_bus.get_message.called


def test_space_time_a_star_search(
    setup_environment, setup_reservation_table, setup_agent, setup_order_tracker
):
    env = setup_environment
    reservation_table = setup_reservation_table
    agent = setup_agent
    order_tracker = setup_order_tracker
    cleanedup_blocking_agents = set()

    goal = Coordinate2D(x=4, y=4)
    search = space_time_a_star_search(
        env=env,
        reservation_table=reservation_table,
        agent=agent,
        goal=goal,
        time_window=10,
        timestep=0,
        initial_pose=agent.position,
        order_tracker=order_tracker,
        cleanedup_blocking_agents=cleanedup_blocking_agents,
    )

    assert isinstance(search, _t.Generator)


def test_continue_space_time_a_star_search(
    setup_environment, setup_reservation_table, setup_agent, setup_order_tracker
):
    env = setup_environment
    reservation_table = setup_reservation_table
    agent = setup_agent
    order_tracker = setup_order_tracker
    cleanedup_blocking_agents = set()

    goal = Coordinate2D(x=4, y=4)
    rra = space_time_a_star_search(
        env=env,
        reservation_table=reservation_table,
        agent=agent,
        goal=goal,
        time_window=10,
        timestep=0,
        initial_pose=agent.position,
        order_tracker=order_tracker,
        cleanedup_blocking_agents=cleanedup_blocking_agents,
    )

    result = next(rra)

    assert isinstance(result, list)
    assert len(result) > 0
