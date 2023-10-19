import arcade
import math

from .internal_types import Environment, NodeState

# Draw a grid of circles with dimentions (x_dim, y_dim)
# Color "agent" circles.
# Color "goal" circles.
# Draw a line, representing a path
# If head-on or meet collision is happening, draw a red circle around the agent
# and stop execution.


class EnvironmentVisualizer(arcade.Window):
    WINDOW_TITLE = "Environment Visualizer"
    BACKGROUND_COLOR = arcade.color.WHITE
    GRID_SIZE = 30

    def __init__(
        self, window_width: int, window_height: int, env: Environment, agent_paths
    ):
        super().__init__(window_width, window_height, self.WINDOW_TITLE)
        self.env = env
        self.current_step = 0
        self.agent_paths = agent_paths
        arcade.set_background_color(self.BACKGROUND_COLOR)

    def on_draw(self):
        arcade.start_render()
        for x in range(self.env.x_dim):
            for y in range(self.env.y_dim):
                if self.env.grid[x][y] == NodeState.BLOCKED:
                    color = arcade.color.BLACK
                elif self.env.grid[x][y] == NodeState.FREE:
                    color = arcade.color.WHITE
                else:
                    color = arcade.color.WHITE

                arcade.draw_rectangle_filled(
                    y * self.GRID_SIZE + self.GRID_SIZE / 2,
                    x * self.GRID_SIZE + self.GRID_SIZE / 2,
                    self.GRID_SIZE,
                    self.GRID_SIZE,
                    color,
                )

        for agent in self.env.agents:
            goal = agent.goal
            x, y = goal.position_x, goal.position_y
            arcade.draw_rectangle_filled(
                y * self.GRID_SIZE + self.GRID_SIZE / 2,
                x * self.GRID_SIZE + self.GRID_SIZE / 2,
                self.GRID_SIZE,
                self.GRID_SIZE,
                arcade.color.RED,
            )

        for _, path in self.agent_paths.items():
            agent_color = arcade.color.GREEN
            if self.current_step < len(path):
                dt, step = math.modf(self.current_step)
                step = int(step)
                node = path[step]
                x, y = node.position_x, node.position_y
                next_node = path[min(step + 1, len(path) - 1)]
                new_x = (next_node.position_x - x) * dt + x
                new_y = (next_node.position_y - y) * dt + y

                arcade.draw_rectangle_filled(
                    new_y * self.GRID_SIZE + self.GRID_SIZE / 2,
                    new_x * self.GRID_SIZE + self.GRID_SIZE / 2,
                    self.GRID_SIZE,
                    self.GRID_SIZE,
                    agent_color,
                )

        self.current_step += 0.05
        if self.current_step >= max(len(path) for path in self.agent_paths.values()):
            self.current_step = 0

    def run(self):
        arcade.run()
