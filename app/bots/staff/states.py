"""FSM states for the staff bot."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Auth(StatesGroup):
    waiting_pin = State()
    waiting_branch = State()


class Work(StatesGroup):
    idle = State()
    finding_customer = State()
    customer_active = State()


class OpenPrepaid(StatesGroup):
    waiting_qty = State()
    waiting_amount = State()
    waiting_confirm = State()


class Refund(StatesGroup):
    waiting_tx = State()
    waiting_reason = State()
    waiting_confirm = State()
