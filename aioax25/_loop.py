#!/usr/bin/env python3

"""
Async event loop handling.  This basically tries to handle Python 3.14's
stricter approach to creating and using event loops.
"""

from asyncio import get_event_loop, new_event_loop, set_event_loop

# Forward declaration, will be filled in shortly
LOOPMANAGER = None


class EventLoopManager(object):
    """
    Singleton class that manages access to a single event loop.
    """

    def __init__(self):
        self._loop = None

    @property
    def have_loop(self):
        """
        Return True if we have a loop we can use.
        """
        if self._loop is None:
            return False

        try:
            if self._loop.is_closed():
                return False
        except AttributeError:
            # For test instrumentation!
            pass

        return True

    @property
    def loop(self):
        """
        Retrieve the current library event loop.  A new event loop is
        created if no existing loop exists.
        """

        if not self.have_loop:
            self._loop = self._get_loop()

        return self._loop

    @loop.setter
    def loop(self, new_loop):
        """
        Define the event loop for the library.  The caller is responsible
        for ensuring the loop is registered with the `asyncio` subsystem.
        """
        if self._loop is new_loop:
            # No-op
            return

        if (self._loop is not None) and (new_loop is not None):
            raise RuntimeError("An event loop is already defined")

        self._loop = new_loop

    def _get_loop(self):
        """
        Attempt to quietly retrieve an event loop, or create and register
        one if none exists.
        """

        try:
            return get_event_loop()
        except RuntimeError:
            # No loop is currently running
            pass

        loop = new_event_loop()
        set_event_loop(loop)
        return loop


class EventLoopConsumer(object):
    """
    A mix-in class that sets up an event loop for the class.
    """

    @property
    def _loop(self):
        return LOOPMANAGER.loop

    @_loop.setter
    def _loop(self, new_loop):
        # Silently ignore setting the loop to None.  Allows for
        # constructors that default to using whatever loop we implement.
        if new_loop is not None:
            LOOPMANAGER.loop = new_loop


LOOPMANAGER = EventLoopManager()
