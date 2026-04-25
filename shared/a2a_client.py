"""Shared A2A client utilities."""
from uuid import uuid4

import httpx
from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types import Message, MessageSendParams, Part, Role, Task, TextPart
from a2a.utils import get_message_text


async def send_text(http: httpx.AsyncClient, url: str, text: str) -> str:
    """Send a text message to an A2A agent and return the response text."""
    transport = JsonRpcTransport(http, url=url)
    params = MessageSendParams(
        message=Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id=str(uuid4()),
        )
    )
    result = await transport.send_message(params)
    if isinstance(result, Task):
        if result.status and result.status.message:
            return get_message_text(result.status.message)
        return ""
    if isinstance(result, Message):
        return get_message_text(result)
    return str(result)


__all__ = ["send_text"]
