"""MQTT broker smoke test for the Smart Load Protection Panel.

Purpose
-------
Prove that a client can connect to the local Mosquitto broker, subscribe to a
topic, publish a message and receive it back. This is an infrastructure test,
not a test of the application message contract (that arrives with the
simulator and backend in later phases).

Usage (Windows, from the project root, with the broker running):

    .\\.venv\\Scripts\\python.exe .\\scripts\\mqtt_smoke_test.py

Environment variables (all optional):
    MQTT_HOST           broker hostname (default 127.0.0.1)
    MQTT_PORT           broker TCP port (default 1883)
    MQTT_SMOKE_TIMEOUT  seconds to wait for the round trip (default 5)

Exit codes:
    0  round trip succeeded
    1  connection, subscription, publish or receive failed
"""

from __future__ import annotations

import os
import sys
import threading
import uuid

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1883"))
TIMEOUT = float(os.environ.get("MQTT_SMOKE_TIMEOUT", "5"))
TOPIC_ROOT = "panel/_smoke"


def run_smoke_test() -> int:
    """Run one publish/subscribe round trip and return a process exit code."""
    token = uuid.uuid4().hex
    topic = f"{TOPIC_ROOT}/{token}"
    payload = f'{{"token":"{token}"}}'

    finished = threading.Event()
    state: dict[str, object] = {
        "error": None,
        "received": None,
    }

    def on_connect(
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            state["error"] = f"broker refused connection: {reason_code}"
            finished.set()
            return
        client.subscribe(topic, qos=1)

    def on_subscribe(
        client: mqtt.Client,
        userdata: object,
        mid: int,
        reason_codes: list[mqtt.ReasonCode],
        properties: mqtt.Properties | None,
    ) -> None:
        result = client.publish(topic, payload, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            state["error"] = f"publish failed with rc={result.rc}"
            finished.set()

    def on_message(
        client: mqtt.Client,
        userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        state["received"] = message.payload.decode("utf-8", errors="replace")
        finished.set()

    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=f"smart-panel-smoke-{token[:8]}",
    )
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    print(f"Connecting to {HOST}:{PORT} ...")
    try:
        client.connect(HOST, PORT, keepalive=10)
    except OSError as exc:
        print(f"FAIL: cannot reach broker at {HOST}:{PORT}: {exc}")
        return 1

    client.loop_start()
    try:
        if not finished.wait(TIMEOUT):
            print(f"FAIL: no response within {TIMEOUT}s (topic {topic})")
            return 1

        error = state["error"]
        if error:
            print(f"FAIL: {error}")
            return 1

        if state["received"] != payload:
            print(f"FAIL: payload mismatch, received {state['received']!r}")
            return 1

        print(f"PASS: connected to {HOST}:{PORT}")
        print(f"PASS: QoS 1 round trip on {topic}")
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(run_smoke_test())
