import enum
import typing as _t
import tempfile
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field

import zmq
from dataclasses_avroschema.schema_generator import AvroModel
import structlog

from .internal_types import (
    GlobalStart,
    Map,
    OrderFinished,
    Orders,
    AgentPath,
    GlobalStop,
    ProcessStarted,
)

logger = structlog.get_logger(__name__)

SOCKET_WAIT_TIMEOUT_MS = 5 * 100


class MessageBusGlobalStop(Exception):
    pass


@enum.unique
class MessageTopic(enum.Enum):
    MAP = "map"
    ORDERS = "orders"
    AGENT_PATH = "agent_path"
    GLOBAL_STOP = "global_stop"
    PROCESS_STARTED = "process_started"
    GLOBAL_START = "global_start"
    ORDER_FINISHED = "order_finished"


MessageTopicToMessageClass = {
    MessageTopic.ORDERS: Orders,
    MessageTopic.GLOBAL_STOP: GlobalStop,
    MessageTopic.AGENT_PATH: AgentPath,
    MessageTopic.MAP: Map,
    MessageTopic.ORDER_FINISHED: OrderFinished,
    MessageTopic.PROCESS_STARTED: ProcessStarted,
    MessageTopic.GLOBAL_START: GlobalStart,
}

PUB_SOCKET = "ipc:///tmp/agent_joggler.pub"
SUB_SOCKET = "ipc:///tmp/agent_joggler.sub"
PROXY_CONTROL_SOCKET = "ipc:///tmp/agent_joggler.proxy_control"


def _get_zmq_context() -> zmq.Context:
    return zmq.Context()


def _get_zmq_socket(context: zmq.Context, socket_type: int) -> zmq.Socket:
    return context.socket(socket_type)


def _get_zmq_subscribe_socket(context: zmq.Context) -> zmq.Socket:
    socket = _get_zmq_socket(context, zmq.SUB)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVTIMEO, SOCKET_WAIT_TIMEOUT_MS)
    socket.connect(PUB_SOCKET)
    return socket


def _get_zmq_publish_socket(context: zmq.Context) -> zmq.Socket:
    socket = _get_zmq_socket(context, zmq.PUB)
    socket.connect(SUB_SOCKET)
    return socket


def _get_zmq_xsub_socket(context: zmq.Context) -> zmq.Socket:
    socket = _get_zmq_socket(context, zmq.XSUB)
    socket.bind(SUB_SOCKET)
    return socket


def _get_zmq_xpub_socket(context: zmq.Context) -> zmq.Socket:
    socket = _get_zmq_socket(context, zmq.XPUB)
    socket.bind(PUB_SOCKET)
    return socket


def _get_zmq_proxy_control_rep_socket(context: zmq.Context) -> zmq.Socket:
    socket = _get_zmq_socket(context, zmq.REP)
    socket.bind(PROXY_CONTROL_SOCKET)
    return socket


def _get_zmq_proxy_control_req_socket(context: zmq.Context) -> zmq.Socket:
    socket = _get_zmq_socket(context, zmq.REQ)
    socket.connect(PROXY_CONTROL_SOCKET)
    return socket


def zmq_proxy_start():
    logger.info("starting zmq proxy")
    context = _get_zmq_context()
    xpub = _get_zmq_xpub_socket(context)
    xsub = _get_zmq_xsub_socket(context)
    control_rep = _get_zmq_proxy_control_rep_socket(context)
    zmq.proxy_steerable(xpub, xsub, None, control_rep)


def zmq_proxy_stopper():
    logger.info("stopping zmq proxy")
    context = _get_zmq_context()
    socket = _get_zmq_proxy_control_req_socket(context)
    socket.send("TERMINATE".encode())


class MessageBusProtocol(_t.Protocol):

    @_t.overload
    def send_message(
        self, topic: _t.Literal[MessageTopic.MAP], message: Map
    ) -> None: ...

    @_t.overload
    def send_message(
        self, topic: _t.Literal[MessageTopic.ORDERS], message: Orders
    ) -> None: ...

    @_t.overload
    def send_message(
        self,
        topic: _t.Literal[MessageTopic.ORDER_FINISHED],
        message: OrderFinished,
    ) -> None: ...

    @_t.overload
    def send_message(
        self, topic: _t.Literal[MessageTopic.AGENT_PATH], message: AgentPath
    ) -> None: ...

    def send_message(self, topic: MessageTopic, message: AvroModel) -> None: ...

    @_t.overload
    def get_message(
        self, topic: _t.Literal[MessageTopic.MAP], wait: bool
    ) -> _t.Optional[Map]: ...

    @_t.overload
    def get_message(
        self, topic: _t.Literal[MessageTopic.AGENT_PATH], wait: bool
    ) -> _t.Optional[AgentPath]: ...

    @_t.overload
    def get_message(
        self, topic: _t.Literal[MessageTopic.ORDERS], wait: bool
    ) -> _t.Optional[Orders]: ...

    @_t.overload
    def get_message(
        self, topic: _t.Literal[MessageTopic.ORDER_FINISHED], wait: bool
    ) -> _t.Optional[OrderFinished]: ...

    @_t.overload
    def get_message(
        self, topic: _t.Literal[MessageTopic.GLOBAL_STOP], wait: bool
    ) -> _t.Optional[GlobalStop]: ...

    def get_message(self, topic: MessageTopic, wait: bool) -> AvroModel | None: ...


def dump_message_to_filesystem(message: AvroModel):
    current_time = datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p")
    with tempfile.NamedTemporaryFile(
        prefix=f"message_{str(type(message).__name__).lower()}_{current_time}",
        delete=False,
        mode="wb",
    ) as temp_file:
        temp_file.write(message.serialize(serialization_type="avro-json"))
        logger.info("dumped a message", path=temp_file.name, message=message)


@dataclass
class MessageBus:

    _publish_socket: zmq.Socket = field(init=False)
    _subscribe_socket: zmq.Socket = field(init=False)
    _context: zmq.Context = field(init=False)

    _topic_to_message_class: dict[MessageTopic, _t.Type[AvroModel]] = field(
        init=False, default_factory=dict
    )
    _topic_to_received_message: dict[MessageTopic, deque[AvroModel]] = field(
        init=False, default_factory=dict
    )
    _MAX_MESSAGE_BUFFER: int = field(init=False, default=100)

    def __post_init__(self):
        self._context = _get_zmq_context()
        self._subscribe_socket = _get_zmq_subscribe_socket(context=self._context)
        self._publish_socket = _get_zmq_publish_socket(context=self._context)

    def tear_down(self):
        self._context.destroy()

    def subscribe(self, topic: MessageTopic):
        self._subscribe_socket.subscribe(topic.value.encode())
        self._topic_to_received_message[topic] = deque(maxlen=self._MAX_MESSAGE_BUFFER)

    def prepare_publisher(self, topic: MessageTopic):
        del topic

    def send_message(self, topic: MessageTopic, message: AvroModel) -> None:
        assert isinstance(message, MessageTopicToMessageClass[topic])
        topic_encoded = topic.value.encode()
        self._publish_socket.send_multipart([topic_encoded, message.serialize()])

    def get_message(self, topic: MessageTopic, wait: bool) -> _t.Optional[AvroModel]:
        if self._topic_to_received_message[topic]:
            message = self._topic_to_received_message[topic].popleft()
            return message
        self._receive_raw_messages(expected_topic=topic, wait=wait)
        if self._topic_to_received_message[topic]:
            message = self._topic_to_received_message[topic].popleft()
            return message
        if not wait:
            return None

        while wait and not self._topic_to_received_message.get(topic):
            self._receive_raw_messages(expected_topic=topic, wait=wait)

        message = self._topic_to_received_message[topic].popleft()
        return message

    def _receive_raw_messages(self, expected_topic: MessageTopic, wait: bool) -> None:
        BATCH_SIZE = 1 if wait else 10
        for _ in range(BATCH_SIZE):
            try:
                flag = 0
                if not wait:
                    flag = zmq.DONTWAIT
                raw_topic, raw_message = self._subscribe_socket.recv_multipart(
                    flags=flag
                )
                logger.debug(
                    "received message", topic=raw_topic, raw_message=raw_message
                )
            except zmq.Again:
                if wait:
                    continue
                break
            except zmq.ZMQError:
                break

            topic = MessageTopic(raw_topic.decode())
            message_class = MessageTopicToMessageClass[topic]
            message = message_class.deserialize(raw_message)
            self._topic_to_received_message[topic].append(message)
            if topic == expected_topic:
                return
            if wait and topic is MessageTopic.GLOBAL_STOP:
                raise MessageBusGlobalStop("Received Global Stop message")
