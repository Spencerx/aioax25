#!/usr/bin/env python3

"""
Base KISS interface unit tests.
"""

from aioax25.kiss import (
    BaseKISSDevice,
    KISSDeviceState,
    KISSCommand,
    KISSPort,
    buffer_empty,
)
from aioax25._loop import LOOPMANAGER
from ..loop import DummyLoop
from asyncio import BaseEventLoop, Future

import pytest


class DummyKISSDevice(BaseKISSDevice):
    def __init__(self, **kwargs):
        super(DummyKISSDevice, self).__init__(**kwargs)

        self.transmitted = bytearray()
        self.open_calls = 0
        self.close_calls = 0

    def _open(self):
        self.open_calls += 1

    def _close(self):
        self.close_calls += 1

    def _send_raw_data(self, data):
        if data == b"!":
            raise DummyKISSDeviceError()

        self.transmitted += data

    def _ensure_future(self, future):
        return future


class DummyFutureQueue(object):
    def __init__(self):
        self._exception = None
        self._result = None
        self._state = "unset"
        self.futures = []

    @property
    def exception(self):
        assert self._state == "exception"
        return self._exception

    @property
    def result(self):
        assert self._state == "result"
        return self._result

    def add(self, future):
        self.futures.append(future)

    def set_exception(self, ex):
        self._state = "exception"
        self._exception = ex

    def set_result(self, v):
        self._state = "result"
        self._result = v


class DummyKISSDeviceError(IOError):
    pass


class FailingKISSDevice(BaseKISSDevice):
    def __init__(self, **kwargs):
        super(FailingKISSDevice, self).__init__(**kwargs)

        self.transmitted = bytearray()
        self.open_calls = 0
        self.close_calls = 0

    def _open(self):
        self.open_calls += 1
        raise DummyKISSDeviceError("Open fails")

    def _close(self):
        self.close_calls += 1
        raise DummyKISSDeviceError("Close fails")

    def _send_raw_data(self, data):
        self.transmitted += data
        raise DummyKISSDeviceError("Send fails")


def test_buffer_empty_no_data():
    """
    Test buffer_empty considers an empty buffer is really empty
    """
    assert buffer_empty(b"") is True


def test_buffer_empty_fend():
    """
    Test buffer_empty considers an buffer containing only FEND is empty
    """
    assert buffer_empty(b"\xc0") is True


def test_buffer_empty_not_fend():
    """
    Test buffer_empty considers an buffer containing a non-FEND byte is
    not empty
    """
    assert buffer_empty(b"\x00") is False


def test_buffer_empty_multiple_bytes():
    """
    Test buffer_empty considers an buffer containing multiple bytes is
    not empty.
    """
    assert buffer_empty(b"\xc0\xc0") is False


def test_constructor_own_loop():
    """
    Test constructor uses its own IOLoop if not given one
    """
    LOOPMANAGER.loop = None
    kissdev = DummyKISSDevice(loop=None)
    assert isinstance(kissdev._loop, BaseEventLoop)


@pytest.mark.asyncio
async def test_ensure_future_given():
    """
    Test _ensure_future returns the future it's given
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = BaseKISSDevice(loop=loop, return_future=False)

    future = Future()
    assert kissdev._ensure_future(future) is future, \
            "Didn't return our future to us"

@pytest.mark.asyncio
async def test_ensure_future_created():
    """
    Test _ensure_future creates a future if given None
    """
    LOOPMANAGER.loop = None
    future = Future()

    class MyLoop(DummyLoop):
        def __init__(self):
            super(MyLoop, self).__init__()
            self.create_future_called = 0

        def create_future(self):
            self.create_future_called += 1
            return future

    loop = MyLoop()
    kissdev = BaseKISSDevice(loop=loop, return_future=True)

    result = kissdev._ensure_future(None)
    assert loop.create_future_called == 1, \
            "Didn't create a future via the IO loop"
    assert result is future, \
            "Didn't return our future to us"

def test_ensure_future_oneshot():
    """
    Test _ensure_future in oneshot mode returns None if given None
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = BaseKISSDevice(loop=loop, return_future=False)

    assert kissdev._ensure_future(None) is None


def test_open():
    """
    Test an open call passes to subclass _open
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    assert kissdev.open_calls == 0
    kissdev.open()

    assert kissdev.open_calls == 1

    assert failures == []


def test_open_multiple():
    """
    Test that calling open on a port that's opening, will add a future
    to the queue.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    future = Future()
    kissdev = DummyKISSDevice(loop=loop)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    assert kissdev.open_calls == 0
    kissdev.open()

    assert kissdev.open_calls == 1

    # Call again, this time pass in a future
    kissdev.open(future)

    # We should have just one call, but our future object will be queued.
    assert kissdev.open_calls == 1
    assert len(kissdev._open_queue._futures) > 0
    (f, _) = kissdev._open_queue._futures.pop(0)
    assert f is future

    assert failures == []


def test_open_async():
    """
    Test that calling open in async mode adds the future to a queue
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    future = Future()
    kissdev = DummyKISSDevice(loop=loop, return_future=True)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    assert kissdev.open_calls == 0
    kissdev.open(future)

    # We should have just one call, the future we were given should be queued.
    assert kissdev.open_calls == 1
    assert len(kissdev._open_queue._futures) > 0
    (f, _) = kissdev._open_queue._futures.pop(0)
    assert f is future

    assert failures == []


def test_open_fail():
    """
    Test an open call that fails triggers the failed signal
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = FailingKISSDevice(loop=loop)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    assert kissdev.open_calls == 0
    try:
        kissdev.open()
        open_ex = None
    except DummyKISSDeviceError as e:
        assert str(e) == "Open fails"
        open_ex = e

    assert kissdev.open_calls == 1
    assert kissdev.state == KISSDeviceState.FAILED
    assert len(failures) == 1
    failure = failures.pop(0)

    assert failure.pop("action") == "open"
    (ex_c, ex_v, _) = failure.pop("exc_info")
    assert ex_c is DummyKISSDeviceError
    assert ex_v is open_ex


def test_close():
    """
    Test a close call passes to _close
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=False)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Force the port open
    kissdev._state = KISSDeviceState.OPEN

    assert kissdev.close_calls == 0

    # Now try closing the port
    kissdev.close()
    assert kissdev.close_calls == 1

    assert failures == []


def test_close_multiple():
    """
    Test calling close whilst closing just adds a future
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    future = Future()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=False)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Force the port open
    kissdev._state = KISSDeviceState.OPEN

    assert kissdev.close_calls == 0

    # Now try closing the port
    kissdev.close()
    assert kissdev.close_calls == 1

    # Try again passing in a future
    kissdev.close(future)

    # We should have just one call, the future we were given should be queued.
    assert kissdev.close_calls == 1
    assert len(kissdev._close_queue._futures) > 0
    (f, _) = kissdev._close_queue._futures.pop(0)
    assert f is future

    assert failures == []


def test_close_async():
    """
    Test calling close adds future to queue
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    future = Future()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=False)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Force the port open
    kissdev._state = KISSDeviceState.OPEN

    assert kissdev.close_calls == 0

    # Now try closing the port
    kissdev.close(future)

    assert kissdev.close_calls == 1
    assert len(kissdev._close_queue._futures) > 0
    (f, _) = kissdev._close_queue._futures.pop(0)
    assert f is future

    assert failures == []


def test_close_fail():
    """
    Test a close call that fails triggers the failed signal
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = FailingKISSDevice(loop=loop, reset_on_close=False)

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Force the port open
    kissdev._state = KISSDeviceState.OPEN

    assert kissdev.close_calls == 0

    # Now try closing the port
    try:
        kissdev.close()
        close_ex = None
    except DummyKISSDeviceError as e:
        assert str(e) == "Close fails"
        close_ex = e

    assert kissdev.close_calls == 1
    assert kissdev.state == KISSDeviceState.FAILED
    assert len(failures) == 1
    failure = failures.pop(0)

    assert failure.pop("action") == "close"
    (ex_c, ex_v, _) = failure.pop("exc_info")
    assert ex_c is DummyKISSDeviceError
    assert ex_v is close_ex


def test_close_reset():
    """
    Test a close call with reset_on_close sends the "return from KISS" frame
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)

    # Force the port open
    kissdev._state = KISSDeviceState.OPEN

    # Now try closing the port
    kissdev.close()

    # Should be in the closing state
    assert kissdev._state == KISSDeviceState.CLOSING

    # A "return from KISS" frame should be in the transmit buffer (minus FEND
    # bytes)
    assert kissdev._tx_queue == [(b"\xff", None)]

    # A call to _send_data should be pending
    (_, func) = loop.calls.pop()
    assert func == kissdev._send_data


def test_reset():
    """
    Test a reset call resets a failed device
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=False)

    # Force the port failed
    kissdev._state = KISSDeviceState.FAILED

    # Reset the device
    kissdev.reset()

    assert kissdev._state == KISSDeviceState.CLOSED


def test_receive():
    """
    Test that a call to _receive stashes the data then schedules _receive_frame.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._receive(b"test incoming data")

    # Data should be waiting
    assert bytes(kissdev._rx_buffer) == b"test incoming data"

    # A call to _receive_frame should be pending
    (_, func) = loop.calls.pop()
    assert func == kissdev._receive_frame


def test_receive_opening():
    """
    Test that a call to _receive whilst in "OPENING" state stashes the data then schedules _check_open.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)

    # Inject the state
    kissdev._state = KISSDeviceState.OPENING

    # Pass the data in
    kissdev._receive(b"test incoming data")

    # Data should be waiting
    assert bytes(kissdev._rx_buffer) == b"test incoming data"

    # A call to _check_open should be pending
    (_, func) = loop.calls.pop()
    assert func == kissdev._check_open


def test_receive_frame_garbage():
    """
    Test _receive_frame discards all data when no FEND byte found.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._rx_buffer += b"this should be discarded"
    kissdev._receive_frame()

    # We should just have the data including and following the FEND
    assert bytes(kissdev._rx_buffer) == b""

    # As there's no complete frames, no calls should be scheduled
    assert len(loop.calls) == 0


def test_receive_frame_garbage_start():
    """
    Test _receive_frame discards everything up to the first FEND byte.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._rx_buffer += b"this should be discarded\xc0this should be kept"
    kissdev._receive_frame()

    # We should just have the data including and following the FEND
    assert bytes(kissdev._rx_buffer) == b"\xc0this should be kept"

    # As there's no complete frames, no calls should be scheduled
    assert len(loop.calls) == 0


def test_receive_frame_single_fend():
    """
    Test _receive_frame does nothing if there's only a FEND byte.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._rx_buffer += b"\xc0"
    kissdev._receive_frame()

    # We should just have the last FEND
    assert bytes(kissdev._rx_buffer) == b"\xc0"

    # It should leave the last FEND there and wait for more data.
    assert len(loop.calls) == 0


def test_receive_frame_empty():
    """
    Test _receive_frame discards empty frames.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._rx_buffer += b"\xc0\xc0"
    kissdev._receive_frame()

    # We should just have the last FEND
    assert bytes(kissdev._rx_buffer) == b"\xc0"

    # It should leave the last FEND there and wait for more data.
    assert len(loop.calls) == 0


def test_receive_frame_single():
    """
    Test _receive_frame hands a single frame to _dispatch_rx_frame.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._rx_buffer += b"\xc0\x00a single KISS frame\xc0"
    kissdev._receive_frame()

    # We should just have the last FEND
    assert bytes(kissdev._rx_buffer) == b"\xc0"

    # We should have one call to _dispatch_rx_frame
    assert len(loop.calls) == 1
    (_, func, frame) = loop.calls.pop(0)
    assert func == kissdev._dispatch_rx_frame
    assert isinstance(frame, KISSCommand)
    assert frame.port == 0
    assert frame.cmd == 0
    assert frame.payload == b"a single KISS frame"


def test_receive_frame_more():
    """
    Test _receive_frame calls itself when more data left.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)
    kissdev._rx_buffer += b"\xc0\x00a single KISS frame\xc0more data"
    kissdev._receive_frame()

    # We should just have the left-over bit including the last FEND
    assert bytes(kissdev._rx_buffer) == b"\xc0more data"

    # This should have generated two calls:
    assert len(loop.calls) == 2

    # We should have one call to _dispatch_rx_frame
    (_, func, frame) = loop.calls.pop(0)
    assert func == kissdev._dispatch_rx_frame
    assert isinstance(frame, KISSCommand)
    assert frame.port == 0
    assert frame.cmd == 0
    assert frame.payload == b"a single KISS frame"

    # We should have another to _receive_frame itself.
    (_, func) = loop.calls.pop(0)
    assert func == kissdev._receive_frame


def test_dispatch_rx_invalid_port():
    """
    Test that _dispatch_rx_port to an undefined port drops the frame.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    kissdev._dispatch_rx_frame(
        KISSCommand(cmd=10, port=14, payload=b"this should be dropped")
    )


def test_dispatch_rx_exception():
    """
    Test that _dispatch_rx_port drops frame on exception.
    """
    LOOPMANAGER.loop = None

    class DummyPort(object):
        def _receive_frame(self, frame):
            raise IOError("Whoopsie")

    port = DummyPort()
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    kissdev._port[14] = port

    # Deliver the frame
    frame = KISSCommand(cmd=10, port=14, payload=b"this should be dropped")
    kissdev._dispatch_rx_frame(frame)


def test_dispatch_rx_valid_port():
    """
    Test that _dispatch_rx_port to a known port delivers to that port.
    """
    LOOPMANAGER.loop = None

    class DummyPort(object):
        def __init__(self):
            self.frames = []

        def _receive_frame(self, frame):
            self.frames.append(frame)

    port = DummyPort()
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    kissdev._port[14] = port

    # Deliver the frame
    frame = KISSCommand(cmd=10, port=14, payload=b"this should be delivered")
    kissdev._dispatch_rx_frame(frame)

    # Our port should have the frame
    assert len(port.frames) == 1
    assert port.frames[0] is frame


def test_send():
    """
    Test that _send appends a frame to the transmit queue then schedules
    _send_data to transmit it.
    """
    LOOPMANAGER.loop = None

    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)

    # Queue should be empty
    assert kissdev._tx_queue == []

    # Make a dummy frame object to enqueue
    class MyFrame(object):
        def __init__(self, data):
            self._data = data

        def __bytes__(self):
            return self._data.encode()

    # Enqueue a frame, without a future
    kissdev._send(MyFrame("testing 1 2 3 4"))

    # The frame should now be in the TX buffer
    assert kissdev._tx_queue == [(b"testing 1 2 3 4", None)]

    # We should have a call to _send_data scheduled.
    (_, func) = loop.calls.pop(0)
    assert func == kissdev._send_data


def test_send_future():
    """
    Test that _send with a future, stores the future with the frame to send.
    """
    LOOPMANAGER.loop = None

    class DummyFuture(object):
        pass

    future = DummyFuture()
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)

    # Queue should be empty
    assert kissdev._tx_queue == []

    # Make a dummy frame object to enqueue
    class MyFrame(object):
        def __init__(self, data):
            self._data = data

        def __bytes__(self):
            return self._data.encode()

    # Enqueue a frame, without a future
    kissdev._send(MyFrame("testing 1 2 3 4"), future)

    # The frame should now be in the TX buffer
    assert kissdev._tx_queue == [(b"testing 1 2 3 4", future)]

    # We should have a call to _send_data scheduled.
    (_, func) = loop.calls.pop(0)
    assert func == kissdev._send_data


def test_send_data():
    """
    Test that _send_data sends whatever data is buffered up to the block size.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    kissdev._tx_buffer += b"test output data"

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Send the data out.
    kissdev._send_data()

    # We should now see this was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"test output data"

    # That should be the lot
    assert len(loop.calls) == 0

    # There should be no failures
    assert failures == []


def test_send_data_emptybuffer():
    """
    Test that _send_data will pick the next frame off the transmit queue if
    it has nothing to send in the buffer.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    my_future = Future()
    assert bytes(kissdev._tx_buffer) == b""

    kissdev._tx_queue = [(b"test output data", my_future)]

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Send the data out.
    kissdev._send_data()

    # We should now see this was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"\xc0test output data\xc0"

    # my_future should be the current transmit future
    assert kissdev._tx_future is my_future

    # That should be the lot
    assert len(loop.calls) == 0

    # There should be no failures
    assert failures == []


def test_send_data_emptybuffer_emptyqueue():
    """
    Test that _send_data does nothing if all queues are empty.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    assert bytes(kissdev._tx_buffer) == b""
    assert kissdev._tx_queue == []

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Send the data out.
    kissdev._send_data()

    # That should be the lot
    assert len(loop.calls) == 0

    # There should be no failures
    assert failures == []


def test_send_data_fail():
    """
    Test that _send_data puts device in failed state if send fails.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = FailingKISSDevice(loop=loop)
    kissdev._tx_buffer += b"test output data"

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Send the data out.
    try:
        kissdev._send_data()
        send_ex = None
    except DummyKISSDeviceError as e:
        assert str(e) == "Send fails"
        send_ex = e

    # We should now see this was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"test output data"

    # That should be the lot
    assert len(loop.calls) == 0

    # We should be in the failed state
    assert kissdev.state == KISSDeviceState.FAILED
    assert len(failures) == 1
    failure = failures.pop(0)

    assert failure.pop("action") == "send"
    (ex_c, ex_v, _) = failure.pop("exc_info")
    assert ex_c is DummyKISSDeviceError
    assert ex_v is send_ex


def test_send_data_fail_future():
    """
    Test that _send_data passes the exception to the future if given one.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    future = Future()
    kissdev = FailingKISSDevice(loop=loop)
    kissdev._tx_buffer += b"test output data"
    kissdev._tx_future = future

    failures = []

    def _on_fail(**kwargs):
        failures.append(kwargs)

    kissdev.failed.connect(_on_fail)

    # Send the data out.
    try:
        kissdev._send_data()
        send_ex = None
    except DummyKISSDeviceError as e:
        assert str(e) == "Send fails"
        send_ex = e

    # We should now see this was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"test output data"

    # That should be the lot
    assert len(loop.calls) == 0

    # We should be in the failed state
    assert kissdev.state == KISSDeviceState.FAILED
    assert len(failures) == 1
    failure = failures.pop(0)

    assert failure.pop("action") == "send"
    (ex_c, ex_v, _) = failure.pop("exc_info")
    assert ex_c is DummyKISSDeviceError
    assert ex_v is send_ex

    assert future.exception() is send_ex


def test_send_data_block_size_exceed_reschedule():
    """
    Test that _send_data re-schedules itself when buffer exceeds block size
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(
        loop=loop, send_block_size=4, send_block_delay=1
    )
    kissdev._tx_buffer += b"test output data"

    # Send the data out.
    kissdev._send_data()

    # We should now see the first block was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"test"

    # The rest should be waiting
    assert bytes(kissdev._tx_buffer) == b" output data"

    # There should be a pending call to send more:
    assert len(loop.calls) == 1
    (calltime, callfunc) = loop.calls.pop(0)

    # It'll be roughly in a second's time calling the same function
    assert (calltime - loop.time()) > (0.990)
    assert (calltime - loop.time()) < (1.0)
    assert callfunc == kissdev._send_data


def test_send_data_close_after_send():
    """
    Test that _send_data when closing the device, closes after last send
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)
    kissdev._tx_buffer += b"test output data"

    # Force state
    kissdev._state = KISSDeviceState.CLOSING
    kissdev._close_queue = DummyFutureQueue()

    # No close call made yet
    assert kissdev.close_calls == 0

    # Send the data out.
    kissdev._send_data()

    # We should now see the first block was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"test output data"

    # The device should now be closed.
    assert kissdev.close_calls == 1


def test_send_data_all_sent_before_close():
    """
    Test that _send_data waits until all data sent before closing.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(
        loop=loop, send_block_size=4, send_block_delay=1
    )
    kissdev._tx_buffer += b"test output data"

    # Force state
    kissdev._state = KISSDeviceState.CLOSING

    # Send the data out.
    kissdev._send_data()

    # We should now see the first block was "sent" and now in 'transmitted'
    assert bytes(kissdev.transmitted) == b"test"

    # The rest should be waiting
    assert bytes(kissdev._tx_buffer) == b" output data"

    # There should be a pending call to send more:
    assert len(loop.calls) == 1
    (calltime, callfunc) = loop.calls.pop(0)

    # It'll be roughly in a second's time calling the same function
    assert (calltime - loop.time()) > (0.990)
    assert (calltime - loop.time()) < (1.0)
    assert callfunc == kissdev._send_data

    # No close call made yet
    assert kissdev.close_calls == 0


def test_mark_sent_mismatch():
    """
    Test _mark_sent flags an exception if the data does not match.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(
        loop=loop, send_block_size=4, send_block_delay=1
    )
    kissdev._tx_buffer += b"test output data"

    try:
        kissdev._mark_sent(b"data not in buffer", None)
        assert False, "Should not have worked"
    except AssertionError as e:
        if str(e) != "Did not find sent data in the transmit buffer!":
            raise


def test_mark_sent_mismatch_future():
    """
    Test _mark_sent passes mismatch assertions to future.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    future = Future()
    kissdev = DummyKISSDevice(
        loop=loop, send_block_size=4, send_block_delay=1
    )
    kissdev._tx_buffer += b"test output data"

    assert_ex = None
    try:
        kissdev._mark_sent(b"data not in buffer", future)
        assert False, "Should not have worked"
    except AssertionError as e:
        if str(e) != "Did not find sent data in the transmit buffer!":
            raise
        assert_ex = e

    assert future.exception() is assert_ex


def test_init_kiss():
    """
    Test _init_kiss sets up the commands to be sent to initialise KISS
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop)

    # Force state
    kissdev._state = KISSDeviceState.OPENING

    # Initialise the KISS device
    kissdev._init_kiss()

    # We should see a copy of the KISS commands, minus the first
    assert kissdev._kiss_rem_commands == kissdev._kiss_commands[1:]

    # We should see the first initialisation commands
    assert bytes(kissdev.transmitted) == b"INT KISS\r"


def test_getitem():
    """
    Test __getitem__ returns a port instance.
    """
    LOOPMANAGER.loop = None
    kissdev = DummyKISSDevice(loop=DummyLoop())
    port = kissdev[7]
    assert isinstance(port, KISSPort)
    assert kissdev._port[7] is port


def test_send_kiss_cmd_done():
    """
    Test _send_kiss_cmd marks the port as open if there's nothing more to
    send.
    """

    LOOPMANAGER.loop = None
    kissdev = DummyKISSDevice(loop=DummyLoop())
    kissdev._kiss_rem_commands = []
    open_queue = DummyFutureQueue()
    kissdev._open_queue = open_queue

    kissdev._send_kiss_cmd()
    assert KISSDeviceState.OPEN == kissdev._state
    assert bytearray() == kissdev._rx_buffer

    assert kissdev._open_queue is None
    assert open_queue.result is None


def test_send_kiss_cmd_next():
    """
    Test _send_kiss_cmd transmits the next command before calling _check_open
    again.
    """

    LOOPMANAGER.loop = None
    kissdev = DummyKISSDevice(loop=DummyLoop())
    kissdev._kiss_rem_commands = [
            "dummy command"
    ]
    open_queue = DummyFutureQueue()
    kissdev._open_queue = open_queue
    kissdev._state = KISSDeviceState.OPENING

    kissdev._send_kiss_cmd()
    assert KISSDeviceState.OPENING == kissdev._state
    assert b"dummy command\r" == bytes(kissdev.transmitted)
    assert kissdev._open_queue is open_queue


def test_send_kiss_cmd_fail():
    """
    Test _send_kiss_cmd handles failures in transmission.
    """

    LOOPMANAGER.loop = None
    kissdev = DummyKISSDevice(loop=DummyLoop())
    kissdev._kiss_rem_commands = [
            "!"  # Make it fail
    ]
    open_queue = DummyFutureQueue()
    kissdev._open_queue = open_queue

    tx_ex = None

    try:
        kissdev._send_kiss_cmd()
        assert False, "Should not have passed"
    except DummyKISSDeviceError as ex:
        tx_ex = ex

    assert KISSDeviceState.FAILED == kissdev._state
    assert kissdev._open_queue is None
    assert open_queue.exception is tx_ex


def test_check_open():
    """
    Test that a call to _check_open hands-off to _send_kiss_cmd.
    """
    LOOPMANAGER.loop = None
    loop = DummyLoop()
    kissdev = DummyKISSDevice(loop=loop, reset_on_close=True)

    # Call the function under test
    kissdev._check_open()

    # A call to _send_kiss_cmd should be pending
    (_, func) = loop.calls.pop()
    assert func == kissdev._send_kiss_cmd
