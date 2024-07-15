import structlog

from src.internal_types import AgentPath
from src.message_transport import MessageBusProtocol, MessageTopic, zmq_proxy_stopper
from src.runner import (
    Process,
    ProcessFinishPolicy,
    get_process_executor,
    setup_message_bus,
    start_processes,
    supervise_processes,
)

logger = structlog.getLogger(__name__)


def send_message(message_bus: MessageBusProtocol) -> str:
    topic = MessageTopic.AGENT_PATH
    message = AgentPath(agent_id=42, path=[])
    message_bus.send_message(topic, message)
    return "message sent"


def get_first_process() -> Process:
    return Process(
        name="send_message",
        subsribe_topics=(),
        publish_topics=(MessageTopic.AGENT_PATH,),
        process_function=send_message,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )


def get_message(message_bus: MessageBusProtocol) -> str:
    topic = MessageTopic.AGENT_PATH
    message = message_bus.get_message(topic, wait=True)
    assert message is not None
    assert isinstance(message, AgentPath)
    assert message.agent_id == 42
    assert message.path == []
    return "message received"


def get_second_process() -> Process:
    return Process(
        name="get_message",
        subsribe_topics=(MessageTopic.AGENT_PATH,),
        publish_topics=(),
        process_function=get_message,
        process_finish_policy=ProcessFinishPolicy.STOP_ALL,
    )


def test_message_bus():
    processes = (
        get_first_process(),
        get_second_process(),
    )

    with get_process_executor() as executor:
        with setup_message_bus(executor) as message_bus:
            process_futures = start_processes(executor, processes, message_bus)
            results = supervise_processes(
                executor=executor,
                process_futures=process_futures,
                message_bus=message_bus,
            )
            assert len(results) == 2
            first_result = results[processes[0]]
            assert first_result == "message sent"

            second_result = results[processes[1]]
            assert second_result == "message received"


def function_la_bomba(message_bus: MessageBusProtocol) -> None:
    del message_bus
    raise RuntimeError("La boom")


def test_runner_stop_all():
    processes = (
        get_first_process(),
        Process(
            name="function_la_bomba",
            subsribe_topics=(),
            publish_topics=(),
            process_function=function_la_bomba,
            process_finish_policy=ProcessFinishPolicy.STOP_ALL,
        ),
    )

    with get_process_executor() as executor:
        with setup_message_bus(executor) as message_bus:
            process_futures = start_processes(executor, processes, message_bus)
            results = supervise_processes(
                executor=executor,
                process_futures=process_futures,
                message_bus=message_bus,
            )
            assert len(results) == 2
            first_result = results[processes[0]]
            assert first_result == "message sent"

            second_result = results[processes[1]]
            assert isinstance(second_result, RuntimeError)
