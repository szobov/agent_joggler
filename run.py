from collections.abc import Sequence

from rich.traceback import install

from src.path_planning import path_planner
from src.environment import generator
from src.logger import setup_logging
from src.orders import order_planner
from src.runner import (
    Process,
    get_process_executor,
    setup_message_bus,
    start_processes,
    supervise_processes,
)

install(show_locals=True)

setup_logging(name="root")


def main():
    processes: Sequence[Process] = (
        generator.get_process(),
        path_planner.get_process(),
        order_planner.get_process(),
    )
    with get_process_executor() as executor:
        with setup_message_bus(executor) as message_bus:
            process_futures = start_processes(executor, processes, message_bus)
            supervise_processes(
                executor=executor,
                process_futures=process_futures,
                message_bus=message_bus,
            )


if __name__ == "__main__":
    main()
