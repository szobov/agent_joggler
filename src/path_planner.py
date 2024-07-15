import dataclasses
import typing as _t
import itertools

import structlog

from src.runner import Process, ProcessFinishPolicy

from .message_transport import (
    MessageBusProtocol,
    MessageTopic,
)

from .internal_types import (
    Agent,
    AgentIdT,
    AgentPath,
    Environment,
    Coordinate2D,
    Coordinate2DWithTime,
    PlannerTasks,
    TimeT,
    Map,
    NodeState,
    MapObjectType,
    ReservationTable,
    PriorityQueueItem,
)

from .common_a_star_utils import (
    get_neighbors,
    edge_cost,
    OpenSet,
)

from .reverse_resumable_a_star import (
    initialize_reverse_resumable_a_star,
    resume_rra,
)

logger = structlog.getLogger(__name__)


def make_reservation_table(time_window: TimeT) -> ReservationTable:
    return ReservationTable(time_window=time_window)


# https://en.wikipedia.org/wiki/A*_search_algorithm
def reconstruct_path(
    came_from_node_map: dict[Coordinate2DWithTime, Coordinate2DWithTime],
    current_node: Coordinate2DWithTime,
) -> _t.Sequence[Coordinate2DWithTime]:
    total_path = [current_node]
    while current_node in came_from_node_map.keys():
        current_node = came_from_node_map.pop(current_node)
        total_path.append(current_node)
    return list(reversed(total_path))


def follow_path(
    path: _t.Sequence[Coordinate2DWithTime],
    reservation_table: ReservationTable,
    agent: Agent,
):
    for prev_node, next_node in zip(path, path[1:]):
        assert (
            prev_node.time_step != next_node.time_step
        ), f"{prev_node.time_step} != {next_node.time_step}"

        for wait_time_step in range(prev_node.time_step, next_node.time_step):
            reservation_table.reserve_node(prev_node, wait_time_step, agent)
        if prev_node.to_node() == next_node.to_node():
            reservation_table.reserve_node(prev_node, next_node.time_step, agent)
        else:
            reservation_table.reserve_edge(
                prev_node, next_node, next_node.time_step, agent
            )
    last_node = path[-1]
    reservation_table.reserve_node(last_node, last_node.time_step, agent)


def time_expand_path(
    path: _t.Sequence[Coordinate2DWithTime],
) -> _t.Sequence[Coordinate2D]:
    expanded_path: list[Coordinate2D] = []
    for prev_node, next_node in zip(path, path[1:]):
        for _ in range(prev_node.time_step, next_node.time_step):
            expanded_path.append(prev_node.to_node())
    expanded_path.append(path[-1].to_node())
    return expanded_path


def _need_wait(
    time_step: TimeT,
    reservation_table: ReservationTable,
    curr_node: Coordinate2D,
    next_node: Coordinate2D,
) -> bool:
    is_next_node_occupied = reservation_table.is_node_occupied(
        next_node,
        time_step,
    )
    is_edge_occpuied = reservation_table.is_edge_occupied(
        curr_node,
        next_node,
        time_step,
    )
    return is_edge_occpuied or is_next_node_occupied


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


def _windowed_hierarhical_cooperative_a_start_iteration(
    *,
    message_bus: MessageBusProtocol,
    time_window: int,
    env: Environment,
    reservation_table: ReservationTable,
    agent_id_to_goal: dict[int, Coordinate2D],
    agent_to_space_time_a_star_search: dict[
        Agent, _t.Generator[_t.Sequence[Coordinate2DWithTime], None, None]
    ],
    agent_iteration_index: int,
    agents_reached_goal: int,
    agent_path_last_sent_timestep: dict[Agent, TimeT],
):
    wait = False
    if len(agent_id_to_goal) == agents_reached_goal:
        wait = True
    new_orders = message_bus.get_message(topic=MessageTopic.PLANNER_TASKS, wait=wait)

    new_orders_map = {}
    if new_orders:
        logger.info("received new orders", new_orders=new_orders)
        new_orders_map = _convert_planner_tasks_to_agent_to_goal_map(new_orders)

    num_agents = len(env.agents)

    agent_iteration_index += 1
    agent_iteration_index = agent_iteration_index % num_agents

    for agent in itertools.islice(
        itertools.cycle(env.agents),
        agent_iteration_index,
        agent_iteration_index + num_agents - 1,
    ):
        goal = agent_id_to_goal.get(agent.agent_id, agent.position)
        initial_pose = agent.position
        time_step = 0
        if (
            new_goal := new_orders_map.get(agent.agent_id)
        ) is not None and new_goal != goal:
            logger.info("got new goal", agent=agent, old_goal=goal, new_goal=new_goal)
            if len(reservation_table.agents_paths[agent]) != 0:
                last_position = reservation_table.agents_paths[agent][-1]
                initial_pose = last_position.to_node()
                time_step = last_position.time_step
            del agent_to_space_time_a_star_search[agent]
            agent_id_to_goal[agent.agent_id] = new_goal
            goal = new_goal

        if agent in agent_to_space_time_a_star_search:
            stas_search = agent_to_space_time_a_star_search[agent]
        else:
            stas_search = space_time_a_star_search(
                env=env,
                reservation_table=reservation_table,
                agent=agent,
                time_window=time_window,
                goal=goal,
                timestep=time_step,
                initial_pose=initial_pose,
            )
            agent_to_space_time_a_star_search[agent] = stas_search
        new_partial_path = list(next(stas_search))
        previous_partial_path = reservation_table.agents_paths[agent]
        if len(previous_partial_path) and (
            previous_partial_path[-1] == new_partial_path[0]
        ):
            new_partial_path = new_partial_path[1:]
        logger.debug(
            "joining new path",
            new_partial_path=new_partial_path,
            previous_partial_path=previous_partial_path,
            agent=agent,
        )
        reservation_table.agents_paths[agent] = (
            list(previous_partial_path) + new_partial_path
        )

    agents_reached_goal = 0
    for agent, path in reservation_table.agents_paths.items():
        last_timestep_sent = agent_path_last_sent_timestep[agent]
        if (path[-1].time_step - last_timestep_sent) >= time_window * 2:
            for node_index, node in enumerate(path):
                if node.time_step - last_timestep_sent > time_window:
                    break
            path_to_send = path[:node_index]
            rest = path[node_index:]
            agent_path_last_sent_timestep[agent] = path_to_send[-1].time_step
            reservation_table.agents_paths[agent] = rest
            logger.info(
                "send new partial path",
                partial_path=path_to_send,
                rest_path=rest,
                agent=agent,
            )
            # check for goal is reached
            goal_node = agent_id_to_goal.get(agent.agent_id)
            if any(map(lambda p: p.to_node() == goal_node, path)):
                agents_reached_goal += 1
            message_bus.send_message(
                MessageTopic.AGENT_PATH,
                AgentPath(agent_id=agent.agent_id, path=list(path_to_send)),
            )
        # XXX: I send the path here, and when I did it, shouldn't I
        #      cleanup this path from the reservation table?
        #      I can also try to save "last_send_timestep" and cleanup
        #      nodes that are older than this timestep.
        #
        # XXX: should I cleanup reservation_table right here?
        #
        # XXX: current issue: here I always send the whole path, so I clearly need to do two things:
        #      1. Cleanup reservation table
        #      2. Track "current time" in order planner and visualizer, since I must not move robot back in time.


def _convert_planner_tasks_to_agent_to_goal_map(
    planner_tasks: PlannerTasks,
) -> dict[AgentIdT, Coordinate2D]:
    return {task.agent_id: task.goal for task in planner_tasks.tasks}


def windowed_hierarhical_cooperative_a_start(
    message_bus: MessageBusProtocol,
    env: Environment,
    time_window: TimeT,
    reservation_table: ReservationTable,
) -> None:

    logger.info("waiting for first planner tasks")
    planner_tasks = message_bus.get_message(topic=MessageTopic.PLANNER_TASKS, wait=True)
    assert planner_tasks

    agent_to_space_time_a_star_search: dict[
        Agent, _t.Generator[_t.Sequence[Coordinate2DWithTime], None, None]
    ] = {}
    agent_iteration_index = -1
    agent_id_to_goal = _convert_planner_tasks_to_agent_to_goal_map(planner_tasks)
    agent_path_last_sent_timestep: dict[Agent, TimeT] = {
        agent: 0 for agent in env.agents
    }
    agents_reached_goal = 0

    logger.info("planning loop is started", initial_tasks=planner_tasks)
    while not message_bus.get_message(MessageTopic.GLOBAL_STOP, wait=False):
        _windowed_hierarhical_cooperative_a_start_iteration(
            time_window=time_window,
            message_bus=message_bus,
            agent_id_to_goal=agent_id_to_goal,
            agent_to_space_time_a_star_search=agent_to_space_time_a_star_search,
            agents_reached_goal=agents_reached_goal,
            agent_iteration_index=agent_iteration_index,
            agent_path_last_sent_timestep=agent_path_last_sent_timestep,
            reservation_table=reservation_table,
            env=env,
        )
    return


def space_time_a_star_search(
    env: Environment,
    reservation_table: ReservationTable,
    agent: Agent,
    goal: Coordinate2D,
    time_window: int,
    timestep: TimeT,
    initial_pose: Coordinate2D,
) -> _t.Generator[_t.Sequence[Coordinate2DWithTime], None, None]:
    logger.info(
        "starting new space_time_a*", agent=agent, goal=goal, time_step=timestep
    )
    rra = initialize_reverse_resumable_a_star(env, goal, initial_pose)
    time_step: TimeT = timestep
    open_set = OpenSet()

    g_score: dict[Coordinate2D, float] = dict()
    g_score[initial_pose] = 0

    f_score = dict()
    f_score[initial_pose] = resume_rra(rra, initial_pose)

    open_set.add(
        PriorityQueueItem(
            f_score[initial_pose],
            Coordinate2DWithTime.from_node(initial_pose, time_step),
        )
    )
    return continue_space_time_a_star_search(
        env=env,
        time_window=time_window,
        reservation_table=reservation_table,
        open_set=open_set,
        f_score=f_score,
        g_score=g_score,
        rra=rra,
        agent=agent,
        goal=goal,
    )


def continue_space_time_a_star_search(
    env: Environment,
    time_window: int,
    reservation_table: ReservationTable,
    open_set: OpenSet,
    g_score: dict[Coordinate2D, float],
    f_score: dict[Coordinate2D, float],
    rra: _t.Generator[float, Coordinate2D, None],
    agent: Agent,
    goal: Coordinate2D,
) -> _t.Generator[_t.Sequence[Coordinate2DWithTime], None, None]:
    came_from: dict[Coordinate2DWithTime, Coordinate2DWithTime] = dict()
    terminal_node = goal
    log = logger.bind(agent=agent)

    start_interval_time_step = 0

    while True:
        current_node_with_priority = open_set.pop()
        current_node = current_node_with_priority.node
        log = log.bind(current_node=current_node)
        assert type(current_node) is Coordinate2DWithTime
        if (
            current_node.time_step % time_window == 0
        ) and current_node.time_step != start_interval_time_step:
            path = reconstruct_path(came_from, current_node)
            log.info("time window is over", path=path)
            follow_path(path, reservation_table, agent)
            yield path
            current_node = reservation_table.agents_paths[agent][-1]
            h_score = resume_rra(rra, current_node)
            open_set = OpenSet()

            open_set.add(
                dataclasses.replace(
                    dataclasses.replace(current_node_with_priority, node=current_node),
                    f_score=h_score,
                )
            )
            start_interval_time_step = current_node.time_step
            continue

        if current_node.to_node() == terminal_node:
            log.info("arrived to terminal node")
            next_time_step = current_node.time_step + 1
            while (
                next_time_step % time_window != 0
            ) and not reservation_table.is_node_occupied(current_node, next_time_step):
                next_time_step += 1
            if next_time_step != current_node.time_step + 1:
                new_current_node = dataclasses.replace(
                    current_node, time_step=next_time_step
                )
                came_from[new_current_node] = current_node
                open_set.add(
                    dataclasses.replace(
                        current_node_with_priority, node=new_current_node
                    )
                )
                continue

        for neighbor_node in get_neighbors(env, current_node):
            log = log.bind(neighbor_node=neighbor_node)
            next_time_step = current_node.time_step + 1

            is_current_node_reserved = False
            while _need_wait(
                next_time_step,
                reservation_table,
                current_node,
                neighbor_node,
            ):
                if reservation_table.is_node_occupied(
                    current_node,
                    next_time_step,
                ):
                    logger.debug("current node is occupied")
                    is_current_node_reserved = True
                    break
                next_time_step += 1

            if is_current_node_reserved:
                log.debug("current_node is reserved. Abandoning this branch...")
                continue
            wait_time = next_time_step - current_node.time_step - 1
            tentative_g_score = g_score[current_node.to_node()] + edge_cost(
                env, current_node, neighbor_node
            )
            tentative_g_score_plus_wait_time = tentative_g_score + wait_time

            came_from[Coordinate2DWithTime.from_node(neighbor_node, next_time_step)] = (
                current_node
            )
            g_score[neighbor_node] = tentative_g_score_plus_wait_time
            node_h_score = resume_rra(rra, neighbor_node)
            node_f_score = node_h_score + tentative_g_score_plus_wait_time
            f_score[neighbor_node] = node_f_score
            log.debug(
                "adding new node to open_set",
                open_set=open_set.item_queue,
                node_f_score=node_f_score,
            )
            open_set.upsert(
                PriorityQueueItem(
                    node=Coordinate2DWithTime.from_node(neighbor_node, next_time_step),
                    f_score=node_f_score,
                )
            )
        if len(open_set) == 0 and reservation_table.is_node_occupied(
            current_node,
            current_node.time_step
            + 1,  # XXX: it's not right to just add 1 here, likely next_time_step should be used
            agent=agent,
        ):
            log.info("start of the path is already occupied by another agent")
            # TODO: clamp cleanup to a specific length
            reservation_table.cleanup_blocked_node(
                current_node.to_node(), current_node.time_step + 1, agent
            )
            open_set.add(current_node_with_priority)

        log = log.try_unbind("neighbor_node")


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
            MessageTopic.PLANNER_TASKS,
        ),
        publish_topics=(MessageTopic.AGENT_PATH,),
        process_function=path_planning_process,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )
