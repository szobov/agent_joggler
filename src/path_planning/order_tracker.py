import dataclasses
import typing as _t
from collections import defaultdict, deque

import structlog
from structlog.typing import WrappedLogger

from ..internal_types import Agent, Coordinate2D, Order, Orders, OrderType, TimeT

logger = structlog.getLogger(__name__)


@dataclasses.dataclass
class OrderTracker:
    not_assigned_orders: deque[Order] = dataclasses.field(default_factory=deque)
    assigned_order: dict[Agent, Order] = dataclasses.field(default_factory=dict)
    finished_orders: dict[Agent, deque[tuple[TimeT, Order]]] = dataclasses.field(
        default_factory=lambda: defaultdict(deque)
    )
    logger: WrappedLogger = dataclasses.field(
        default_factory=lambda: logger.bind(isinstance="order_tracker")
    )

    def add_orders(self, orders: Orders):
        self.logger.info("add orders", orders=orders)
        for order in orders.orders:
            self.not_assigned_orders.append(order)

    def iterate_finished_orders(
        self, agent: Agent, time_step: TimeT
    ) -> _t.Iterator[Order]:
        for time_stamp, _ in self.finished_orders[agent].copy():
            if time_stamp < time_step:
                yield self.finished_orders[agent].popleft()[1]
            else:
                break

    def assign_order(self, agent: Agent) -> Coordinate2D:
        log = self.logger.bind(agent=agent)
        log.info("assign order")
        assert agent not in self.assigned_order
        if len(self.not_assigned_orders) == 0:
            # If we have no assigned tasks, return robot to the parking
            # position
            log.info("No orders available, send home")
            return agent.position
        if (
            self.finished_orders[agent]
            and self.finished_orders[agent][0] != OrderType.DELIVERY
        ):
            _, prev_order = self.finished_orders[agent][0]
            log.info("searching for next delivery order", prev_order=prev_order)
            accumulator: list[Order] = []
            next_order = None
            while self.not_assigned_orders:
                next_order = self.not_assigned_orders.popleft()
                if (
                    next_order.order_type == OrderType.DELIVERY
                    and next_order.pallet_id != prev_order.pallet_id
                ):
                    accumulator.append(next_order)
                else:
                    log.info(
                        "Found next delivery order",
                        prev_order=prev_order,
                        next_order=next_order,
                    )
                    self.not_assigned_orders.extendleft(accumulator)
                    break
        else:
            next_order = self.not_assigned_orders.popleft()
            log.info("next order", next_order=next_order)
        assert next_order is not None
        self.assigned_order[agent] = next_order
        return next_order.goal

    def validate_finished_tasks(self, cleaned_up_time_step: TimeT, agent: Agent):
        for time_stamp, task in reversed(self.finished_orders[agent].copy()):
            if time_stamp < cleaned_up_time_step:
                return
            _, task = self.finished_orders[agent].pop()
            self.not_assigned_orders.appendleft(task)

    def agent_finished_task(self, agent: Agent, time_step: TimeT):
        self.logger.info("finished order", agent=agent, time_step=time_step)
        task = self.assigned_order.pop(agent)
        self.finished_orders[agent].append((time_step, task))
