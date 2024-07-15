import enum
import time
from collections.abc import Sequence
from contextlib import contextmanager
from concurrent.futures import (
    ALL_COMPLETED,
    FIRST_EXCEPTION,
    Future,
    ProcessPoolExecutor,
    wait,
)
from dataclasses import dataclass
from typing import Any, NamedTuple, cast, Protocol, Iterator
import multiprocessing

import structlog

from src.internal_types import GlobalStart, GlobalStop, ProcessStarted
from src.logger import setup_logging
from src.message_transport import (
    MessageBus,
    MessageBusProtocol,
    MessageTopic,
    zmq_proxy_start,
    zmq_proxy_stopper,
)

logger = structlog.getLogger(__name__)

PROCESS_START_TIMEOUT_SEC = 5.0
RUNNER_FUTURE_WAIT_TIMEOUT_SEC = 5.0


def get_deadline(timeout: float) -> float:
    return time.monotonic() + timeout


def reached_deadline(deadline: float) -> bool:
    return time.monotonic() > deadline


class ProcessFunctionProtocol(Protocol):
    def __call__(self, message_bus: MessageBusProtocol) -> Any: ...


@enum.unique
class ProcessFinishPolicy(enum.Enum):
    RESTART = enum.auto()
    RESTART_ALL = enum.auto()
    STOP_ALL = enum.auto()
    NOTHING = enum.auto()


@dataclass(frozen=True)
class Process:
    name: str
    subsribe_topics: Sequence[MessageTopic]
    publish_topics: Sequence[MessageTopic]
    process_function: ProcessFunctionProtocol
    process_finish_policy: ProcessFinishPolicy


class ProcessFuture(NamedTuple):
    process: Process
    future: Future


def _runner(process: Process):
    setup_logging(process.name)
    message_bus = MessageBus()
    log = logger.bind(process=process)
    log.info("Starting process...")
    message_bus.subscribe(MessageTopic.GLOBAL_STOP)
    message_bus.subscribe(MessageTopic.GLOBAL_START)
    message_bus.prepare_publisher(MessageTopic.PROCESS_STARTED)

    for topic in process.subsribe_topics:
        message_bus.subscribe(topic)

    for topic in process.publish_topics:
        message_bus.prepare_publisher(topic)
    log.info("Topics are advertised")
    deadline = get_deadline(PROCESS_START_TIMEOUT_SEC)
    get_start_message = False
    while not reached_deadline(deadline) and not get_start_message:
        global_start = message_bus.get_message(MessageTopic.GLOBAL_START, wait=False)
        if global_start is not None:
            global_start = cast(GlobalStart, global_start)
            if global_start.process_name == process.name:
                get_start_message = True
                break
        message_bus.send_message(
            MessageTopic.PROCESS_STARTED, ProcessStarted(process.name)
        )
    if not get_start_message:
        log.error("Didn't get GlobalStart message")
        return
    else:
        log.info("starting process function")
        result = process.process_function(cast(MessageBusProtocol, message_bus))
        log.info("process function completed", result=result)
        return result


def set_exception_logger_future(future: Future):
    def exception_handler(future: Future):
        exception = future.exception()
        if exception is None:
            return
        logger.exception(exception)

    future.add_done_callback(exception_handler)


def start_process(executor: ProcessPoolExecutor, process: Process) -> Future:
    future = executor.submit(_runner, process)
    return future


def validate_processes(processes: Sequence[Process]):
    assert len(set(p.name for p in processes)) == len(
        processes
    ), f"Process names must be unique: {processes}"


@contextmanager
def setup_message_bus(executor: ProcessPoolExecutor) -> Iterator[MessageBus]:
    zmq_proxy_future = executor.submit(zmq_proxy_start)
    set_exception_logger_future(zmq_proxy_future)
    message_bus = MessageBus()
    message_bus.subscribe(MessageTopic.PROCESS_STARTED)
    message_bus.prepare_publisher(MessageTopic.GLOBAL_START)
    message_bus.prepare_publisher(MessageTopic.GLOBAL_STOP)
    try:
        yield message_bus
    finally:
        zmq_proxy_stopper()
        message_bus.tear_down()


@contextmanager
def get_process_executor() -> Iterator[ProcessPoolExecutor]:
    with ProcessPoolExecutor(
        mp_context=multiprocessing.get_context("fork")
    ) as executor:
        yield executor


def start_processes(
    executor: ProcessPoolExecutor, processes: Sequence[Process], message_bus: MessageBus
) -> Sequence[ProcessFuture]:
    validate_processes(processes)

    futures = []
    for process in processes:
        future = start_process(executor, process)
        set_exception_logger_future(future)
        futures.append((process, future))

    started_processes = set()
    deadline = get_deadline(PROCESS_START_TIMEOUT_SEC)
    while not reached_deadline(deadline) and len(started_processes) != len(processes):
        process_started = message_bus.get_message(
            topic=MessageTopic.PROCESS_STARTED, wait=False
        )
        if process_started is None:
            continue
        assert isinstance(process_started, ProcessStarted)
        if process_started.process_name not in started_processes:
            started_processes.add(process_started.process_name)
            logger.info(
                "Sending global start message", to_process=process_started.process_name
            )
            message_bus.send_message(
                MessageTopic.GLOBAL_START, GlobalStart(process_started.process_name)
            )
    if len(started_processes) != len(processes):
        logger.error(
            "Processes were not started withing the timeout",
            expected_processes=process,
            timeout=PROCESS_START_TIMEOUT_SEC,
            started_processes=started_processes,
            futures=futures,
        )
        message_bus.send_message(MessageTopic.GLOBAL_STOP, GlobalStop())
        for _, future in futures:
            future.cancel()
    else:
        logger.info("All processes started", processes=processes)
    return futures


def _supervise_stop_all_handler(
    message_bus: MessageBus,
    future_to_stop: Sequence[Future],
    future_process_map: dict[Future, Process],
    results: dict[Process, Any],
):
    message_bus.send_message(MessageTopic.GLOBAL_STOP, GlobalStop())
    (done, _) = wait(future_to_stop, return_when=ALL_COMPLETED)
    for future in done:
        try:
            results[future_process_map[future]] = future.result()
        except Exception:
            logger.exception("Exception on stopping all processes")


def supervise_processes(
    executor: ProcessPoolExecutor,
    process_futures: Sequence[ProcessFuture],
    message_bus: MessageBus,
) -> dict[Process, Any]:
    map: dict[Future, Process] = {f: p for p, f in process_futures}
    results: dict[Process, Any] = {}
    stopped = False

    while not stopped and map:
        try:
            (done, not_done) = wait(
                map.keys(),
                timeout=RUNNER_FUTURE_WAIT_TIMEOUT_SEC,
                return_when=FIRST_EXCEPTION,
            )
            for done_future in done:
                process = map[done_future]
                try:
                    result = done_future.result()
                except Exception as ex:
                    logger.exception("Process finished with exception", process=process)
                    result = ex
                match process.process_finish_policy:
                    case ProcessFinishPolicy.RESTART:
                        restarted_process = start_processes(
                            executor=executor,
                            processes=[process],
                            message_bus=message_bus,
                        )[0]
                        map[restarted_process.future] = restarted_process.process
                    case ProcessFinishPolicy.RESTART_ALL:
                        message_bus.send_message(MessageTopic.GLOBAL_STOP, GlobalStop())
                        wait(not_done, return_when=ALL_COMPLETED)
                        restarted_process_futures = start_processes(
                            executor=executor,
                            processes=tuple(map.values()),
                            message_bus=message_bus,
                        )
                        map = {f: p for p, f in restarted_process_futures}
                    case ProcessFinishPolicy.STOP_ALL:
                        stopped = True
                        results[process] = result
                        _supervise_stop_all_handler(
                            message_bus, list(not_done), map, results
                        )
                    case ProcessFinishPolicy.NOTHING:
                        map.pop(done_future)
                        results[process] = result
        except KeyboardInterrupt:
            stopped = True
            _supervise_stop_all_handler(message_bus, list(map.keys()), map, results)

    return results
