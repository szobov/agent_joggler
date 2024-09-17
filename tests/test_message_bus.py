import os
from collections import deque
from unittest.mock import MagicMock, Mock, patch

import pytest
import structlog

from src.internal_types import AgentPath, Orders
from src.message_transport import (
    MessageBus,
    MessageBusProtocol,
    MessageTopic,
    dump_message_to_filesystem,
)
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
        process_finish_policy=ProcessFinishPolicy.NOTHING,
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


IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"


@pytest.mark.skipif(
    IN_GITHUB_ACTIONS, reason="For some reasons this test fails in GitHub Actions"
)
def test_message_bus():
    processes = (
        get_second_process(),
        get_first_process(),
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
            first_result = results[processes[1]]
            assert first_result == "message sent"

            second_result = results[processes[0]]
            assert second_result == "message received"


def function_la_bomba(message_bus: MessageBusProtocol) -> None:
    del message_bus
    raise RuntimeError("La boom")


@pytest.mark.skip
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


def test_message_bus_initialization():
    with (
        patch("src.message_transport._get_zmq_context") as mock_get_zmq_context,
        patch(
            "src.message_transport._get_zmq_subscribe_socket"
        ) as mock_get_zmq_subscribe_socket,
        patch(
            "src.message_transport._get_zmq_publish_socket"
        ) as mock_get_zmq_publish_socket,
    ):
        mock_context = MagicMock()
        mock_subscribe_socket = MagicMock()
        mock_publish_socket = MagicMock()

        mock_get_zmq_context.return_value = mock_context
        mock_get_zmq_subscribe_socket.return_value = mock_subscribe_socket
        mock_get_zmq_publish_socket.return_value = mock_publish_socket

        message_bus = MessageBus()

        assert message_bus._context == mock_context
        assert message_bus._subscribe_socket == mock_subscribe_socket
        assert message_bus._publish_socket == mock_publish_socket


# Test MessageBus.subscribe
def test_message_bus_subscribe():
    with (
        patch("src.message_transport._get_zmq_context"),
        patch("src.message_transport._get_zmq_subscribe_socket"),
        patch("src.message_transport._get_zmq_publish_socket"),
    ):
        message_bus = MessageBus()
        message_bus.subscribe(MessageTopic.ORDERS)
        assert isinstance(message_bus._subscribe_socket.subscribe, Mock)
        message_bus._subscribe_socket.subscribe.assert_called_once_with(
            MessageTopic.ORDERS.value.encode()
        )
        assert isinstance(
            message_bus._topic_to_received_message[MessageTopic.ORDERS], deque
        )


# Test MessageBus.send_message
def test_message_bus_send_message():
    with (
        patch("src.message_transport._get_zmq_context"),
        patch("src.message_transport._get_zmq_subscribe_socket"),
        patch("src.message_transport._get_zmq_publish_socket"),
    ):
        message_bus = MessageBus()
        message = MagicMock(spec=Orders)
        message.serialize.return_value = b"serialized_message"

        message_bus.send_message(MessageTopic.ORDERS, message)

        assert isinstance(message_bus._publish_socket.send_multipart, Mock)
        message_bus._publish_socket.send_multipart.assert_called_once_with(
            [MessageTopic.ORDERS.value.encode(), b"serialized_message"]
        )


# Test MessageBus.get_message when message is already in queue
def test_message_bus_get_message_from_queue():
    with (
        patch("src.message_transport._get_zmq_context"),
        patch("src.message_transport._get_zmq_subscribe_socket"),
        patch("src.message_transport._get_zmq_publish_socket"),
    ):
        message_bus = MessageBus()
        message = MagicMock(spec=Orders)
        message_bus._topic_to_received_message[MessageTopic.ORDERS] = deque([message])

        received_message = message_bus.get_message(MessageTopic.ORDERS, wait=False)

        assert received_message == message
        assert len(message_bus._topic_to_received_message[MessageTopic.ORDERS]) == 0


def test_message_bus_get_message_not_in_queue_no_wait():
    with (
        patch("src.message_transport._get_zmq_context"),
        patch("src.message_transport._get_zmq_subscribe_socket"),
        patch("src.message_transport._get_zmq_publish_socket"),
        patch(
            "src.message_transport.MessageBus._receive_raw_messages"
        ) as mock_receive_raw_messages,
    ):
        message_bus = MessageBus()
        message_bus.subscribe(MessageTopic.ORDERS)
        mock_receive_raw_messages.return_value = None

        received_message = message_bus.get_message(MessageTopic.ORDERS, wait=False)

        assert received_message is None
        mock_receive_raw_messages.assert_called_once_with(
            expected_topic=MessageTopic.ORDERS, wait=False
        )


# Test MessageBus.get_message when wait is True and message arrives
def test_message_bus_get_message_with_wait():
    with (
        patch("src.message_transport._get_zmq_context"),
        patch("src.message_transport._get_zmq_subscribe_socket"),
        patch("src.message_transport._get_zmq_publish_socket"),
        patch(
            "src.message_transport.MessageBus._receive_raw_messages"
        ) as mock_receive_raw_messages,
    ):
        message_bus = MessageBus()
        message = MagicMock(spec=Orders)
        message_bus._topic_to_received_message[MessageTopic.ORDERS] = deque()

        mock_receive_raw_messages.side_effect = (
            lambda *_, **kwargs: message_bus._topic_to_received_message[
                MessageTopic.ORDERS
            ].append(message)
        )

        received_message = message_bus.get_message(MessageTopic.ORDERS, wait=True)

        assert received_message == message
        assert len(message_bus._topic_to_received_message[MessageTopic.ORDERS]) == 0


@patch("src.message_transport.logger")
def test_dump_message_to_filesystem(mock_logger):
    with (
        patch("tempfile.NamedTemporaryFile") as mock_tempfile,
        patch("src.message_transport.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value.strftime.return_value = "mocked_time"
        temp_file_mock = MagicMock()
        mock_tempfile.return_value.__enter__.return_value = temp_file_mock

        message = MagicMock(spec=Orders)
        message.serialize.return_value = b"serialized_message"

        dump_message_to_filesystem(message)

        temp_file_mock.write.assert_called_once_with(b"serialized_message")
        mock_logger.info.assert_called_with(
            "dumped a message", path=temp_file_mock.name, message=message
        )
