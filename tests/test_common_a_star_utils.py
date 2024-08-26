import pytest
from src.internal_types import (
    Environment,
    Heuristic,
    Coordinate2D,
    NodeState,
    PriorityQueueItem,
)
from src.path_planning.common_a_star_utils import (
    heuristic,
    get_neighbors,
    edge_cost,
    OpenSet,
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


def test_heuristic():
    node_a = Coordinate2D(x=0, y=0)
    node_b = Coordinate2D(x=3, y=4)

    manhattan = heuristic(Heuristic.MANHATTAN_DISTANCE, node_a, node_b)
    euclidean = heuristic(Heuristic.EUCLIDEAN_DISTANCE, node_a, node_b)

    assert manhattan == 7
    assert euclidean == 5.0


def test_get_neighbors(setup_environment):
    env = setup_environment
    node = Coordinate2D(x=2, y=2)

    neighbors = list(get_neighbors(env, node))

    assert Coordinate2D(x=3, y=2) in neighbors
    assert Coordinate2D(x=2, y=1) in neighbors
    assert Coordinate2D(x=2, y=2) in neighbors
    assert len(neighbors) == 3


def test_edge_cost(setup_environment):
    env = setup_environment
    node_a = Coordinate2D(x=0, y=0)
    node_b = Coordinate2D(x=1, y=1)

    cost = edge_cost(env, node_a, node_b)

    assert cost == 1.0


def test_open_set_add():
    open_set = OpenSet()
    item = PriorityQueueItem(f_score=1.0, node=Coordinate2D(x=0, y=0))

    open_set.add(item)

    assert len(open_set) == 1
    assert Coordinate2D(x=0, y=0) in open_set


def test_open_set_upsert():
    open_set = OpenSet()
    item1 = PriorityQueueItem(f_score=2.0, node=Coordinate2D(x=0, y=0))
    item2 = PriorityQueueItem(f_score=1.0, node=Coordinate2D(x=0, y=0))

    open_set.add(item1)
    open_set.upsert(item2)

    assert len(open_set) == 1
    assert Coordinate2D(x=0, y=0) in open_set
    assert open_set.pop().f_score == 1.0


def test_open_set_pop():
    open_set = OpenSet()
    item1 = PriorityQueueItem(f_score=2.0, node=Coordinate2D(x=0, y=0))
    item2 = PriorityQueueItem(f_score=1.0, node=Coordinate2D(x=1, y=1))

    open_set.add(item1)
    open_set.add(item2)

    assert len(open_set) == 2
    popped_item = open_set.pop()
    assert popped_item.f_score == 1.0
    assert len(open_set) == 1
    assert Coordinate2D(x=1, y=1) not in open_set


def test_open_set_contains():
    open_set = OpenSet()
    item = PriorityQueueItem(f_score=1.0, node=Coordinate2D(x=0, y=0))

    open_set.add(item)

    assert Coordinate2D(x=0, y=0) in open_set
    assert Coordinate2D(x=1, y=1) not in open_set
