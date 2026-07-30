"""Encode Python-side protocol payloads (snapshots and captured op
messages) into JSON-safe structures for the browser harness: memoryviews
become {"__b64__": ...} markers, decoded to DataViews on the JS side."""

import base64


def _b64(buffer: memoryview) -> str:
    return base64.b64encode(bytes(buffer)).decode()


def encode_binary(node):
    if isinstance(node, memoryview):
        return {"__b64__": _b64(node)}
    if isinstance(node, dict):
        return {key: encode_binary(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [encode_binary(value) for value in node]
    return node


def snapshot_payload(renderer):
    """The renderer's current full snapshot (delta ops folded in) in
    harness wire form."""
    return encode_binary(renderer.get_state()["_scene_state"])


def messages_payload(sent):
    """Captured ``renderer.send`` messages in harness wire form."""
    return [
        {
            "content": encode_binary(message["content"]),
            "buffers": [_b64(b) for b in (message["buffers"] or [])],
        }
        for message in sent
    ]
