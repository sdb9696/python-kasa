"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import contextlib
import errno
import logging
import struct
from pprint import pformat as pf
from typing import Dict, Generator, Optional, Union

from .exceptions import SmartDeviceException
from .json import dumps as json_dumps
from .json import loads as json_loads

_LOGGER = logging.getLogger(__name__)
_NO_RETRY_ERRORS = {errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED}


class TPLinkProtocol:
    """Base class for all TP-Link Smart Home communication."""

    DEFAULT_TIMEOUT = 5

    def __init__(self, host: str, *, port: Optional[int] = None) -> None:
        """Create a protocol object."""
        self.host = host
        self.port = port
        self.timeout = self.DEFAULT_TIMEOUT

    @staticmethod
    def get_discovery_targets(targetip: str = "255.255.255.255"):
        """Return a list of discovery targets for the protocol.  Abstract method to be overriden."""
        raise SmartDeviceException("get_discovery_targets should be overridden")

    @staticmethod
    def get_discovery_payload():
        """Get discovery payload for the protocol.  Abstract method to be overriden."""
        raise SmartDeviceException("get_discovery_payload should be overridden")

    @staticmethod
    def try_get_discovery_info(port, data):
        """Try get the discovery info from supplied data after a discovery broadcast has resulted in a received datagram."""
        raise SmartDeviceException("try_get_discovery_info should be overridden")

    async def try_query_discovery_info(self):
        """Try to query a device for discovery info."""
        raise SmartDeviceException("try_query_discovery_info should be overridden")

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device for the protocol.  Abstract method to be overriden."""
        raise SmartDeviceException("query should be overridden")

    async def close(self) -> None:
        """Close the protocol.  Abstract method to be overriden."""
        raise SmartDeviceException("close should be overridden")


class TPLinkSmartHomeProtocol(TPLinkProtocol):
    """Implementation of the TP-Link Smart Home protocol."""

    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999
    BLOCK_SIZE = 4
    DISCOVERY_QUERY = {
        "system": {"get_sysinfo": None},
    }

    def __init__(self, host: str, *, port: Optional[int] = None) -> None:
        """Create a protocol object."""
        super().__init__(host=host, port=port or self.DEFAULT_PORT)

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.query_lock: Optional[asyncio.Lock] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    @staticmethod
    def get_discovery_targets(targetip: str = "255.255.255.255"):
        """Return a list of discovery targets for this protocol."""
        return [(targetip, TPLinkSmartHomeProtocol.DEFAULT_PORT)]

    @staticmethod
    def get_discovery_payload():
        """Get discovery payload for this protocol."""
        req = json_dumps(TPLinkSmartHomeProtocol.DISCOVERY_QUERY)
        encrypted_req = TPLinkSmartHomeProtocol.encrypt(req)
        return encrypted_req[4:]

    @staticmethod
    def try_get_discovery_info(port, data):
        """Try to get discovery info which will return info if the ports match and we can decrypt the data or None otherwise."""
        if port == TPLinkSmartHomeProtocol.DEFAULT_PORT:
            try:
                info = json_loads(TPLinkSmartHomeProtocol.decrypt(data))
                if "system" in info and "get_sysinfo" in info["system"]:
                    return info
            except Exception as ex:
                print(ex)
                return None
        else:
            return None

    async def try_query_discovery_info(self):
        """Return discovery info if the ports match and we can decrypt the data."""
        try:
            info = await self.query(TPLinkSmartHomeProtocol.DISCOVERY_QUERY)
            return info
        except SmartDeviceException:
            _LOGGER.debug(
                "Unable to query discovery for %s with TPLinkSmartHomeProtocol",
                self.host,
            )
            return None

    def _detect_event_loop_change(self) -> None:
        """Check if this object has been reused betwen event loops."""
        loop = asyncio.get_running_loop()
        if not self.loop:
            self.loop = loop
        elif self.loop != loop:
            _LOGGER.warning("Detected protocol reuse between different event loop")
            self._reset()

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param str host: host name or ip address of the device
        :param request: command to send to the device (can be either dict or
        json string)
        :param retry_count: how many retries to do in case of failure
        :return: response dict
        """
        self._detect_event_loop_change()

        if not self.query_lock:
            self.query_lock = asyncio.Lock()

        if isinstance(request, dict):
            request = json_dumps(request)
            assert isinstance(request, str)

        async with self.query_lock:
            return await self._query(request, retry_count, self.timeout)

    async def _connect(self, timeout: int) -> None:
        """Try to connect or reconnect to the device."""
        if self.writer:
            return
        self.reader = self.writer = None
        task = asyncio.open_connection(self.host, self.port)
        self.reader, self.writer = await asyncio.wait_for(task, timeout=timeout)

    async def _execute_query(self, request: str) -> Dict:
        """Execute a query on the device and wait for the response."""
        assert self.writer is not None
        assert self.reader is not None
        debug_log = _LOGGER.isEnabledFor(logging.DEBUG)

        if debug_log:
            _LOGGER.debug("%s >> %s", self.host, request)
        self.writer.write(TPLinkSmartHomeProtocol.encrypt(request))
        await self.writer.drain()

        packed_block_size = await self.reader.readexactly(self.BLOCK_SIZE)
        length = struct.unpack(">I", packed_block_size)[0]

        buffer = await self.reader.readexactly(length)
        response = TPLinkSmartHomeProtocol.decrypt(buffer)
        json_payload = json_loads(response)
        if debug_log:
            _LOGGER.debug("%s << %s", self.host, pf(json_payload))

        return json_payload

    async def close(self) -> None:
        """Close the connection."""
        writer = self.writer
        self.reader = self.writer = None
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _reset(self) -> None:
        """Clear any varibles that should not survive between loops."""
        self.reader = self.writer = self.loop = self.query_lock = None

    async def _query(self, request: str, retry_count: int, timeout: int) -> Dict:
        """Try to query a device."""
        #
        # Most of the time we will already be connected if the device is online
        # and the connect call will do nothing and return right away
        #
        # However, if we get an unrecoverable error (_NO_RETRY_ERRORS and ConnectionRefusedError)
        # we do not want to keep trying since many connection open/close operations
        # in the same time frame can block the event loop. This is especially
        # import when there are multiple tplink devices being polled.
        #
        for retry in range(retry_count + 1):
            try:
                await self._connect(timeout)
            except ConnectionRefusedError as ex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}:{self.port}: {ex}"
                )
            except OSError as ex:
                await self.close()
                if ex.errno in _NO_RETRY_ERRORS or retry >= retry_count:
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}:{self.port}: {ex}"
                    )
                continue
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}:{self.port}: {ex}"
                    )
                continue

            try:
                assert self.reader is not None
                assert self.writer is not None
                return await asyncio.wait_for(
                    self._execute_query(request), timeout=timeout
                )
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to query the device {self.host}:{self.port}: {ex}"
                    ) from ex

                _LOGGER.debug(
                    "Unable to query the device %s, retrying: %s", self.host, ex
                )

        # make mypy happy, this should never be reached..
        await self.close()
        raise SmartDeviceException("Query reached somehow to unreachable")

    def __del__(self) -> None:
        if self.writer and self.loop and self.loop.is_running():
            # Since __del__ will be called when python does
            # garbage collection is can happen in the event loop thread
            # or in another thread so we need to make sure the call to
            # close is called safely with call_soon_threadsafe
            self.loop.call_soon_threadsafe(self.writer.close)
        self._reset()

    @staticmethod
    def _xor_payload(unencrypted: bytes) -> Generator[int, None, None]:
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        for unencryptedbyte in unencrypted:
            key = key ^ unencryptedbyte
            yield key

    @staticmethod
    def encrypt(request: str) -> bytes:
        """Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext to be send over wire, in bytes
        """
        plainbytes = request.encode()
        return struct.pack(">I", len(plainbytes)) + bytes(
            TPLinkSmartHomeProtocol._xor_payload(plainbytes)
        )

    @staticmethod
    def _xor_encrypted_payload(ciphertext: bytes) -> Generator[int, None, None]:
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        for cipherbyte in ciphertext:
            plainbyte = key ^ cipherbyte
            key = cipherbyte
            yield plainbyte

    @staticmethod
    def decrypt(ciphertext: bytes) -> str:
        """Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        return bytes(
            TPLinkSmartHomeProtocol._xor_encrypted_payload(ciphertext)
        ).decode()


# Try to load the kasa_crypt module and if it is available
try:
    from kasa_crypt import decrypt, encrypt

    TPLinkSmartHomeProtocol.decrypt = decrypt  # type: ignore[method-assign]
    TPLinkSmartHomeProtocol.encrypt = encrypt  # type: ignore[method-assign]
except ImportError:
    pass
