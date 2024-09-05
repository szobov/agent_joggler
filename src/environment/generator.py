"""
Y
^
|
|----> X
"""

import dataclasses
import enum
import itertools
import random
import typing as _t

import structlog

from src.environment.visualizer import MapVisualizer
from src.runner import Process, ProcessFinishPolicy

from ..internal_types import (
    Coordinate2D,
    Map,
    MapConfiguration,
    MapObject,
    MapObjectType,
)
from ..message_transport import MessageBus, MessageBusProtocol, MessageTopic

logger = structlog.getLogger(__name__)


@enum.unique
class Border(enum.Enum):
    TOP = enum.auto()
    RIGHT = enum.auto()
    BOTTOM = enum.auto()
    LEFT = enum.auto()


def random_2d_coords(
    range_x: tuple[int, int], range_y: tuple[int, int]
) -> Coordinate2D:
    if range_x[0] == range_x[1]:
        x = range_x[0]
    else:
        x = random.randint(range_x[0], range_x[1] - 1)
    if range_y[0] == range_y[1]:
        y = range_y[0]
    else:
        y = random.randint(range_y[0], range_y[1] - 1)
    return Coordinate2D(x, y)


@dataclasses.dataclass
class MapGenerator:
    map: Map

    def __post_init__(self):
        self._generate_objects()

    def _get_object_far_corner(self, object: MapObject):
        size = self.map.configuration.object_sizes[object.object_type.value]
        return object.coordinates.x + size.x, object.coordinates.y + size.y

    def _generate_objects(self):
        RANDOMLY_PLACED_OBJECTS = {
            MapObjectType.PILLAR.value,
        }

        for maintanance_area_id in range(
            self.map.configuration.object_numbers[MapObjectType.MAINTENANCE_AREA.value]
        ):
            self._generate_maintenance_area(maintanance_area_id)
        for object_type, num in filter(
            lambda keyval: keyval[0] in RANDOMLY_PLACED_OBJECTS,
            self.map.configuration.object_numbers.items(),
        ):
            for object_id in range(num):
                self._generate_object(
                    MapObjectType(object_type),
                    object_id,
                    (0, self.map.configuration.width_units - 1),
                    (0, self.map.configuration.height_units - 1),
                    ignore_object_overlap=set(),
                )
        for agent_id in range(
            self.map.configuration.object_numbers[MapObjectType.AGENT.value]
        ):
            self._generate_agent(agent_id)

        self._generate_clustered_objects(
            MapObjectType.PICKUP_STATION,
            opposite_to_type=MapObjectType.MAINTENANCE_AREA,
        )

        self._generate_clustered_objects(MapObjectType.STACK, opposite_to_type=None)

        assert len(self.map.objects) == sum(
            self.map.configuration.object_numbers.values()
        ), f"{len(self.map.objects)} == {sum(self.map.configuration.object_numbers.values())}"

    def _generate_object(
        self,
        type: MapObjectType,
        object_id: int,
        range_x: tuple[int, int],
        range_y: tuple[int, int],
        ignore_object_overlap: set[MapObject],
    ) -> MapObject:
        overlap = True
        log = logger.bind(
            object_type=type,
            object_id=object_id,
            range_x=range_x,
            range_y=range_y,
            ignore_object_overlap=ignore_object_overlap,
        )
        MAX_ATTEMPTS = 30
        attempt = iter(range(1, MAX_ATTEMPTS + 1))
        while overlap and next(attempt, False):
            log.debug("Attempt to place an object on map")
            coords = random_2d_coords(range_x, range_y)
            coords = Coordinate2D(
                max(0, min(coords.x, self.map.configuration.width_units - 1)),
                max(0, min(coords.y, self.map.configuration.height_units - 1)),
            )
            log = log.bind(coords=coords)
            possible_object = MapObject(coords, type, object_id)
            far_x, far_y = self._get_object_far_corner(possible_object)

            overlap = False
            for other_object in filter(
                lambda object: object not in ignore_object_overlap, self.map.objects
            ):
                other_object_far_x, other_object_far_y = self._get_object_far_corner(
                    other_object
                )
                overlap_x = (
                    other_object.coordinates.x
                    <= possible_object.coordinates.x
                    <= other_object_far_x - 1
                ) or (
                    possible_object.coordinates.x
                    <= other_object.coordinates.x
                    <= far_x - 1
                )
                overlap_y = (
                    other_object.coordinates.y
                    <= possible_object.coordinates.y
                    <= other_object_far_y - 1
                    or possible_object.coordinates.y
                    <= other_object.coordinates.y
                    <= far_y - 1
                )
                overlap = overlap_x and overlap_y
                if overlap:
                    log.debug("object overlaps", other_object=other_object)
                    break

            if not overlap:
                log.debug("Object is placed")
                self.map.objects.append(possible_object)
                return possible_object
            log = log.unbind("coords")
        assert (
            False
        ), f"Unable to place an object in {MAX_ATTEMPTS}. Most likely an unlucky random.seed"

    def _generate_agent(self, agent_id: int):
        maintenance_area = next(
            filter(
                lambda obj: obj.object_type == MapObjectType.MAINTENANCE_AREA,
                random.sample(self.map.objects, len(self.map.objects)),
            )
        )
        far_x, far_y = self._get_object_far_corner(maintenance_area)
        self._generate_object(
            MapObjectType.AGENT,
            agent_id,
            (maintenance_area.coordinates.x, far_x),
            (maintenance_area.coordinates.y, far_y),
            ignore_object_overlap={
                maintenance_area,
            },
        )

    def _generate_maintenance_area(self, object_id: int):
        border = random.choice(list(Border))

        maintenance_area_size = self.map.configuration.object_sizes[
            MapObjectType.MAINTENANCE_AREA.value
        ]
        x_range, y_range = self._get_along_the_border_coordinates_range(
            border, maintenance_area_size
        )

        self._generate_object(
            MapObjectType.MAINTENANCE_AREA, object_id, x_range, y_range, set()
        )

    def _get_along_the_border_coordinates_range(
        self, border: Border, object_size: Coordinate2D
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        x_range = (0, self.map.configuration.width_units - 1 - object_size.x)
        y_range = (0, self.map.configuration.height_units - 1 - object_size.y)

        match border:
            case Border.BOTTOM:
                y_range = (0, object_size.y)
            case Border.RIGHT:
                x_range = (
                    self.map.configuration.width_units - 1 - object_size.x,
                    self.map.configuration.width_units - 1 - object_size.x,
                )
            case Border.TOP:
                y_range = (
                    self.map.configuration.height_units - 1 - object_size.y,
                    self.map.configuration.height_units - 1 - object_size.y,
                )
            case Border.LEFT:
                x_range = (0, object_size.x)
        return (x_range, y_range)

    def _generate_clustered_objects(
        self, object_type: MapObjectType, opposite_to_type: _t.Optional[MapObjectType]
    ):
        num_objects = self.map.configuration.object_numbers[object_type.value]

        CLUSTER_SIZE = random.randint(2, 4)

        for objects in itertools.batched(range(num_objects), CLUSTER_SIZE):
            objects_center_range = self._get_along_the_border_coordinates_range(
                random.choice(list(Border)),
                self.map.configuration.object_sizes[object_type.value],
            )
            if opposite_to_type is not None:
                opposite_object = next(
                    filter(
                        lambda obj: obj.object_type == opposite_to_type,
                        random.sample(self.map.objects, len(self.map.objects)),
                    )
                )
                opposite_object_far_corner = self._get_object_far_corner(
                    opposite_object
                )
                opposite_object_border = Border.LEFT

                if opposite_object.coordinates.x == 0:
                    opposite_object_border = Border.LEFT
                elif opposite_object.coordinates.y == 0:
                    opposite_object_border = Border.BOTTOM
                elif (
                    opposite_object_far_corner[0] == self.map.configuration.width_units
                ):
                    opposite_object_border = Border.RIGHT
                else:
                    opposite_object_border = Border.TOP

                pickup_cluster_center_border = Border.RIGHT
                match opposite_object_border:
                    case Border.LEFT:
                        pickup_cluster_center_border = Border.RIGHT
                    case Border.RIGHT:
                        pickup_cluster_center_border = Border.LEFT
                    case Border.TOP:
                        pickup_cluster_center_border = Border.BOTTOM
                    case Border.BOTTOM:
                        pickup_cluster_center_border = Border.TOP

                objects_center_range = self._get_along_the_border_coordinates_range(
                    pickup_cluster_center_border,
                    self.map.configuration.object_sizes[object_type.value],
                )

            objects_ids = list(objects)
            objects_center_id = objects_ids[len(objects_ids) // 2]

            cluster_center_object = self._generate_object(
                object_type,
                objects_center_id,
                objects_center_range[0],
                objects_center_range[1],
                set(),
            )
            object_size = self.map.configuration.object_sizes[object_type.value]
            for side_object_id in filter(
                lambda p_id: p_id != objects_center_id, objects_ids
            ):
                x_offset = random.randint(1, CLUSTER_SIZE) * object_size.x
                y_offset = random.randint(1, CLUSTER_SIZE) * object_size.y
                self._generate_object(
                    object_type,
                    side_object_id,
                    (
                        cluster_center_object.coordinates.x - x_offset,
                        cluster_center_object.coordinates.x + x_offset,
                    ),
                    (
                        cluster_center_object.coordinates.y - y_offset,
                        cluster_center_object.coordinates.y + y_offset,
                    ),
                    set(),
                )


def get_message_bus() -> MessageBusProtocol:
    message_bus = MessageBus()
    message_bus.subscribe(MessageTopic.GLOBAL_STOP)
    message_bus.subscribe(MessageTopic.AGENT_PATH)

    message_bus.prepare_publisher(MessageTopic.MAP)

    return _t.cast(MessageBusProtocol, message_bus)


def main(message_bus: MessageBusProtocol):
    map_configuration = MapConfiguration(
        width_units=18,
        height_units=12,
        object_sizes={
            MapObjectType.MAINTENANCE_AREA.value: Coordinate2D(3, 3),
            MapObjectType.STACK.value: Coordinate2D(1, 1),
            MapObjectType.PICKUP_STATION.value: Coordinate2D(1, 1),
            MapObjectType.PILLAR.value: Coordinate2D(1, 1),
            MapObjectType.AGENT.value: Coordinate2D(1, 1),
        },
        object_numbers={
            MapObjectType.MAINTENANCE_AREA.value: 2,
            MapObjectType.STACK.value: 12,
            MapObjectType.PICKUP_STATION.value: 3,
            MapObjectType.PILLAR.value: 8,
            MapObjectType.AGENT.value: 12,
        },
    )
    map_generator = MapGenerator(Map(map_configuration))
    map_visualizer = MapVisualizer(map_generator.map)
    message_bus.send_message(MessageTopic.MAP, message=map_visualizer.map)

    map_visualizer.run(message_bus=message_bus)


def get_process() -> Process:
    return Process(
        name="environment_generator",
        subsribe_topics=(MessageTopic.AGENT_PATH,),
        publish_topics=(MessageTopic.MAP,),
        process_function=main,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )
