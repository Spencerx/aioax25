#!/usr/bin/env python3

"""
TCP server KISS interface unit tests.
"""

# Most of the functionality here is common to SerialKISSDevice, so this
# really just tests that we pass the right commands to the IOLoop when
# establishing a connection.

from aioax25 import kiss
from aioax25._loop import LOOPMANAGER
import logging
from asyncio import get_event_loop

import pytest


@pytest.mark.asyncio
async def test_open_connection():
    LOOPMANAGER.loop = None

    # This will receive the arguments passed to create_connection
    connection_args = {}

    loop = get_event_loop()

    # Stub the create_connection method
    orig_create_server = loop.create_server

    async def _create_server(proto_factory, **kwargs):
        # proto_factory should give us a KISSProtocol object
        protocol = proto_factory()
        assert isinstance(protocol, kiss.KISSProtocol)

        connection_args.update(kwargs)

    loop.create_server = _create_server

    try:
        device = kiss.TCPKISSServer(
            port=5432,
            loop=loop,
            log=logging.getLogger(__name__),
        )

        await device._open_connection()

        # Expect a connection attempt to have been made
        assert connection_args == dict(
            host="::",
            port=5432,
            ssl=None,
            family=0,
            flags=0,
            sock=None,
            backlog=1,
            reuse_address=None,
            reuse_port=None,
        )
    finally:
        # Restore mock
        loop.create_server = orig_create_server


@pytest.mark.asyncio
async def test_open_connection_fail():
    LOOPMANAGER.loop = None

    # This will receive the arguments passed to create_connection
    connection_args = {}

    loop = get_event_loop()

    # Stub the create_connection method
    orig_create_server = loop.create_server

    async def _create_server(proto_factory, **kwargs):
        # proto_factory should give us a KISSProtocol object
        protocol = proto_factory()
        assert isinstance(protocol, kiss.KISSProtocol)

        connection_args.update(kwargs)
        raise IOError("Connection failed")

    loop.create_server = _create_server

    try:
        device = kiss.TCPKISSServer(
            port=5432,
            loop=loop,
            log=logging.getLogger(__name__),
        )

        failures = []

        def _on_fail(**kwargs):
            failures.append(kwargs)

        device.failed.connect(_on_fail)

        await device._open_connection()

        # Expect a connection attempt to have been made
        assert connection_args == dict(
            host="::",
            port=5432,
            ssl=None,
            family=0,
            flags=0,
            sock=None,
            backlog=1,
            reuse_address=None,
            reuse_port=None,
        )

        # Connection should be in the failed state
        assert device.state == kiss.KISSDeviceState.FAILED

        # Failure should have been reported
        assert failures
        failure = failures.pop(0)

        assert failure.pop("action") == "open"
        ex_c, ex_v, _ = failure.pop("exc_info")
        assert ex_c is IOError
        assert str(ex_v) == "Connection failed"
    finally:
        # Restore mock
        loop.create_server = orig_create_server


@pytest.mark.asyncio
async def test_on_connect():
    LOOPMANAGER.loop = None

    loop = get_event_loop()

    class DummyKISSTransport(object):
        def write(self, data):
            pass

    class TESTTCPKISSServer(kiss.TCPKISSServer):
        def __init__(self, *args, **kwargs):
            super(TESTTCPKISSServer, self).__init__(*args, **kwargs)

            self.open_called = False

        def open(self, *args, **kwargs):
            assert self.open_called is False, "open() already called!"
            self.open_called = True

        def _init_kiss(self):
            pass

    device = TESTTCPKISSServer(
        port=5432,
        loop=loop,
        log=logging.getLogger(__name__),
    )

    assert (
        device._state is kiss.KISSDeviceState.CLOSED
    ), "Device is not CLOSED"
    assert (
        device._transport is None
    ), "Device has a transport when it shouldn't"

    transport = DummyKISSTransport()
    device._on_connect(transport)

    assert device.open_called is True, "Device did call open() on connect"
    assert (
        device._transport is transport
    ), "Device did not store received transport object"


@pytest.mark.asyncio
async def test_on_connect_not_closed():
    LOOPMANAGER.loop = None

    loop = get_event_loop()

    class DummyKISSTransport(object):
        def write(self, data):
            pass

    class TESTTCPKISSServer(kiss.TCPKISSServer):
        def __init__(self, *args, **kwargs):
            super(TESTTCPKISSServer, self).__init__(*args, **kwargs)

            self.open_called = False

        def open(self, *args, **kwargs):
            assert self.open_called is False, "open() already called!"
            self.open_called = True

        def _init_kiss(self):
            pass

    device = TESTTCPKISSServer(
        port=5432,
        loop=loop,
        log=logging.getLogger(__name__),
    )

    assert (
        device._state is kiss.KISSDeviceState.CLOSED
    ), "Device is not CLOSED"
    assert (
        device._transport is None
    ), "Device has a transport when it shouldn't"

    # Inject state
    device._state = kiss.KISSDeviceState.OPENING

    transport = DummyKISSTransport()
    device._on_connect(transport)

    assert (
        device._state is kiss.KISSDeviceState.OPENING
    ), "Device is not OPENING"
    assert (
        device.open_called is False
    ), "Device called open() on connect when it shouldn't"
    assert (
        device._transport is transport
    ), "Device did not store received transport object"
