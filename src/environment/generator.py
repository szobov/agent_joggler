import arcade
import random
import dataclasses
import enum


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


def random_2d_coords(width: int, height: int) -> Coordinate2D:
    x = random.randint(0, width - 1)
    y = random.randint(0, height - 1)
    return Coordinate2D(x, y)


@dataclasses.dataclass(frozen=True)
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

    def __post_init__(self):
        self._generate_objects()

    def _get_object_far_corner(self, object: MapObject):
        size = self.configuration.object_sizes[object.object_type]
        return object.coordinates.x + size.x, object.coordinates.y + size.y

    def _generate_objects(self):
        for object_type, num in self.configuration.object_numbers.items():
            for object_id in range(num):
                self._generate_object(object_type, object_id)
        assert len(self.objects) == sum(
            self.configuration.object_numbers.values()
        ), f"{len(self.objects)} == {sum(self.configuration.object_numbers.values())}"

    def _generate_object(self, type: MapObjectType, object_id: int):
        overlap = True
        while overlap:
            coords = random_2d_coords(
                self.configuration.width_units, self.configuration.height_units
            )
            possible_object = MapObject(coords, type, object_id)
            far_x, far_y = self._get_object_far_corner(possible_object)

            overlap = False
            for other_object in self.objects:
                other_object_far_x, other_object_far_y = self._get_object_far_corner(
                    other_object
                )
                overlap_x = (
                    other_object.coordinates.x
                    <= possible_object.coordinates.x
                    <= other_object_far_x
                ) or (
                    possible_object.coordinates.x <= other_object.coordinates.x <= far_x
                )
                overlap_y = (
                    other_object.coordinates.y
                    <= possible_object.coordinates.y
                    <= other_object_far_y
                    or possible_object.coordinates.y
                    <= other_object.coordinates.y
                    <= far_y
                )
                overlap = overlap_x and overlap_y
                if overlap:
                    break
            if not overlap:
                self.objects.append(possible_object)


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
                MapObjectType.PICKUP_STATION: 2,
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
        for x in range(0, self.width, int(self.unit_pixel_size)):
            arcade.draw_line(x, 0, x, self.height, arcade.color.WHITE, 2)
        for y in range(0, self.height, int(self.unit_pixel_size)):
            arcade.draw_line(0, y, self.width, y, arcade.color.WHITE, 2)

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
    window = WarehouseGanerator()
    arcade.run()


if __name__ == "__main__":
    main()
