import pytest

from src.internal_types import (
    Agent,
    Coordinate2D,
    Coordinate2DWithTime,
    ReservationTable,
)


@pytest.fixture
def setup_environment():
    agent_1 = Agent(agent_id=1, position=Coordinate2D(x=0, y=0))
    agent_2 = Agent(agent_id=2, position=Coordinate2D(x=1, y=1))
    agent_3 = Agent(agent_id=3, position=Coordinate2D(x=2, y=2))
    reservation_table = ReservationTable(time_window=10)
    return agent_1, agent_2, agent_3, reservation_table


def test_reserve_and_check_node(setup_environment):
    agent_1, _, _, reservation_table = setup_environment
    node = Coordinate2D(x=0, y=0)
    time_step = 5

    reservation_table.reserve_node(node, time_step, agent_1)

    assert reservation_table.is_node_occupied(node, time_step)
    assert not reservation_table.is_node_occupied(node, time_step + 1)

    assert not reservation_table.is_node_occupied(node, time_step, agent_1)

    assert reservation_table._reservation_table.get((node, node, time_step)) == agent_1


def test_reserve_and_check_edge(setup_environment):
    agent_1, _, _, reservation_table = setup_environment
    node_from = Coordinate2D(x=0, y=0)
    node_to = Coordinate2D(x=1, y=1)
    time_step = 5

    reservation_table.reserve_edge(node_from, node_to, time_step, agent_1)
    assert reservation_table.is_edge_occupied(node_from, node_to, time_step)
    assert not reservation_table.is_edge_occupied(node_from, node_to, time_step + 1)

    reservation_table.reserve_edge(node_to, node_from, time_step, agent_1)
    assert reservation_table.is_edge_occupied(node_to, node_from, time_step)


def test_cleanup(setup_environment):
    agent_1, _, _, reservation_table = setup_environment
    node = Coordinate2D(x=0, y=0)
    time_step = 5

    reservation_table.reserve_node(node, time_step, agent_1)
    reservation_table.cleanup(time_step + 1)
    assert not reservation_table.is_node_occupied(node, time_step)

    reservation_table.reserve_node(node, time_step + 2, agent_1)
    reservation_table.cleanup(time_step + 1)
    assert reservation_table.is_node_occupied(node, time_step + 2)


def test_cleanup_blocked_node(setup_environment):
    agent_1, agent_2, _, reservation_table = setup_environment
    node = Coordinate2D(x=1, y=1)
    time_step = 5

    path = [
        Coordinate2DWithTime(x=0, y=0, time_step=4),
        Coordinate2DWithTime(x=1, y=1, time_step=5),
    ]
    reservation_table.agents_paths[agent_2] = path
    reservation_table.reserve_node(node, time_step, agent_2)

    blocked_agent, blocked_time = reservation_table.cleanup_blocked_node(
        node, time_step, agent_1
    )
    assert blocked_agent == agent_2
    assert blocked_time == time_step

    assert not reservation_table.is_node_occupied(node, time_step)
    assert len(reservation_table._reservation_table) == 0


def test_multiple_agents_reservation(setup_environment):
    agent_1, agent_2, agent_3, reservation_table = setup_environment
    node = Coordinate2D(x=2, y=2)
    time_step = 5

    reservation_table.reserve_node(node, time_step, agent_1)
    reservation_table.reserve_node(node, time_step + 1, agent_2)

    assert reservation_table.is_node_occupied(node, time_step)
    assert reservation_table.is_node_occupied(node, time_step + 1)

    with pytest.raises(AssertionError):
        reservation_table.reserve_node(node, time_step, agent_3)


def test_coordinate2DWithTime_conversions():
    node = Coordinate2D(x=1, y=1)
    time_step = 5
    node_with_time = Coordinate2DWithTime.from_node(node, time_step)

    assert node_with_time.x == 1
    assert node_with_time.y == 1
    assert node_with_time.time_step == 5

    converted_node = node_with_time.to_node()
    assert converted_node == node

    node_with_time_2 = Coordinate2DWithTime(x=1, y=1, time_step=6)
    assert node_with_time != node_with_time_2


def test_reservation_table_consistency(setup_environment):
    agent_1, agent_2, _, reservation_table = setup_environment

    path_1 = [
        Coordinate2DWithTime(x=0, y=0, time_step=1),
        Coordinate2DWithTime(x=1, y=1, time_step=2),
        Coordinate2DWithTime(x=2, y=2, time_step=3),
    ]

    path_2 = [
        Coordinate2DWithTime(x=2, y=2, time_step=4),
        Coordinate2DWithTime(x=3, y=3, time_step=5),
    ]

    for step in path_1:
        reservation_table.reserve_node(step.to_node(), step.time_step, agent_1)

    for step in path_2:
        reservation_table.reserve_node(step.to_node(), step.time_step, agent_2)

    assert reservation_table.is_node_occupied(Coordinate2D(x=1, y=1), 2)
    assert reservation_table.is_node_occupied(Coordinate2D(x=2, y=2), 3)
    assert reservation_table.is_node_occupied(Coordinate2D(x=2, y=2), 4)
    assert reservation_table.is_node_occupied(Coordinate2D(x=3, y=3), 5)

    reservation_table.cleanup(3)
    assert not reservation_table.is_node_occupied(Coordinate2D(x=1, y=1), 2)
    assert reservation_table.is_node_occupied(Coordinate2D(x=3, y=3), 5)
