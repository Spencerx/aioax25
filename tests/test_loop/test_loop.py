#!/usr/bin/env python3

from functools import wraps
from asyncio import new_event_loop

import aioax25._loop
from ..loop import DummyLoop


def save_restore_asyncio_funcs(fn):
    @wraps(fn)
    def _fn(*args, **kwargs):
        # Capture existing library functions
        get_event_loop_orig = aioax25._loop.get_event_loop
        new_event_loop_orig = aioax25._loop.new_event_loop
        set_event_loop_orig = aioax25._loop.set_event_loop

        # Stub the functions with do-nothing versions
        def _failing_stub():
            assert False, "Should not have been called"

        aioax25._loop.get_event_loop = _failing_stub
        aioax25._loop.new_event_loop = _failing_stub
        aioax25._loop.set_event_loop = _failing_stub

        try:
            return fn(*args, **kwargs)
        finally:
            # Restore original library functions
            aioax25._loop.get_event_loop = get_event_loop_orig
            aioax25._loop.new_event_loop = new_event_loop_orig
            aioax25._loop.set_event_loop = set_event_loop_orig

    return _fn


@save_restore_asyncio_funcs
def test_elm_get_loop_existing():
    """
    Test we can return a loop if we have one existing.
    """
    # Create a dummy loop for get_event_loop to return
    loop = DummyLoop()

    # Stub get_event_loop
    def _get_event_loop():
        return loop

    aioax25._loop.get_event_loop = _get_event_loop

    # _get_loop should return the loop from _get_event_loop above!
    assert aioax25._loop.LOOPMANAGER._get_loop() is loop


@save_restore_asyncio_funcs
def test_elm_get_loop_new():
    """
    Test a new loop is created when no existing one exists.
    """
    # Create a dummy loop for new_event_loop to return
    loop = DummyLoop()

    # Stub get_event_loop
    def _get_event_loop():
        raise RuntimeError("No loop here")

    aioax25._loop.get_event_loop = _get_event_loop

    # Stub new_event_loop
    def _new_event_loop():
        return loop

    aioax25._loop.new_event_loop = _new_event_loop

    # Stub set_event_loop
    def _set_event_loop(l):
        assert loop is l

    aioax25._loop.set_event_loop = _set_event_loop

    # _get_loop should return the loop from _new_event_loop above!
    assert aioax25._loop.LOOPMANAGER._get_loop() is loop


def test_elm_prohibit_overwrite_loop():
    """
    Test that overwriting an IOLoop is prohibited.
    """
    # Inject a loop instance
    aioax25._loop.LOOPMANAGER._loop = DummyLoop()

    # Attempt to replace that instance
    try:
        aioax25._loop.LOOPMANAGER.loop = DummyLoop()
        assert False, "Should not have worked"
    except RuntimeError:
        pass
    finally:
        # Force drop it for future tests
        aioax25._loop.LOOPMANAGER._loop = None


def test_elm_replace_closed_loop():
    """
    Test that a new loop is fetched if the existing one is closed
    """
    # Inject a loop instance
    orig_loop = new_event_loop()
    aioax25._loop.LOOPMANAGER._loop = orig_loop
    aioax25._loop.LOOPMANAGER._loop.close()

    # Attempt to replace that instance
    try:
        loop = aioax25._loop.LOOPMANAGER.loop

        assert (
            aioax25._loop.LOOPMANAGER._loop is not orig_loop
        ), "Loop not replaced"
    finally:
        # Force drop it for future tests
        aioax25._loop.LOOPMANAGER._loop = None
