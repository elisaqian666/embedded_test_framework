"""Purpose: Provide product-independent WebSocket communication."""

import copy
import logging
import queue

from ws4py.client.threadedclient import WebSocketClient
from ws4py.messaging import TextMessage

import embedded_framework.lib.timeout


class _ThreadedWebSocket(WebSocketClient):
    def __init__(self, url, protocols=None):
        if protocols is None:
            protocols = []
        super().__init__(url, protocols=protocols, heartbeat_freq=10.0)
        self.messages = queue.Queue()

    def received_message(self, m):
        """the received message is"""
        self.messages.put(copy.deepcopy(m))


class WebSocketClient(object):
    """
    WebSocketClient connects remotely to a Websocket server and allow to send and receive files.
    """

    def __init__(self, ws):
        """
        Constructs a WebSocketClient"""
        self.ws = ws
        self.url = ws.url
        self.logger = logging.getLogger("websocket")

    @staticmethod
    def __protocol__():
        return "websocket"

    def __str__(self):
        return f"websocket engine with url {self.ws.url}"

    def __re_init__(self):
        """
        re initializes the engine
        """
        ws = wait_for_web_socket_creation(self.url)
        if ws:
            self.ws.close()
            self.ws = ws

    def send(self, message):
        """
        Send a message

        :param message: string message to send
        """
        self.logger.debug("Send message %s", message)
        if self.ws.terminated:
            self.__re_init__()
        self.ws.send(message)

    def receive(self, block=True, timeout=-1) -> TextMessage:
        """
        Receive a text message, you can use ".data" to make it a string

        :param block: If True, wait for incoming messages. If False, only look at unprocessed cached messages
        :param timeout:
        :return: Returns received message if successful, otherwise returns False
        :rtype: ws4py.messaging.TextMessage
        """
        if self.ws.terminated:
            self.__re_init__()
        try:
            message = self.ws.messages.get(block, None if timeout == -1 else timeout)
            self.logger.debug("Received message %s", message)
            return message
        except queue.Empty:
            return False

    def get_pending_messages_count(self):
        """
        Get the number of received messages that are not processed yet

        :return: The number of unprocessed received messages
        """
        return self.ws.messages.qsize()

    def close(self):
        """closes the socket"""
        self.ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def wait_for_web_socket_creation(url):
    """wait until a websocket is created"""
    timeout_param = embedded_framework.lib.timeout.TimeoutParams(
        timeout=150,
        timeout_msg=f"Not able to connect to websocket on {url}",
        no_spam_sleep=1,
    )
    return embedded_framework.lib.timeout.wait_no_exception_timeout(create_and_connect_to_websocket, timeout_param, Exception, url)


def create_and_connect_to_websocket(url):
    """create a websocket and connect to it"""
    ws = _ThreadedWebSocket(url)
    logger = logging.getLogger("websocket")
    logger.debug("THREAD? {}")
    ws.opened()
    ws.connect()
    return ws


def make_websocket_client(url):
    """
    make a websocket engine

    :param url: the url to create a websocket to
    :return: websocket engine
    :rtype: WebSocketClient
    """
    logging.getLogger("websocket").info("creating websocket engine on url %s", url)
    ws = wait_for_web_socket_creation(url)
    return WebSocketClient(ws)


