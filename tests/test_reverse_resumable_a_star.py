import pytest
import typing as _t
from src.path_planning.reverse_resumable_a_star import (
    initialize_reverse_resumable_a_star,
    resume_rra,
)
from src.internal_types import (
    Environment,
    Coordinate2D,
    Coordinate2DWithTime,
    NodeState,
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


def test_initialize_reverse_resumable_a_star(setup_environment):
    env = setup_environment
    initial_node = Coordinate2D(x=0, y=0)
    goal_node = Coordinate2D(x=4, y=4)

    rra = initialize_reverse_resumable_a_star(env, initial_node, goal_node)
    assert isinstance(rra, _t.Generator)

    g_score = resume_rra(rra, goal_node)
    assert g_score >= 0


def test_resume_reverse_a_star(setup_environment):
    env = setup_environment
    initial_node = Coordinate2D(x=0, y=0)
    goal_node = Coordinate2D(x=4, y=4)

    rra = initialize_reverse_resumable_a_star(env, initial_node, goal_node)
    next(rra)

    g_score = rra.send(goal_node)
    assert g_score
    assert g_score >= 0

    intermediate_node = Coordinate2D(x=2, y=2)
    g_score = resume_rra(rra, intermediate_node)
    assert g_score >= 0


def test_reverse_a_star_no_path(setup_environment):
    env = setup_environment
    initial_node = Coordinate2D(x=0, y=0)
    goal_node = Coordinate2D(x=1, y=2)

    rra = initialize_reverse_resumable_a_star(env, initial_node, goal_node)

    blocked_node = Coordinate2D(x=1, y=1)
    g_score = resume_rra(rra, blocked_node)
    assert g_score == float("inf")


def test_resume_rra_with_time_coordinate(setup_environment):
    env = setup_environment
    initial_node = Coordinate2D(x=0, y=0)
    goal_node = Coordinate2D(x=4, y=4)

    rra = initialize_reverse_resumable_a_star(env, initial_node, goal_node)

    coordinate_with_time = Coordinate2DWithTime(x=4, y=4, time_step=10)
    g_score = resume_rra(rra, coordinate_with_time.to_node())
    assert g_score >= 0
