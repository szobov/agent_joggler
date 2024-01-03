import dataclasses
import typing as _t

import structlog

from .utils import is_debug

from .internal_types import (
    Agent,
    Environment,
    Node,
    NodeWithTime,
    TimeT,
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


def make_reservation_table(agents: _t.Sequence[Agent]) -> ReservationTable:
    return ReservationTable(agents=agents)


# https://en.wikipedia.org/wiki/A*_search_algorithm
def reconstruct_path(
    came_from_node_map: dict[NodeWithTime, NodeWithTime], current_node: NodeWithTime
) -> _t.Sequence[NodeWithTime]:
    total_path = [current_node]
    while current_node in came_from_node_map.keys():
        current_node = came_from_node_map.pop(current_node)
        total_path.append(current_node)
    return list(reversed(total_path))


def follow_path(
    path: _t.Sequence[NodeWithTime], reservation_table: ReservationTable, agent: Agent
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


def time_expand_path(path: _t.Sequence[NodeWithTime]) -> _t.Sequence[Node]:
    expanded_path: list[Node] = []
    for prev_node, next_node in zip(path, path[1:]):
        for _ in range(prev_node.time_step, next_node.time_step):
            expanded_path.append(prev_node.to_node())
    expanded_path.append(path[-1].to_node())
    return expanded_path


def _need_wait(
    time_step: TimeT,
    reservation_table: ReservationTable,
    curr_node: Node,
    next_node: Node,
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


def windowed_hierarhical_cooperative_a_start(
    env: Environment,
) -> dict[Agent, _t.Sequence[Node]]:
    agents_paths: _t.DefaultDict[Agent, _t.Sequence[NodeWithTime]] = _t.DefaultDict(
        list
    )
    reservation_table = make_reservation_table(env.agents)
    # TODO: partial paths:
    # 4. What means: This can be achieved by interleaving the searches, so that roughly 2n/d units replan at the same time?
    TIME_WINDOW = 8
    agent_to_space_time_a_star_search: dict[
        Agent, _t.Generator[_t.Sequence[NodeWithTime], None, None]
    ] = {}
    while not all_agent_reached_destination(agents_paths, env):
        try:
            for agent in env.agents:
                if agent in agent_to_space_time_a_star_search:
                    stas_search = agent_to_space_time_a_star_search[agent]
                else:
                    stas_search = space_time_a_star_search(
                        env=env,
                        reservation_table=reservation_table,
                        agent=agent,
                        time_window=TIME_WINDOW,
                    )
                    agent_to_space_time_a_star_search[agent] = stas_search
                new_partial_path = list(next(stas_search))
                logger.info(
                    "joining new path", new_partial_path=new_partial_path, agent=agent
                )
                previous_partial_path = agents_paths[agent]
                if len(previous_partial_path) and (
                    previous_partial_path[-1] == new_partial_path[0]
                ):
                    new_partial_path = new_partial_path[1:]
                agents_paths[agent] = list(previous_partial_path) + new_partial_path
        except Exception:
            if is_debug() and len(agents_paths):
                return {
                    agent: time_expand_path(path)
                    for agent, path in agents_paths.items()
                }
            else:
                raise
    logger.info("all agents reached destination")
    return {agent: time_expand_path(path) for agent, path in agents_paths.items()}


def all_agent_reached_destination(
    agent_paths: dict[Agent, _t.Sequence[NodeWithTime]], env: Environment
) -> bool:
    num_of_agents = len(env.agents)
    number_of_reached = sum(
        1
        for _ in filter(
            lambda item: item[0].goal == item[1][-1].to_node(), agent_paths.items()
        )
    )
    return num_of_agents == number_of_reached


def space_time_a_star_search(
    env: Environment,
    reservation_table: ReservationTable,
    agent: Agent,
    time_window: int,
) -> _t.Generator[_t.Sequence[NodeWithTime], None, None]:
    rra = initialize_reverse_resumable_a_star(env, agent.goal, agent.position)
    time_step: TimeT = 0
    open_set = OpenSet()

    g_score: dict[Node, float] = dict()
    g_score[agent.position] = 0

    f_score = dict()
    f_score[agent.position] = resume_rra(rra, agent.position)

    open_set.add(
        PriorityQueueItem(
            f_score[agent.position],
            NodeWithTime.from_node(agent.position, time_step),
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
    )


def continue_space_time_a_star_search(
    env: Environment,
    time_window: int,
    reservation_table: ReservationTable,
    open_set: OpenSet,
    g_score: dict[Node, float],
    f_score: dict[Node, float],
    rra: _t.Generator[float, Node, None],
    agent: Agent,
) -> _t.Generator[_t.Sequence[NodeWithTime], None, None]:
    came_from: dict[NodeWithTime, NodeWithTime] = dict()
    terminal_node = agent.goal
    log = logger.bind(agent=agent)

    start_interval_time_step = 0

    reservation_table.free_initialy_reserved_node(agent.position)
    while True:
        # XXX: Current problem: node is initially reserved and then ignored during the search.
        # possible solutions:
        current_node_with_priority = open_set.pop()
        current_node = current_node_with_priority.node
        log = log.bind(current_node=current_node)
        assert type(current_node) is NodeWithTime
        if (
            current_node.time_step % time_window == 0
        ) and current_node.time_step != start_interval_time_step:
            path = reconstruct_path(came_from, current_node)
            log.info("time window is over", path=path)
            follow_path(path, reservation_table, agent)
            yield path
            h_score = resume_rra(rra, current_node)
            open_set = OpenSet()

            open_set.add(
                dataclasses.replace(current_node_with_priority, f_score=h_score)
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
            if reservation_table.is_node_initially_reserved(neighbor_node):
                log.info("neighbor_node is initially reserved")
                continue
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
                    logger.info("current node is occupied")
                    is_current_node_reserved = True
                    break
                next_time_step += 1

            if is_current_node_reserved:
                log.info("current_node is reserved. Abandoning this branch...")
                continue
            wait_time = next_time_step - current_node.time_step - 1
            tentative_g_score = g_score[current_node.to_node()] + edge_cost(
                env, current_node, neighbor_node
            )
            tentative_g_score_plus_wait_time = tentative_g_score + wait_time

            came_from[
                NodeWithTime.from_node(neighbor_node, next_time_step)
            ] = current_node
            g_score[neighbor_node] = tentative_g_score_plus_wait_time
            node_h_score = resume_rra(rra, neighbor_node)
            node_f_score = node_h_score + tentative_g_score_plus_wait_time
            f_score[neighbor_node] = node_f_score
            log.info(
                "adding new node to open_set",
                open_set=open_set.item_queue,
                node_f_score=node_f_score,
            )
            open_set.upsert(
                PriorityQueueItem(
                    node=NodeWithTime.from_node(neighbor_node, next_time_step),
                    f_score=node_f_score,
                )
            )
        log = log.try_unbind("neighbor_node")
