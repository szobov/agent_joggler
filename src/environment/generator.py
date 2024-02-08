"""
Y
^
|
|----> X
"""

from typing import Optional
import arcade
import random
import dataclasses
import enum
import structlog
import itertools


logger = structlog.getLogger(__name__)


@enum.unique
class MapObjectType(enum.Enum):
    PICKUP_STATION = enum.auto()
    MAINTENANCE_AREA = enum.auto()
    PILLAR = enum.auto()
    AGENT = enum.auto()


@dataclasses.dataclass(frozen=True)
class Coordinate2D:
    x: int
    y: int


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


@dataclasses.dataclass(frozen=True, order=True)
class MapObject:
    coordinates: Coordinate2D
    object_type: MapObjectType
    object_id: int


@dataclasses.dataclass(frozen=True)
class MapConfiguration:
    width_units: int
    height_units: int

    object_sizes: dict[MapObjectType, Coordinate2D] = dataclasses.field(
        default_factory=dict
    )
    object_numbers: dict[MapObjectType, int] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Map:
    configuration: MapConfiguration
    objects: list[MapObject] = dataclasses.field(default_factory=list)
    seed: Optional[int] = None

    def __post_init__(self):
        if self.seed is not None:
            random.seed(self.seed)
        self._generate_objects()

    def _get_object_far_corner(self, object: MapObject):
        size = self.configuration.object_sizes[object.object_type]
        return object.coordinates.x + size.x, object.coordinates.y + size.y

    def _generate_objects(self):
        RANDOMLY_PLACED_OBJECTS = {
            MapObjectType.PILLAR,
        }

        for maintanance_area_id in range(
            self.configuration.object_numbers[MapObjectType.MAINTENANCE_AREA]
        ):
            self._generate_maintenance_area(maintanance_area_id)
        for object_type, num in filter(
            lambda keyval: keyval[0] in RANDOMLY_PLACED_OBJECTS,
            self.configuration.object_numbers.items(),
        ):
            for object_id in range(num):
                self._generate_object(
                    object_type,
                    object_id,
                    (0, self.configuration.width_units),
                    (0, self.configuration.height_units),
                    ignore_object_overlap=set(),
                )
        for agent_id in range(self.configuration.object_numbers[MapObjectType.AGENT]):
            self._generate_agent(agent_id)

        self._generate_pickup_stations()

        assert len(self.objects) == sum(
            self.configuration.object_numbers.values()
        ), f"{len(self.objects)} == {sum(self.configuration.object_numbers.values())}"

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
        while overlap:
            log.debug("Attempt to place an object on mape")
            coords = random_2d_coords(range_x, range_y)
            coords = Coordinate2D(
                max(0, min(coords.x, self.configuration.width_units)),
                max(0, min(coords.y, self.configuration.height_units)),
            )
            log = log.bind(coords=coords)
            possible_object = MapObject(coords, type, object_id)
            far_x, far_y = self._get_object_far_corner(possible_object)

            overlap = False
            for other_object in filter(
                lambda object: object not in ignore_object_overlap, self.objects
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
                self.objects.append(possible_object)
                return possible_object
            log = log.unbind("coords")
        assert False

    def _generate_agent(self, agent_id: int):
        maintenance_area = next(
            filter(
                lambda obj: obj.object_type == MapObjectType.MAINTENANCE_AREA,
                random.sample(self.objects, len(self.objects)),
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

        maintenance_area_size = self.configuration.object_sizes[
            MapObjectType.MAINTENANCE_AREA
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
        x_range = (0, self.configuration.width_units - object_size.x)
        y_range = (0, self.configuration.height_units - object_size.y)

        match border:
            case Border.BOTTOM:
                y_range = (0, 0)
            case Border.RIGHT:
                x_range = (
                    self.configuration.width_units - object_size.x,
                    self.configuration.width_units - object_size.x,
                )
            case Border.TOP:
                y_range = (
                    self.configuration.height_units - object_size.y,
                    self.configuration.height_units - object_size.y,
                )
            case Border.LEFT:
                x_range = (0, 0)
        return (x_range, y_range)

    def _generate_pickup_stations(self):
        num_pickup_stations = self.configuration.object_numbers[
            MapObjectType.PICKUP_STATION
        ]

        CLUSTER_SIZE = random.randint(2, 4)

        for pickup_stations in itertools.batched(
            range(num_pickup_stations), CLUSTER_SIZE
        ):
            maintenance_area = next(
                filter(
                    lambda obj: obj.object_type == MapObjectType.MAINTENANCE_AREA,
                    random.sample(self.objects, len(self.objects)),
                )
            )
            maintenance_area_far_corner = self._get_object_far_corner(maintenance_area)
            maintenance_area_border = Border.LEFT

            if maintenance_area.coordinates.x == 0:
                maintenance_area_border = Border.LEFT
            elif maintenance_area.coordinates.y == 0:
                maintenance_area_border = Border.BOTTOM
            elif maintenance_area_far_corner[0] == self.configuration.width_units:
                maintenance_area_border = Border.RIGHT
            else:
                maintenance_area_border = Border.TOP

            pickup_cluster_center_border = Border.RIGHT
            match maintenance_area_border:
                case Border.LEFT:
                    pickup_cluster_center_border = Border.RIGHT
                case Border.RIGHT:
                    pickup_cluster_center_border = Border.LEFT
                case Border.TOP:
                    pickup_cluster_center_border = Border.BOTTOM
                case Border.BOTTOM:
                    pickup_cluster_center_border = Border.TOP

            pickup_stations_center_range = self._get_along_the_border_coordinates_range(
                pickup_cluster_center_border,
                self.configuration.object_sizes[MapObjectType.PICKUP_STATION],
            )

            pickup_stations_ids = list(pickup_stations)
            pickup_station_center_id = pickup_stations_ids[
                len(pickup_stations_ids) // 2
            ]

            pickup_cluster_center_object = self._generate_object(
                MapObjectType.PICKUP_STATION,
                pickup_station_center_id,
                pickup_stations_center_range[0],
                pickup_stations_center_range[1],
                set(),
            )
            pickup_station_size = self.configuration.object_sizes[
                MapObjectType.PICKUP_STATION
            ]
            for side_stations_id in filter(
                lambda p_id: p_id != pickup_station_center_id, pickup_stations_ids
            ):
                x_offset = random.randint(1, CLUSTER_SIZE) * pickup_station_size.x
                y_offset = random.randint(1, CLUSTER_SIZE) * pickup_station_size.y
                self._generate_object(
                    MapObjectType.PICKUP_STATION,
                    side_stations_id,
                    (
                        pickup_cluster_center_object.coordinates.x - x_offset,
                        pickup_cluster_center_object.coordinates.x + x_offset,
                    ),
                    (
                        pickup_cluster_center_object.coordinates.y - y_offset,
                        pickup_cluster_center_object.coordinates.y + y_offset,
                    ),
                    set(),
                )


class WarehouseGanerator(arcade.Window):
    def __init__(self):
        super().__init__(800, 600, "Warehouse Generator")

        self.map_configuration = MapConfiguration(
            width_units=20,
            height_units=15,
            object_sizes={
                MapObjectType.MAINTENANCE_AREA: Coordinate2D(3, 3),
                MapObjectType.PICKUP_STATION: Coordinate2D(1, 1),
                MapObjectType.PILLAR: Coordinate2D(1, 1),
                MapObjectType.AGENT: Coordinate2D(1, 1),
            },
            object_numbers={
                MapObjectType.MAINTENANCE_AREA: 1,
                MapObjectType.PICKUP_STATION: 3,
                MapObjectType.PILLAR: 8,
                MapObjectType.AGENT: 4,
            },
        )
        self.map = Map(self.map_configuration)

        self.object_colors = {
            MapObjectType.MAINTENANCE_AREA: arcade.color.GREEN,
            MapObjectType.PICKUP_STATION: arcade.color.BLUE,
            MapObjectType.PILLAR: arcade.color.GRAY,
            MapObjectType.AGENT: arcade.color.RED,
        }

        self.unit_pixel_size = min(
            self.width / self.map_configuration.width_units,
            self.height / self.map_configuration.height_units,
        )

    def on_draw(self):
        arcade.start_render()
        self.draw_grid()
        for object in self.map.objects:
            self.draw_object(
                object.coordinates,
                self.map_configuration.object_sizes[object.object_type],
                self.object_colors[object.object_type],
                object.object_id,
            )

    def update(self, delta_time):
        del delta_time
        pass

    def draw_grid(self):
        for index, x in enumerate(range(0, self.width, int(self.unit_pixel_size))):
            arcade.draw_line(x, 0, x, self.height, arcade.color.WHITE, 2)
            arcade.draw_text(
                index,
                x + self.unit_pixel_size // 2,
                self.unit_pixel_size // 2,
                arcade.color.WHITE,
                font_size=12,
                width=int(self.unit_pixel_size // 2),
                anchor_x="right",
                anchor_y="top",
            )
        for index, y in enumerate(range(0, self.height, int(self.unit_pixel_size))):
            arcade.draw_line(0, y, self.width, y, arcade.color.WHITE, 2)
            arcade.draw_text(
                index,
                self.unit_pixel_size // 2,
                y + self.unit_pixel_size // 2,
                arcade.color.WHITE,
                font_size=12,
                width=int(self.unit_pixel_size // 2),
                anchor_x="right",
                anchor_y="top",
            )

    def draw_object(
        self,
        object: Coordinate2D,
        size: Coordinate2D,
        color: tuple[int, int, int],
        object_id: int,
    ):
        x = object.x
        y = object.y
        x_pixel = x * self.unit_pixel_size
        y_pixel = y * self.unit_pixel_size
        size_x = size.x * self.unit_pixel_size
        size_y = size.y * self.unit_pixel_size

        center_x = x_pixel + size_x / 2
        center_y = y_pixel + size_y / 2

        text = object_id

        arcade.draw_rectangle_filled(center_x, center_y, size_x, size_y, color)

        arcade.draw_text(
            text,
            center_x,
            center_y,
            arcade.color.WHITE,
            font_size=12,
            width=int(size_x),
            align="center",
            anchor_x="center",
            anchor_y="center",
        )


def main():
    WarehouseGanerator()
    arcade.run()


if __name__ == "__main__":
    main()
