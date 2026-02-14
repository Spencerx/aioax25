#!/usr/bin/env python3

"""
AX.25 Interface handler
"""

import logging
import asyncio
import random
from functools import partial
import time

from .router import Router
from ._loop import EventLoopConsumer
from ._future import FutureWrapperMixin


def _on_tx_future(interface, frame, callback, future):
    """
    Handle a future being resolved for a legacy callback.
    """
    if future.exception() is not None:
        interface._loop.call_soon(
            partial(
                callback,
                interface=interface,
                frame=frame,
                exception=future.exception(),
            )
        )
    else:
        interface._loop.call_soon(
            partial(callback, interface=interface, frame=frame)
        )


def _future_ready(f):
    """
    Return true if the future is ready to take a result.
    """
    return (f is not None) and (not f.done())


class AX25Interface(Router, FutureWrapperMixin, EventLoopConsumer):
    """
    The AX25Interface class represents a logical AX.25 interface.
    The interface handles basic queueing and routing of message traffic.

    Outgoing messages are queued and sent when there is a break of greater
    than the cts_delay (10ms) + a randomisation factor (cts_rand).
    Messages may be cancelled prior to transmission.
    """

    def __init__(
        self,
        kissport,
        cts_delay=0.01,
        cts_rand=0.01,
        return_future=False,
        log=None,
        loop=None,
    ):
        # Initialise the superclass
        super(AX25Interface, self).__init__()

        if log is None:
            log = logging.getLogger(self.__class__.__module__)

        self._log = log
        self._loop = loop
        self._port = kissport
        self._return_future = return_future

        # Message queue
        self._tx_queue = []
        self._tx_pending = None

        # Clear-to-send delay and randomisation factor
        self._cts_delay = cts_delay
        self._cts_rand = cts_rand

        # Clear-to-send expiry
        self._cts_expiry = (
            self._loop.time() + cts_delay + (random.random() * cts_rand)
        )

        # Bind to the KISS port to receive raw messages.
        kissport.received.connect(self._on_receive)

    def transmit(self, frame, callback=None, future=None):
        """
        Enqueue a message for transmission.  Optionally give a call-back
        function or future to receive notification of transmission.
        """
        if callback is not None:
            if future is not None:
                raise ValueError("Pass callback= or future=, not both!")
            future = self._loop.create_future()
            future.add_done_callback(
                partial(
                    _on_tx_future,
                    self,
                    frame,
                    callback,
                )
            )
        else:
            future = self._ensure_future(future)

        self._log.debug("Adding to queue: %s", frame)
        self._tx_queue.append((frame, future))
        if not self._tx_pending:
            self._schedule_tx()

        return future

    def cancel_transmit(self, frame):
        """
        Cancel the transmission of a frame.
        """
        self._log.debug("Removing from queue: %s", frame)

        found = False
        for idx, (f, future) in enumerate(self._tx_queue):
            if f is frame:
                # Found it!
                found = True
                break

        if not found:
            self._log.debug("Frame not found in queue")
            return

        # It is at idx, so remove it first
        self._tx_queue.pop(idx)
        if _future_ready(future):
            self._log.debug("Notifying caller of cancellation")
            future.set_exception(IOError("Cancelled"))

    def _reset_cts(self):
        """
        Reset the clear-to-send timer.
        """
        cts_expiry = (
            self._loop.time()
            + self._cts_delay
            + (random.random() * self._cts_rand)
        )

        # Ensure CTS expiry never goes backwards!
        while cts_expiry < self._cts_expiry:
            cts_expiry += random.random() * self._cts_rand
        self._cts_expiry = cts_expiry

        self._log.debug("Clear-to-send expiry at %s", self._cts_expiry)
        if self._tx_pending:
            # We were waiting for a clear-to-send, so re-schedule.
            self._schedule_tx()

    def _on_receive(self, frame):
        """
        Handle an incoming message.
        """
        self._reset_cts()
        super(AX25Interface, self)._on_receive(frame)

    def _schedule_tx(self):
        """
        Schedule the transmit timer to take place after the CTS expiry.
        """
        if self._tx_pending:
            self._tx_pending.cancel()

        delay = self._cts_expiry - self._loop.time()
        if delay > 0:
            self._log.debug("Scheduling next transmission in %s", delay)
            self._tx_pending = self._loop.call_later(delay, self._tx_next)
        else:
            self._log.debug("Scheduling next transmission ASAP")
            self._tx_pending = self._loop.call_soon(self._tx_next)

    def _tx_next(self):
        """
        Transmit the next message.
        """
        self._tx_pending = None

        try:
            (frame, future) = self._tx_queue.pop(0)
        except IndexError:
            self._log.debug("No traffic to transmit")
            return

        try:
            if (frame.deadline is not None) and (
                frame.deadline < time.time()
            ):
                self._log.info("Dropping expired frame: %s", frame)
                if _future_ready(future):
                    self._log.debug("Notifying caller of expiry")
                    future.set_exception(IOError("Frame expired"))

                self._schedule_tx()
                return
        except AttributeError:  # pragma: no cover
            # Technically, all objects that pass through here should be
            # AX25Frame sub-classes, so this branch should not get executed.
            # If it does, we just pretend there is no deadline.
            pass

        tx_future = self._loop.create_future()
        tx_future.add_done_callback(partial(self._on_tx_done, frame, future))

        try:
            self._log.debug("Transmitting %s", frame)
            self._port.send(frame, tx_future)
        except Exception as ex:
            self._log.debug("Synchronous transmit failure for %s", frame)
            tx_future.set_exception(ex)

    def _on_tx_done(self, frame, caller, future):
        if future.exception() is not None:
            self._log.error(
                "Failed to transmit frame %s: %s", frame, future.exception()
            )
            if _future_ready(caller):
                caller.set_exception(future.exception())
        else:
            self._log.debug("Transmitted frame: %s", frame)
            if _future_ready(caller):
                caller.set_result(None)

        self._reset_cts()
        if len(self._tx_queue) > 0:
            self._schedule_tx()
