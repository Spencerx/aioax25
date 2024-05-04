#!/usr/bin/env python3

"""
Test handling of outgoing connection logic
"""

from aioax25.version import AX25Version
from aioax25.frame import AX25Address, AX25Path, \
        AX25DisconnectFrame, \
        AX25DisconnectModeFrame, \
        AX25FrameRejectFrame, \
        AX25UnnumberedAcknowledgeFrame, \
        AX25TestFrame, \
        AX25SetAsyncBalancedModeFrame, \
        AX25SetAsyncBalancedModeExtendedFrame
from .peer import TestingAX25Peer
from ..mocks import DummyStation

# Connection establishment

def test_connect_not_disconnected():
    """
    Test that calling peer.connect() when not disconnected does nothing.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub negotiation, this should not get called
    def _negotiate(*args, **kwargs):
        assert False, 'Should not have been called'
    peer._negotiate = _negotiate

    # Ensure _negotiate() gets called if we try to connect
    peer._negotiated = False

    # Override the state to ensure connection attempt never happens
    peer._state = peer.AX25PeerState.CONNECTED

    # Now try connecting
    peer.connect()


def test_connect_when_disconnected():
    """
    Test that calling peer.connect() when disconnected initiates connection
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub negotiation, we'll just throw an error to see if it gets called
    class ConnectionStarted(Exception):
        pass
    def _negotiate(*args, **kwargs):
        raise ConnectionStarted()
    peer._negotiate = _negotiate

    # Ensure _negotiate() gets called if we try to connect
    peer._negotiated = False

    # Ensure disconnected state
    peer._state = peer.AX25PeerState.DISCONNECTED

    # Now try connecting
    try:
        peer.connect()
        assert False, 'Did not call _negotiate'
    except ConnectionStarted:
        pass


# SABM(E) transmission

def test_send_sabm():
    """
    Test we can send a SABM (modulo-8)
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub _transmit_frame
    sent = []
    def _transmit_frame(frame):
        sent.append(frame)
    peer._transmit_frame = _transmit_frame

    peer._send_sabm()

    try:
        frame = sent.pop(0)
    except IndexError:
        assert False, 'No frames were sent'

    assert isinstance(frame, AX25SetAsyncBalancedModeFrame)
    assert str(frame.header.destination) == 'VK4MSL'
    assert str(frame.header.source) == 'VK4MSL-1'
    assert str(frame.header.repeaters) == 'VK4RZB'
    assert len(sent) == 0

    assert peer._state == peer.AX25PeerState.CONNECTING


def test_send_sabme():
    """
    Test we can send a SABM (modulo-128)
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )
    peer._modulo128 = True

    # Stub _transmit_frame
    sent = []
    def _transmit_frame(frame):
        sent.append(frame)
    peer._transmit_frame = _transmit_frame

    peer._send_sabm()

    try:
        frame = sent.pop(0)
    except IndexError:
        assert False, 'No frames were sent'

    assert isinstance(frame, AX25SetAsyncBalancedModeExtendedFrame)
    assert str(frame.header.destination) == 'VK4MSL'
    assert str(frame.header.source) == 'VK4MSL-1'
    assert str(frame.header.repeaters) == 'VK4RZB'
    assert len(sent) == 0

    assert peer._state == peer.AX25PeerState.CONNECTING


# SABM response handling


def test_recv_ignore_frmr():
    """
    Test that we ignore FRMR from peer when connecting.

    (AX.25 2.2 sect 6.3.1)
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Stub FRMR handling
    def _on_receive_frmr():
        assert False, 'Should not have been called'
    peer._on_receive_frmr = _on_receive_frmr

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    peer._on_receive(
            AX25FrameRejectFrame(
                destination=AX25Address('VK4MSL-1'),
                source=AX25Address('VK4MSL'),
                repeaters=AX25Path('VK4RZB'),
                w=False, x=False, y=False, z=False,
                frmr_cr=False, vs=0, vr=0, frmr_control=0
            )
    )


def test_recv_ignore_test():
    """
    Test that we ignore TEST from peer when connecting.

    (AX.25 2.2 sect 6.3.1)
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Stub TEST handling
    def _on_receive_test():
        assert False, 'Should not have been called'
    peer._on_receive_test = _on_receive_test

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    peer._on_receive(
            AX25TestFrame(
                destination=AX25Address('VK4MSL-1'),
                source=AX25Address('VK4MSL'),
                repeaters=AX25Path('VK4RZB'),
                payload=b'Frame to be ignored'
            )
    )


def test_recv_ua():
    """
    Test that UA is handled.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Create a handler for receiving the UA
    count = dict(ua=0)
    def _on_receive_ua():
        count['ua'] += 1
    peer._uaframe_handler = _on_receive_ua

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    peer._on_receive(
            AX25UnnumberedAcknowledgeFrame(
                destination=AX25Address('VK4MSL-1'),
                source=AX25Address('VK4MSL'),
                repeaters=AX25Path('VK4RZB')
            )
    )

    # Our handler should have been called
    assert count == dict(ua=1)


def test_recv_disc():
    """
    Test that DISC is handled.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Stub _send_ua and _on_disconnect
    count = dict(send_ua=0, on_disc=0)
    def _send_ua():
        count['send_ua'] += 1
    peer._send_ua = _send_ua
    def _on_disconnect():
        count['on_disc'] += 1
    peer._on_disconnect = _on_disconnect

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    peer._on_receive(
            AX25DisconnectFrame(
                destination=AX25Address('VK4MSL-1'),
                source=AX25Address('VK4MSL'),
                repeaters=AX25Path('VK4RZB')
            )
    )

    # Our handlers should have been called
    assert count == dict(send_ua=1, on_disc=1)


def test_recv_dm():
    """
    Test that DM is handled.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Stub _dmframe_handler and _on_disconnect
    count = dict(on_disc=0)
    def _dmframe_handler():
        assert False, '_dmframe_handler should not have been called'
    peer._dmframe_handler = _dmframe_handler
    def _on_disconnect():
        count['on_disc'] += 1
    peer._on_disconnect = _on_disconnect

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    peer._on_receive(
            AX25DisconnectModeFrame(
                destination=AX25Address('VK4MSL-1'),
                source=AX25Address('VK4MSL'),
                repeaters=AX25Path('VK4RZB')
            )
    )

    # Our handlers should have been called
    assert count == dict(on_disc=1)

    # We should not have removed the DM frame handler
    assert peer._dmframe_handler is not None


def test_recv_sabm():
    """
    Test that SABM is handled.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Stub _on_receive_sabm, we'll test it fully later
    frames = []
    def _on_receive_sabm(frame):
        frames.append(frame)
    peer._on_receive_sabm = _on_receive_sabm

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    frame = AX25SetAsyncBalancedModeFrame(
        destination=AX25Address('VK4MSL-1'),
        source=AX25Address('VK4MSL'),
        repeaters=AX25Path('VK4RZB')
    )
    peer._on_receive(frame)

    assert frames == [frame]


def test_recv_sabme():
    """
    Test that SABME is handled.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub idle time-out handling
    peer._reset_idle_timeout = lambda : None

    # Stub _on_receive_sabm, we'll test it fully later
    frames = []
    def _on_receive_sabm(frame):
        frames.append(frame)
    peer._on_receive_sabm = _on_receive_sabm

    # Set the state
    peer._state = peer.AX25PeerState.CONNECTING

    # Inject a frame
    frame = AX25SetAsyncBalancedModeExtendedFrame(
        destination=AX25Address('VK4MSL-1'),
        source=AX25Address('VK4MSL'),
        repeaters=AX25Path('VK4RZB')
    )
    peer._on_receive(frame)

    assert frames == [frame]


# SABM(E) handling


def test_on_receive_sabm_init():
    """
    Test the incoming connection is initialised on receipt of SABM.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Stub _init_connection
    count = dict(init=0, start_timer=0, conn_rq=0)
    def _init_connection(extended):
        assert extended is False
        count['init'] += 1
    peer._init_connection = _init_connection

    # Stub _start_incoming_connect_timer
    def _start_incoming_connect_timer():
        count['start_timer'] += 1
    peer._start_incoming_connect_timer = _start_incoming_connect_timer

    # Hook connection request event
    def _on_conn_rq(**kwargs):
        assert kwargs == dict(peer=peer)
        count['conn_rq'] += 1
    station.connection_request.connect(_on_conn_rq)

    peer._on_receive_sabm(
        AX25SetAsyncBalancedModeFrame(
            destination=AX25Address('VK4MSL-1'),
            source=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB')
        )
    )


def test_on_receive_sabme_init():
    """
    Test the incoming connection is initialised on receipt of SABME.
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Assume we know it's an AX.25 2.2 peer
    peer._protocol = AX25Version.AX25_22

    # Stub _init_connection
    count = dict(init=0, start_timer=0, conn_rq=0)
    def _init_connection(extended):
        assert extended is True
        count['init'] += 1
    peer._init_connection = _init_connection

    # Stub _start_incoming_connect_timer
    def _start_incoming_connect_timer():
        count['start_timer'] += 1
    peer._start_incoming_connect_timer = _start_incoming_connect_timer

    # Hook connection request event
    def _on_conn_rq(**kwargs):
        assert kwargs == dict(peer=peer)
        count['conn_rq'] += 1
    station.connection_request.connect(_on_conn_rq)

    peer._on_receive_sabm(
        AX25SetAsyncBalancedModeExtendedFrame(
            destination=AX25Address('VK4MSL-1'),
            source=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB')
        )
    )


def test_on_receive_sabme_init_unknown_peer_ver():
    """
    Test we switch the peer to AX.25 2.2 mode on receipt of SABME
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Assume we do not know the peer's AX.25 version
    peer._protocol = AX25Version.UNKNOWN

    # Stub _init_connection
    count = dict(init=0, start_timer=0, conn_rq=0)
    def _init_connection(extended):
        assert extended is True
        count['init'] += 1
    peer._init_connection = _init_connection

    # Stub _start_incoming_connect_timer
    def _start_incoming_connect_timer():
        count['start_timer'] += 1
    peer._start_incoming_connect_timer = _start_incoming_connect_timer

    # Hook connection request event
    def _on_conn_rq(**kwargs):
        assert kwargs == dict(peer=peer)
        count['conn_rq'] += 1
    station.connection_request.connect(_on_conn_rq)

    peer._on_receive_sabm(
        AX25SetAsyncBalancedModeExtendedFrame(
            destination=AX25Address('VK4MSL-1'),
            source=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB')
        )
    )

    assert peer._protocol == AX25Version.AX25_22


def test_on_receive_sabme_ax25_20_station():
    """
    Test we reject SABME if station is in AX.25 2.0 mode
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Set AX.25 2.0 mode on the station
    station._protocol = AX25Version.AX25_20

    # Stub _send_frmr
    frmr = []
    def _send_frmr(frame, **kwargs):
        frmr.append((frame, kwargs))
    peer._send_frmr = _send_frmr

    # Stub _init_connection
    def _init_connection(extended):
        assert False, 'Should not have been called'
    peer._init_connection = _init_connection

    # Stub _start_incoming_connect_timer
    def _start_incoming_connect_timer():
        assert False, 'Should not have been called'
    peer._start_incoming_connect_timer = _start_incoming_connect_timer

    # Hook connection request event
    def _on_conn_rq(**kwargs):
        assert False, 'Should not have been called'
    station.connection_request.connect(_on_conn_rq)

    frame = AX25SetAsyncBalancedModeExtendedFrame(
        destination=AX25Address('VK4MSL-1'),
        source=AX25Address('VK4MSL'),
        repeaters=AX25Path('VK4RZB')
    )
    peer._on_receive_sabm(frame)

    assert frmr == [(frame, dict(w=True))]


def test_on_receive_sabme_ax25_20_peer():
    """
    Test we reject SABME if peer not in AX.25 2.2 mode
    """
    station = DummyStation(AX25Address('VK4MSL', ssid=1))
    peer = TestingAX25Peer(
            station=station,
            address=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB'),
            locked_path=True
    )

    # Assume the peer runs AX.25 2.0
    peer._protocol = AX25Version.AX25_20

    # Stub _send_dm
    count = dict(send_dm=0)
    def _send_dm():
        count['send_dm'] += 1
    peer._send_dm = _send_dm

    # Stub _init_connection
    def _init_connection(extended):
        assert False, 'Should not have been called'
    peer._init_connection = _init_connection

    # Stub _start_incoming_connect_timer
    def _start_incoming_connect_timer():
        assert False, 'Should not have been called'
    peer._start_incoming_connect_timer = _start_incoming_connect_timer

    # Hook connection request event
    def _on_conn_rq(**kwargs):
        assert False, 'Should not have been called'
    station.connection_request.connect(_on_conn_rq)

    peer._on_receive_sabm(
        AX25SetAsyncBalancedModeExtendedFrame(
            destination=AX25Address('VK4MSL-1'),
            source=AX25Address('VK4MSL'),
            repeaters=AX25Path('VK4RZB')
        )
    )

    assert count == dict(send_dm=1)
