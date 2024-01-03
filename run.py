import logging

import structlog
from rich.logging import RichHandler
from rich.traceback import install

from src.environment_builder import build_cross_env
from src.planner import windowed_hierarhical_cooperative_a_start
from src.visualizer import EnvironmentVisualizer

install(show_locals=True)


def setup_logging() -> None:
    logging.basicConfig(
        format="[%(asctime)s] %(name)s %(levelname)s in "
        "%(filename)s:%(lineno)d : %(message)s",
        handlers=[RichHandler()],
    )
    logging.getLogger().setLevel(logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


def main():
    env = build_cross_env()
    paths = windowed_hierarhical_cooperative_a_start(env)
    visualizer = EnvironmentVisualizer(800, 800, env, paths)
    visualizer.run()


if __name__ == "__main__":
    setup_logging()
    main()
