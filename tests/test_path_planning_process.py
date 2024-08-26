from unittest.mock import Mock

from src.internal_types import (
    Coordinate2D,
    Environment,
    Map,
    MapConfiguration,
    MapObject,
    MapObjectType,
    NodeState,
    ReservationTable,
    TimeT,
)
from src.message_transport import MessageBusProtocol, MessageTopic
from src.path_planning.process import (
    _convert_map_to_planner_env,
    _initialize_enviornment,
    _make_reservation_table,
    get_process,
    path_planning_process,
)
from src.runner import Process, ProcessFinishPolicy


def test_make_reservation_table():
    time_window: TimeT = 10
    reservation_table = _make_reservation_table(time_window)
    assert isinstance(reservation_table, ReservationTable)
    assert reservation_table.time_window == time_window


def test_convert_map_to_planner_env():
    map_configuration = MapConfiguration(width_units=5, height_units=5)
    map_objects = [
        MapObject(
            coordinates=Coordinate2D(x=1, y=1),
            object_type=MapObjectType.PILLAR,
            object_id=1,
        ),
        MapObject(
            coordinates=Coordinate2D(x=0, y=0),
            object_type=MapObjectType.AGENT,
            object_id=101,
        ),
    ]
    map = Map(configuration=map_configuration, objects=map_objects)
    env = _convert_map_to_planner_env(map)

    assert isinstance(env, Environment)
    assert env.x_dim == 5
    assert env.y_dim == 5
    assert len(env.agents) == 1
    assert env.agents[0].agent_id == 101
    assert env.grid[1][1] == NodeState.BLOCKED
    assert env.grid[0][0] == NodeState.FREE


def test_initialize_environment():
    message_bus = Mock(spec=MessageBusProtocol)

    map_configuration = MapConfiguration(width_units=5, height_units=5)
    map_objects = [
        MapObject(
            coordinates=Coordinate2D(x=1, y=1),
            object_type=MapObjectType.PILLAR,
            object_id=1,
        ),
        MapObject(
            coordinates=Coordinate2D(x=0, y=0),
            object_type=MapObjectType.AGENT,
            object_id=101,
        ),
    ]
    mock_map = Map(configuration=map_configuration, objects=map_objects)
    message_bus.get_message.return_value = mock_map

    env = _initialize_enviornment(message_bus)

    message_bus.get_message.assert_called_once_with(MessageTopic.MAP, wait=True)
    assert isinstance(env, Environment)
    assert len(env.agents) == 1
    assert env.grid[1][1] == NodeState.BLOCKED


def test_get_process():
    process = get_process()
    assert isinstance(process, Process)
    assert process.name == "path_planner"
    assert MessageTopic.MAP in process.subsribe_topics
    assert MessageTopic.ORDERS in process.subsribe_topics
    assert MessageTopic.AGENT_PATH in process.publish_topics
    assert MessageTopic.ORDER_FINISHED in process.publish_topics
    assert process.process_function == path_planning_process
    assert process.process_finish_policy == ProcessFinishPolicy.STOP_ALL
