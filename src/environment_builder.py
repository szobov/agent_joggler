from .internal_types import Agent, Environment, NodeState, Node, Heuristic
from .common_a_star_utils import heuristic


def set_agent(env: Environment, agent: Agent):
    pos_x = agent.position.position_x
    pos_y = agent.position.position_y
    assert env.grid[pos_x][pos_y] == NodeState.FREE
    env.agents.append(agent)


def build_environment(x_dim: int, y_dim: int) -> Environment:
    graph = [[NodeState.FREE] * y_dim for _ in range(x_dim)]
    return Environment(x_dim=x_dim, y_dim=y_dim, grid=graph, agents=[])


def build_cross_env() -> Environment:
    cross_grid_pattern = [
        [3, 3, 3, 3, 2, 3, 3, 3],
        [3, 3, 3, 3, 1, 3, 3, 3],
        [3, 3, 3, 3, 0, 3, 3, 3],
        [3, 3, 3, 3, 0, 3, 3, 3],
        [2, 1, 0, 0, 0, 0, 1, 2],
        [3, 3, 3, 3, 0, 3, 3, 3],
        [3, 3, 3, 3, 0, 3, 3, 3],
        [3, 3, 3, 3, 1, 3, 3, 3],
        [3, 3, 3, 3, 2, 3, 3, 3],
    ]
    x_dim = len(cross_grid_pattern)
    y_dim = len(cross_grid_pattern[0])

    env = build_environment(x_dim, y_dim)

    agent_poses: list[Node] = []
    goal_poses: list[Node] = []
    for x in range(x_dim):
        for y in range(y_dim):
            pattern_value = cross_grid_pattern[x][y]
            match pattern_value:
                case 0:
                    env.grid[x][y] = NodeState.FREE
                case 1:
                    agent_poses.append(Node(x, y))
                case 2:
                    goal_poses.append(Node(x, y))
                case 3:
                    env.grid[x][y] = NodeState.BLOCKED
    assert len(agent_poses) == len(goal_poses)
    for agen_id, agent_pos in enumerate(agent_poses):
        goal_pos = sorted(
            goal_poses,
            key=lambda node: -heuristic(Heuristic.EUCLIDEAN_DISTANCE, agent_pos, node),
        )[0]
        agent = Agent(agent_id=agen_id, position=agent_pos, goal=goal_pos)
        goal_poses.remove(goal_pos)
        set_agent(env, agent)
    return env
