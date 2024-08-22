import structlog

from ..internal_types import Agent, Environment, Map, MapObjectType, NodeState
from ..message_transport import MessageBusProtocol, MessageTopic
from ..path_planning.path_planner import (
    make_reservation_table,
    windowed_hierarhical_cooperative_a_start,
)
from ..runner import Process, ProcessFinishPolicy

logger = structlog.getLogger(__name__)


def _convert_map_to_planner_env(map: Map) -> Environment:
    x_dim = map.configuration.width_units
    y_dim = map.configuration.height_units
    agents = [
        Agent(agent_id=obj.object_id, position=obj.coordinates)
        for obj in filter(
            lambda object: object.object_type == MapObjectType.AGENT, map.objects
        )
    ]

    grid = [[NodeState.FREE] * y_dim for _ in range(x_dim)]
    for object in map.objects:
        if object.object_type == MapObjectType.PILLAR:
            grid[object.coordinates.x][object.coordinates.y] = NodeState.BLOCKED
    return Environment(x_dim=x_dim, y_dim=y_dim, grid=grid, agents=agents)


def initialize_enviornment(message_bus: MessageBusProtocol) -> Environment:
    logger.info("waiting map")
    map = message_bus.get_message(MessageTopic.MAP, wait=True)
    logger.info("map received")
    assert map
    logger.info("converting map to planner environment")
    return _convert_map_to_planner_env(map)


def path_planning_process(message_bus: MessageBusProtocol) -> None:
    TIME_WINDOW = 8
    logger.info("time window is set", time_window=TIME_WINDOW)
    env = initialize_enviornment(message_bus)
    reservation_table = make_reservation_table(time_window=TIME_WINDOW)
    windowed_hierarhical_cooperative_a_start(
        message_bus, env, TIME_WINDOW, reservation_table
    )


def get_process() -> Process:
    return Process(
        name="path_planner",
        subsribe_topics=(
            MessageTopic.MAP,
            MessageTopic.ORDERS,
        ),
        publish_topics=(MessageTopic.AGENT_PATH, MessageTopic.ORDER_FINISHED),
        process_function=path_planning_process,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )
