from __future__ import annotations
import asyncio

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

@dataclass
class CallbackEvent:
    '''An event with a callback set.'''
    callback: Callable[..., Coroutine[Any, Any, Any]]
    event: Event

@dataclass
class Event:
    '''An event sent by a bot instance to the event manager.'''
    def __call__(self, callback: Callable[..., Coroutine[Any, Any, Any]]) -> CallbackEvent:
        return CallbackEvent(callback, self)

@dataclass
class CogRefreshEvent(Event):
    '''A cog refresh has been requested by one of the instances.'''
    cog: str | None
