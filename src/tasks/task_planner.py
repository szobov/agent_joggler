from src.environment.generator import Map
from src.internal_types import Environment
from dataclasses import dataclass


# TODO:
#
# In generator(?):
# I should create an object type "stack" (id, size). "stack" should contain "pallets" (id).
# An "order": Move "pallet" id(N) to "pickup station" id (M).
# The "TaskPlanner" finds first "pallet" in the "stack".
# Then it calculates the "depth" of the "pallet" and sends "agents" to "move" other "pallets" so "depth" of "pallet" id(N) is 0.
# Then the an "agent" id(L) delivers the "pallet" id(N) to the "pickup station" id(M).
# Meantime the "TaskPlanner" repeat the same for other orders.


@dataclass
class TaskPlanner:
    env: Environment
    map: Map

    def assign_tasks(self):
        pass
