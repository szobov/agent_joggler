from collections import defaultdict, deque
from dataclasses import dataclass
import pathlib
from typing import Type
from dataclasses_avroschema.schema_generator import AvroModel

import pytest

from src.internal_types import (
    Environment,
    Map,
    PlannerTasks,
    AgentPath,
    Coordinate2DWithTime,
)
from src.path_planner import (
    _windowed_hierarhical_cooperative_a_start_iteration,
    make_reservation_table,
    _convert_map_to_planner_env,
    _convert_planner_tasks_to_agent_to_goal_map,
)
from src.message_transport import MessageTopic


@pytest.fixture
def path_to_datadir() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "data"


def _read_message_from_filesystem[
    T
](path_to_datadir: pathlib.Path, filename: str, message_class: Type[T]) -> T:
    assert issubclass(message_class, AvroModel)
    # Apache-Avro expects un-pretty-printed json
    data = b" ".join((path_to_datadir / filename).read_bytes().split())
    return message_class.deserialize(
        data,
        serialization_type="avro-json",
        create_instance=True,
    )


@pytest.fixture
def first_planner_tasks(path_to_datadir: pathlib.Path) -> PlannerTasks:
    return _read_message_from_filesystem(
        path_to_datadir, "first_planner_tasks.json", PlannerTasks
    )


@pytest.fixture
def second_planner_tasks(path_to_datadir: pathlib.Path) -> PlannerTasks:
    return _read_message_from_filesystem(
        path_to_datadir, "second_planner_tasks.json", PlannerTasks
    )


@pytest.fixture
def third_planner_tasks(path_to_datadir: pathlib.Path) -> PlannerTasks:
    return _read_message_from_filesystem(
        path_to_datadir, "third_planner_tasks.json", PlannerTasks
    )


@pytest.fixture
def map(path_to_datadir: pathlib.Path) -> Map:
    return _read_message_from_filesystem(path_to_datadir, "map.json", Map)


@pytest.fixture
def env(map: Map) -> Environment:
    return _convert_map_to_planner_env(map)


@dataclass
class MockedMessageTransport:

    _get_messages = defaultdict(deque)
    _sent_messages = defaultdict(deque)

    def _add_new_message(self, topic, message):
        self._get_messages[topic].append(message)

    def get_message(self, topic, wait):
        del wait
        return self._get_messages[topic].popleft()

    def send_message(self, topic, message):
        self._sent_messages[topic].append(message)


def test_ok(
    env: Environment,
    first_planner_tasks: PlannerTasks,
    second_planner_tasks: PlannerTasks,
    third_planner_tasks: PlannerTasks,
):
    message_bus = MockedMessageTransport()
    TIME_WINDOW = 8
    reservation_table = make_reservation_table(TIME_WINDOW)

    agent_to_space_time_a_star_search = {}
    agent_iteration_index = -1
    agent_id_to_goal = _convert_planner_tasks_to_agent_to_goal_map(first_planner_tasks)
    agent_path_last_sent_timestep = {agent: 0 for agent in env.agents}
    agents_reached_goal = 0

    def _run_until_message_sent(new_message):
        message_bus._add_new_message(MessageTopic.PLANNER_TASKS, new_message)
        while len(message_bus._sent_messages.get(MessageTopic.AGENT_PATH, [])) == 0:
            _windowed_hierarhical_cooperative_a_start_iteration(
                message_bus=message_bus,
                time_window=TIME_WINDOW,
                env=env,
                reservation_table=reservation_table,
                agent_iteration_index=agent_iteration_index,
                agents_reached_goal=agents_reached_goal,
                agent_path_last_sent_timestep=agent_path_last_sent_timestep,
                agent_id_to_goal=agent_id_to_goal,
                agent_to_space_time_a_star_search=agent_to_space_time_a_star_search,
            )
        return message_bus._sent_messages[MessageTopic.AGENT_PATH].popleft()

    assert _run_until_message_sent(None) == AgentPath(
        agent_id=1,
        path=[
            Coordinate2DWithTime(x=1, y=4, time_step=0),
            Coordinate2DWithTime(x=1, y=4, time_step=1),
            Coordinate2DWithTime(x=1, y=3, time_step=2),
            Coordinate2DWithTime(x=0, y=3, time_step=3),
            Coordinate2DWithTime(x=0, y=3, time_step=4),
            Coordinate2DWithTime(x=0, y=2, time_step=5),
            Coordinate2DWithTime(x=0, y=2, time_step=6),
        ],
    )

    assert _run_until_message_sent(None) == AgentPath(
        agent_id=0,
        path=[
            Coordinate2DWithTime(x=0, y=3, time_step=0),
            Coordinate2DWithTime(x=0, y=2, time_step=1),
            Coordinate2DWithTime(x=0, y=1, time_step=2),
            Coordinate2DWithTime(x=0, y=1, time_step=8),
        ],
    )

    assert _run_until_message_sent(third_planner_tasks) == AgentPath(
        agent_id=1, path=[Coordinate2DWithTime(x=0, y=1, time_step=9)]
    )
    assert _run_until_message_sent(second_planner_tasks) == AgentPath(
        agent_id=2,
        path=[
            Coordinate2DWithTime(x=2, y=3, time_step=0),
            Coordinate2DWithTime(x=3, y=3, time_step=1),
            Coordinate2DWithTime(x=3, y=2, time_step=2),
            Coordinate2DWithTime(x=4, y=2, time_step=3),
            Coordinate2DWithTime(x=5, y=2, time_step=4),
            Coordinate2DWithTime(x=6, y=2, time_step=5),
            Coordinate2DWithTime(x=7, y=2, time_step=6),
            Coordinate2DWithTime(x=8, y=2, time_step=7),
            Coordinate2DWithTime(x=9, y=2, time_step=8),
        ],
    )

    assert _run_until_message_sent(None) == AgentPath(
        agent_id=0,
        path=[
            Coordinate2DWithTime(x=1, y=1, time_step=9),
            Coordinate2DWithTime(x=2, y=1, time_step=10),
            Coordinate2DWithTime(x=2, y=0, time_step=11),
            Coordinate2DWithTime(x=1, y=0, time_step=12),
            Coordinate2DWithTime(x=1, y=1, time_step=13),
        ],
    )

    assert _run_until_message_sent(None) == AgentPath(
        agent_id=1,
        path=[
            Coordinate2DWithTime(x=0, y=1, time_step=16),
            Coordinate2DWithTime(x=0, y=2, time_step=17),
        ],
    )

    assert _run_until_message_sent(None) == AgentPath(
        agent_id=2,
        path=[
            Coordinate2DWithTime(x=10, y=2, time_step=9),
            Coordinate2DWithTime(x=11, y=2, time_step=10),
            Coordinate2DWithTime(x=12, y=2, time_step=11),
            Coordinate2DWithTime(x=13, y=2, time_step=12),
            Coordinate2DWithTime(x=14, y=2, time_step=13),
            Coordinate2DWithTime(x=15, y=2, time_step=14),
            Coordinate2DWithTime(x=16, y=2, time_step=15),
            Coordinate2DWithTime(x=17, y=2, time_step=16),
        ],
    )

    assert _run_until_message_sent(None) == AgentPath(
        agent_id=1,
        path=[
            Coordinate2DWithTime(x=0, y=1, time_step=16),
            Coordinate2DWithTime(x=0, y=2, time_step=17),
        ],
    )
