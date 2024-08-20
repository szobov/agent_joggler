from collections import defaultdict
import bisect

import pygame

from ..internal_types import (
    Coordinate2D,
    Map,
    MapObjectType,
)
from ..message_transport import MessageBusProtocol, MessageTopic


class MapVisualizer:
    def __init__(self, map: Map):
        pygame.init()
        self.size = self.width, self.height = 800, 600
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption("Warehouse Generator")

        self.map = map
        self.current_step = 0.0
        self.agent_paths = defaultdict(list)
        self.agents = {
            agent.object_id: agent
            for agent in self.map.objects
            if agent.object_type == MapObjectType.AGENT
        }
        self.object_colors = {
            MapObjectType.STACK: pygame.Color("yellow"),
            MapObjectType.MAINTENANCE_AREA: pygame.Color("green"),
            MapObjectType.PICKUP_STATION: pygame.Color("blue"),
            MapObjectType.PILLAR: pygame.Color("gray"),
            MapObjectType.AGENT: pygame.Color("red"),
        }

        self.unit_pixel_size = min(
            self.width / self.map.configuration.width_units,
            self.height / self.map.configuration.height_units,
        )

        self.clock = pygame.time.Clock()

    def run(self, message_bus: MessageBusProtocol):
        while not message_bus.get_message(MessageTopic.GLOBAL_STOP, wait=False):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return

            self.screen.fill((0, 0, 0))  # Clear screen with black background
            self.draw_grid()
            for object in filter(
                lambda o: o.object_type != MapObjectType.AGENT, self.map.objects
            ):
                self.draw_object(
                    object.coordinates,
                    self.map.configuration.object_sizes[object.object_type.value],
                    self.object_colors[object.object_type],
                    object.object_id,
                )
            self.draw_agents(message_bus=message_bus)
            pygame.display.flip()  # Update the full display Surface to the screen
            self.clock.tick(60)  # Limit to 60 frames per second

    def draw_grid(self):
        for index, x in enumerate(range(0, self.width, int(self.unit_pixel_size))):
            pygame.draw.line(
                self.screen, pygame.Color("white"), (x, 0), (x, self.height), 2
            )
            self.draw_text(
                str(index),
                x + self.unit_pixel_size // 2,
                self.unit_pixel_size // 2,
                pygame.Color("white"),
            )
        for index, y in enumerate(range(0, self.height, int(self.unit_pixel_size))):
            pygame.draw.line(
                self.screen, pygame.Color("white"), (0, y), (self.width, y), 2
            )
            self.draw_text(
                str(index),
                self.unit_pixel_size // 2,
                y + self.unit_pixel_size // 2,
                pygame.Color("white"),
            )

    def draw_object(self, object, size, object_color, object_id):
        x, y = object.x, object.y
        x_pixel, y_pixel = x * self.unit_pixel_size, y * self.unit_pixel_size
        size_x, size_y = size.x * self.unit_pixel_size, size.y * self.unit_pixel_size

        rect = pygame.Rect(x_pixel, y_pixel, size_x, size_y)
        pygame.draw.rect(self.screen, object_color, rect)

        self.draw_text(
            str(object_id), rect.centerx, rect.centery, pygame.Color("white")
        )

    def draw_text(self, text, x, y, color):
        font = pygame.font.Font(None, 24)
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=(x, y))
        self.screen.blit(text_surface, text_rect)

    def draw_agents(self, message_bus: MessageBusProtocol):
        self.current_step += 0.05
        while agent_path := message_bus.get_message(
            MessageTopic.AGENT_PATH, wait=False
        ):
            self.agent_paths[agent_path.agent_id] += agent_path.path

        for agent_id, agent in self.agents.items():
            path = []
            if agent_id in self.agent_paths:
                path = self.agent_paths[agent_id]

            if len(path) > 1:
                step = int(self.current_step)
                position = bisect.bisect_left(path, step, key=lambda x: x.time_step)
                if position == len(path):
                    position -= 1
                item = path[position]

                if item.time_step == step and position < len(path) - 1:
                    start = item
                    end = path[position + 1]
                elif item.time_step > step and position > 0:
                    start = path[position - 1]
                    end = item
                else:
                    start = end = item

                dt = self.current_step - step
                if (
                    abs(start.time_step - end.time_step) > 1.0
                    and end.time_step - step > 1.0
                ):
                    x = start.x
                    y = start.y
                else:
                    x, y = (
                        start.x * (1 - dt) + end.x * dt,
                        start.y * (1 - dt) + end.y * dt,
                    )
                self.draw_object(
                    Coordinate2D(x, y),
                    self.map.configuration.object_sizes[MapObjectType.AGENT.value],
                    self.object_colors[MapObjectType.AGENT],
                    agent_id,
                )
            else:
                self.draw_object(
                    agent.coordinates,
                    self.map.configuration.object_sizes[MapObjectType.AGENT.value],
                    self.object_colors[MapObjectType.AGENT],
                    agent_id,
                )
