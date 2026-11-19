"""Mock ESP32 hardware device for Smart Load Protection Panel.

MANDATORY RULES:
1. All data published is labeled SIMULATED (Zero 230 V AC risk).
2. Follows contract §5-9 (docs/mqtt_contract.md).
3. Subscribes to panel/{DEVICE_ID}/cmd.
4. Publishes real ACKs to panel/{DEVICE_ID}/ack matching backend CommandAckIn schema.
5. Publishes 1 Hz synthetic telemetry to keep dashboard active during tests.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import os
import uuid
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MOCK-ESP32] %(levelname)s: %(message)s")
logger = logging.getLogger("mock_esp32")


class MockEsp32Device:
    """Simulates an ESP32 panel controller over MQTT."""

    def __init__(
        self,
        device_id: str = "PANEL-0001",
        host: str = "127.0.0.1",
        port: int = 1883,
        ack_delay_s: float = 0.05,
    ) -> None:
        self.device_id = device_id
        self.host = host
        self.port = port
        self.ack_delay_s = ack_delay_s

        # Channel states: CH1 = Mechanical Relay (Active-LOW), CH2 = SSR-40DA (Active-HIGH)
        self.channel_states: Dict[int, Dict[str, Any]] = {
            1: {"relay": False, "state": "OFF", "voltage": 230.2, "current": 0.0, "power": 0.0, "pf": 0.85, "f": 50.0, "energy": 0.125},
            2: {"relay": False, "state": "OFF", "voltage": 230.1, "current": 0.0, "power": 0.0, "pf": 0.99, "f": 50.0, "energy": 0.045},
        }

        self.client: Optional[mqtt.Client] = None
        self._running = False
        self._telemetry_thread: Optional[threading.Thread] = None
        self.received_commands: list[dict[str, Any]] = []
        self.published_acks: list[dict[str, Any]] = []
        self.on_cmd_callback: Optional[Callable[[dict[str, Any]], None]] = None

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        rc_code = getattr(rc, "value", rc)
        if rc_code == 0:
            logger.info("Connected to MQTT broker at %s:%d as %s", self.host, self.port, self.device_id)
            cmd_topic = f"panel/{self.device_id}/cmd"
            client.subscribe(cmd_topic, qos=1)
            logger.info("Subscribed to command topic: %s", cmd_topic)

            # Birth status
            status_payload = json.dumps({
                "schema": 1,
                "online": True,
                "fw_version": "1.0.0-MOCK",
                "simulated": True,
                "ts": int(time.time()),
            })
            client.publish(f"panel/{self.device_id}/status", status_payload, qos=1, retain=True)
        else:
            logger.error("Failed to connect to MQTT broker, rc=%s", rc)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.info("Received command message on %s: %s", msg.topic, payload)
            self.received_commands.append(payload)

            if self.on_cmd_callback:
                self.on_cmd_callback(payload)

            # Process command
            cmd_id = payload.get("cmd_id")
            ch = int(payload.get("ch", 1))
            action = str(payload.get("action", "")).upper()
            expires_at = payload.get("expires_at")

            now_ts = int(time.time())
            if expires_at and now_ts > expires_at:
                logger.warning("Command %s arrived expired (now=%d, exp=%d)", cmd_id, now_ts, expires_at)
                self._send_ack(cmd_id, ch, result="FAILED", reason="COMMAND_EXPIRED")
                return

            if ch not in self.channel_states:
                logger.warning("Command received for invalid channel: %d", ch)
                self._send_ack(cmd_id, ch, result="REJECTED", reason="INVALID_CHANNEL")
                return

            if action in ("ON", "OFF"):
                # Simulate hardware actuation delay
                if self.ack_delay_s > 0:
                    time.sleep(self.ack_delay_s)

                target_relay = (action == "ON")
                self.channel_states[ch]["relay"] = target_relay
                self.channel_states[ch]["state"] = "RUNNING" if target_relay else "OFF"
                if target_relay:
                    if ch == 1:
                        self.channel_states[ch]["current"] = 0.95
                        self.channel_states[ch]["power"] = 125.0
                    else:
                        self.channel_states[ch]["current"] = 1.80
                        self.channel_states[ch]["power"] = 414.0
                else:
                    self.channel_states[ch]["current"] = 0.0
                    self.channel_states[ch]["power"] = 0.0

                logger.info("Channel %d relay actuated to %s (result=DONE)", ch, action)
                self._send_ack(cmd_id, ch, result="DONE", reason="OK", relay=target_relay, state=self.channel_states[ch]["state"])

            elif action == "RESET":
                self.channel_states[1]["relay"] = False
                self.channel_states[1]["state"] = "OFF"
                self.channel_states[2]["relay"] = False
                self.channel_states[2]["state"] = "OFF"
                self._send_ack(cmd_id, ch, result="DONE", reason="MANUAL_RESET", relay=False, state="OFF")
            else:
                self._send_ack(cmd_id, ch, result="REJECTED", reason="UNKNOWN_ACTION")

        except Exception as exc:
            logger.exception("Error processing command payload: %s", exc)

    def _send_ack(
        self,
        cmd_id: str,
        ch: int,
        result: str,
        reason: str = "OK",
        relay: Optional[bool] = None,
        state: Optional[str] = None,
    ) -> None:
        if relay is None:
            relay = self.channel_states.get(ch, {}).get("relay", False)
        if state is None:
            state = self.channel_states.get(ch, {}).get("state", "OFF")

        # Ensure cmd_id is always present for backend validation
        if not cmd_id:
            import uuid
            cmd_id = str(uuid.uuid4())
            logger.warning("Command ID was missing, generated: %s", cmd_id)

        ack_payload = {
            "schema": 1,
            "cmd_id": cmd_id,
            "ch": ch,
            "result": result,
            "reason": reason,
            "relay": relay,
            "state": state,
            "ts": int(time.time()),
            "simulated": True,
        }
        topic = f"panel/{self.device_id}/ack"
        self.client.publish(topic, json.dumps(ack_payload), qos=1)
        self.published_acks.append(ack_payload)
        logger.info("Published ACK on %s: result=%s, relay=%s, cmd_id=%s", topic, result, relay, cmd_id)

    def _telemetry_loop(self) -> None:
        """Periodically publishes 1 Hz telemetry to keep backend and UI alive."""
        while self._running:
            try:
                now_ts = time.time()  # Use float timestamp with millisecond precision
                for ch in (1, 2):
                    c = self.channel_states[ch]
                    if c["relay"]:
                        c["energy"] += (c["power"] * 1.0) / (3600.0 * 1000.0)

                    telem = {
                        "schema": 1,
                        "ts": round(now_ts, 3),  # Millisecond precision
                        "ch": ch,
                        "v": round(c["voltage"], 2),
                        "i": round(c["current"], 3),
                        "p": round(c["power"], 2),
                        "e_kwh": round(c["energy"], 4),
                        "pf": round(c["pf"], 3),
                        "f": round(c["f"], 2),
                        "relay": c["relay"],
                        "state": c["state"],
                        "buffered": False,
                        "clock_synced": True,
                        "simulated": True,
                    }
                    topic = f"panel/{self.device_id}/telemetry/{ch}"
                    self.client.publish(topic, json.dumps(telem), qos=1)

                time.sleep(1.0)
            except Exception as exc:
                logger.debug("Telemetry loop exception: %s", exc)

    def start(self, publish_telemetry: bool = True) -> None:
        """Start the mock device MQTT client."""
        import os
        client_id = f"mock-esp32-{self.device_id}-{os.getpid()}-{int(time.time())}"
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        # LWT offline notice
        lwt_payload = json.dumps({"schema": 1, "online": False, "simulated": True})
        self.client.will_set(f"panel/{self.device_id}/status", lwt_payload, qos=1, retain=True)

        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        self._running = True

        if publish_telemetry:
            self._telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
            self._telemetry_thread.start()

        logger.info("Mock ESP32 device %s started.", self.device_id)

    def stop(self) -> None:
        """Stop the mock device cleanly."""
        self._running = False
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        logger.info("Mock ESP32 device %s stopped.", self.device_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock ESP32 controller simulator")
    parser.add_argument("--device-id", default="PANEL-0001", help="Device ID")
    parser.add_argument("--host", default="127.0.0.1", help="MQTT Broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker port")
    parser.add_argument("--no-telemetry", action="store_true", help="Disable background telemetry")
    args = parser.parse_args()

    mock = MockEsp32Device(device_id=args.device_id, host=args.host, port=args.port)
    mock.start(publish_telemetry=not args.no_telemetry)
    print(f"[MOCK-ESP32] Running for {args.device_id}. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mock.stop()
        print("\n[MOCK-ESP32] Stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())