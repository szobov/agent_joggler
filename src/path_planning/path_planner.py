import dataclasses
import itertools
import typing as _t

import structlog

from ..internal_types import (
    Agent,
    AgentIdT,
    AgentPath,
    Coordinate2D,
    Coordinate2DWithTime,
    Environment,
    OrderFinished,
    PriorityQueueItem,
    ReservationTable,
    TimeT,
)
from ..message_transport import MessageBusProtocol, MessageTopic
from ..path_planning.common_a_star_utils import OpenSet, edge_cost, get_neighbors
from ..path_planning.order_tracker import OrderTracker
from ..path_planning.reverse_resumable_a_star import (
    initialize_reverse_resumable_a_star,
    resume_rra,
)

logger = structlog.getLogger(__name__)

SpaceTimeAStarSearchT: _t.TypeAlias = _t.Generator[
    _t.Sequence[Coordinate2DWithTime], None, None
]


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


def _update_or_wait_new_orders(
    message_bus: MessageBusProtocol, order_tracker: OrderTracker
):
    wait = False
    if len(order_tracker.not_assigned_orders) == 0 and not any(
        order_tracker.assigned_order.values()
    ):
        wait = False
    new_orders = message_bus.get_message(topic=MessageTopic.ORDERS, wait=wait)

    if new_orders:
        logger.info("received new orders", new_orders=new_orders)
        order_tracker.add_orders(new_orders)


def _last_time_step_from_agent_paths_iterator(
    reservation_table: ReservationTable,
) -> _t.Iterable[TimeT]:
    return (
        path[-1].time_step for path in reservation_table.agents_paths.values() if path
    )


def _get_ahead_of_time_agents_set(
    reservation_table: ReservationTable, time_window: TimeT
) -> set[Agent]:
    last_time_steps = list(_last_time_step_from_agent_paths_iterator(reservation_table))
    agents_to_ignore = set()
    if last_time_steps:
        min_last_time_steps = min(last_time_steps)
        agents_to_ignore = set(
            agent
            for agent, path in reservation_table.agents_paths.items()
            if path and path[-1].time_step - min_last_time_steps > time_window
        )
    return agents_to_ignore


def _windowed_hierarhical_cooperative_a_start_iteration(
    *,
    message_bus: MessageBusProtocol,
    time_window: int,
    env: Environment,
    reservation_table: ReservationTable,
    order_tracker: OrderTracker,
    agent_id_to_goal: dict[int, Coordinate2D],
    agent_to_space_time_a_star_search: dict[Agent, SpaceTimeAStarSearchT],
    agent_iteration_index: int,
    agent_path_last_sent_timestep: dict[Agent, TimeT],
    cleanedup_blocking_agents: set[Agent],
):
    _update_or_wait_new_orders(message_bus, order_tracker)
    num_agents = len(env.agents)

    agent_iteration_index += 1
    agent_iteration_index = agent_iteration_index % num_agents

    ahead_of_time_agents = _get_ahead_of_time_agents_set(
        reservation_table, time_window=time_window
    )

    for agent in filter(
        lambda a: a not in ahead_of_time_agents,
        itertools.islice(
            itertools.cycle(env.agents),
            agent_iteration_index,
            agent_iteration_index + num_agents,
        ),
    ):
        goal = agent_id_to_goal.get(agent.agent_id, agent.position)
        initial_pose = agent.position
        time_step = 0

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
                order_tracker=order_tracker,
                cleanedup_blocking_agents=cleanedup_blocking_agents,
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
        while cleanedup_blocking_agents:
            agent = cleanedup_blocking_agents.pop()
            goal = agent.position
            if (order := order_tracker.assigned_order.get(agent)) is not None:
                goal = order.goal
            agent_to_space_time_a_star_search[agent] = (
                _rebuild_space_time_a_start_from_last_node(
                    agent=agent,
                    reservation_table=reservation_table,
                    env=env,
                    goal_node=goal,
                    time_window=time_window,
                    order_tracker=order_tracker,
                    cleanedup_blocking_agents=cleanedup_blocking_agents,
                )
            )
    min_last_time_step = min(
        _last_time_step_from_agent_paths_iterator(reservation_table=reservation_table)
    )
    CLEANUP_THRESHOLD = time_window * 4
    reservation_table.cleanup(min_last_time_step - CLEANUP_THRESHOLD)

    _post_iteration(
        message_bus=message_bus,
        env=env,
        reservation_table=reservation_table,
        time_window=time_window,
        order_tracker=order_tracker,
        agent_path_last_sent_timestep=agent_path_last_sent_timestep,
        agent_to_space_time_a_star_search=agent_to_space_time_a_star_search,
        agent_id_to_goal=agent_id_to_goal,
        cleanedup_blocking_agents=cleanedup_blocking_agents,
    )


def _rebuild_space_time_a_start_from_last_node(
    *,
    agent: Agent,
    reservation_table: ReservationTable,
    env: Environment,
    goal_node: Coordinate2D,
    time_window: TimeT,
    order_tracker: OrderTracker,
    cleanedup_blocking_agents: set[Agent],
):
    last_position = reservation_table.agents_paths[agent][-1]
    initial_pose = last_position.to_node()
    time_step = last_position.time_step

    return space_time_a_star_search(
        env=env,
        reservation_table=reservation_table,
        agent=agent,
        time_window=time_window,
        goal=goal_node,
        timestep=time_step,
        initial_pose=initial_pose,
        order_tracker=order_tracker,
        cleanedup_blocking_agents=cleanedup_blocking_agents,
    )


def _post_iteration(
    message_bus: MessageBusProtocol,
    env: Environment,
    reservation_table: ReservationTable,
    time_window: int,
    order_tracker: OrderTracker,
    agent_path_last_sent_timestep: dict[Agent, TimeT],
    agent_to_space_time_a_star_search: dict[Agent, SpaceTimeAStarSearchT],
    agent_id_to_goal: dict[AgentIdT, Coordinate2D],
    cleanedup_blocking_agents: set[Agent],
):
    min_last_time_step = min(
        _last_time_step_from_agent_paths_iterator(reservation_table)
    )
    SEND_AGENT_PATH_TIME_THRESHOLD = time_window * 2
    for agent, path in reservation_table.agents_paths.items():
        last_time_step = path[-1].time_step
        for node_index, node in enumerate(reversed(path), start=1):
            if (
                last_time_step - node.time_step > SEND_AGENT_PATH_TIME_THRESHOLD
                and min_last_time_step - node.time_step > SEND_AGENT_PATH_TIME_THRESHOLD
            ):
                break
        else:
            continue
        path_to_send = path[: len(path) - node_index]
        if not path_to_send:
            continue
        rest = path[len(path) - node_index :]

        agent_path_last_sent_timestep[agent] = path_to_send[-1].time_step
        reservation_table.agents_paths[agent] = rest
        logger.info(
            "send new partial path",
            partial_path=path_to_send,
            rest_path=rest,
            agent=agent,
        )
        if path_to_send:
            message_bus.send_message(
                MessageTopic.AGENT_PATH,
                AgentPath(agent_id=agent.agent_id, path=list(path_to_send)),
            )
            last_time_step = path_to_send[-1].time_step
            for order in order_tracker.iterate_finished_orders(agent, last_time_step):
                message_bus.send_message(
                    MessageTopic.ORDER_FINISHED,
                    OrderFinished(order.order_id, agent_id=agent.agent_id),
                )
        goal_node = agent_id_to_goal.get(agent.agent_id)
        for node in path:
            if (
                agent not in order_tracker.assigned_order
                and len(order_tracker.not_assigned_orders) == 0
            ):
                break

            if node.to_node() != goal_node:
                continue
            if agent in order_tracker.assigned_order:
                order_tracker.agent_finished_task(agent, node.time_step)
            new_goal_node = order_tracker.assign_order(agent)
            agent_id_to_goal[agent.agent_id] = new_goal_node

            assert len(reservation_table.agents_paths[agent]) != 0
            agent_to_space_time_a_star_search[agent] = (
                _rebuild_space_time_a_start_from_last_node(
                    env=env,
                    agent=agent,
                    goal_node=new_goal_node,
                    time_window=time_window,
                    order_tracker=order_tracker,
                    cleanedup_blocking_agents=cleanedup_blocking_agents,
                    reservation_table=reservation_table,
                )
            )
            break


def windowed_hierarhical_cooperative_a_start(
    message_bus: MessageBusProtocol,
    env: Environment,
    time_window: TimeT,
    reservation_table: ReservationTable,
) -> None:
    logger.info("waiting for first orders")
    orders = message_bus.get_message(topic=MessageTopic.ORDERS, wait=True)
    assert orders
    agent_to_space_time_a_star_search: dict[Agent, SpaceTimeAStarSearchT] = {}
    agent_iteration_index = -1

    order_tracker = OrderTracker()
    order_tracker.add_orders(orders)

    agent_id_to_goal = {
        agent.agent_id: order_tracker.assign_order(agent) for agent in env.agents
    }

    agent_path_last_sent_timestep: dict[Agent, TimeT] = {
        agent: 0 for agent in env.agents
    }

    cleanedup_blocking_agents: set[Agent] = set()
    logger.info("planning loop is started", initial_tasks=orders)
    while not message_bus.get_message(MessageTopic.GLOBAL_STOP, wait=False):
        _windowed_hierarhical_cooperative_a_start_iteration(
            time_window=time_window,
            message_bus=message_bus,
            order_tracker=order_tracker,
            agent_id_to_goal=agent_id_to_goal,
            agent_to_space_time_a_star_search=agent_to_space_time_a_star_search,
            agent_iteration_index=agent_iteration_index,
            agent_path_last_sent_timestep=agent_path_last_sent_timestep,
            reservation_table=reservation_table,
            env=env,
            cleanedup_blocking_agents=cleanedup_blocking_agents,
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
    order_tracker: OrderTracker,
    cleanedup_blocking_agents: set[Agent],
) -> SpaceTimeAStarSearchT:
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
        order_tracker=order_tracker,
        cleanedup_blocking_agents=cleanedup_blocking_agents,
    )


def continue_space_time_a_star_search(
    env: Environment,
    time_window: int,
    reservation_table: ReservationTable,
    open_set: OpenSet,
    g_score: dict[Coordinate2D, float],
    f_score: dict[Coordinate2D, float],
    rra: _t.Generator[float | None, Coordinate2D, None],
    agent: Agent,
    goal: Coordinate2D,
    order_tracker: OrderTracker,
    cleanedup_blocking_agents: set[Agent],
) -> SpaceTimeAStarSearchT:
    came_from: dict[Coordinate2DWithTime, Coordinate2DWithTime] = dict()
    terminal_node = goal
    log = logger.bind(agent=agent, goal=goal)

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
                if reservation_table.is_node_occupied(current_node, next_time_step):
                    next_time_step -= 1
                    break
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
        min_next_time_step = float("inf")
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
                    agent=agent,
                ):
                    log.info(
                        "current node is occupied",
                        next_time_step=next_time_step,
                    )
                    is_current_node_reserved = True
                    break
                next_time_step += 1

            if is_current_node_reserved:
                log.debug(
                    "current_node is reserved. Abandoning this branch...",
                    next_time_step=next_time_step,
                )
                min_next_time_step = min(min_next_time_step, next_time_step)
                continue
            wait_time = next_time_step - current_node.time_step - 1
            assert (
                current_node.to_node() in g_score
            ), f"{current_node=}, {agent=}, {g_score=}"
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
        if len(open_set) == 0:
            log.info(
                "open set is empty. Check for a cleanup.",
                min_next_time_step=min_next_time_step,
            )
            if reservation_table.is_node_occupied(
                current_node,
                TimeT(min_next_time_step),
                agent=agent,
            ):
                log.info("start of the path is already occupied by another agent")

                blocked_by_agent, cleanup_until = (
                    reservation_table.cleanup_blocked_node(
                        current_node.to_node(), TimeT(min_next_time_step), agent
                    )
                )
                cleanedup_blocking_agents.add(blocked_by_agent)
                order_tracker.validate_finished_tasks(
                    cleaned_up_time_step=cleanup_until, agent=blocked_by_agent
                )

                open_set.add(current_node_with_priority)
        assert len(open_set), f"{open_set=}"

        log = log.try_unbind("neighbor_node")
