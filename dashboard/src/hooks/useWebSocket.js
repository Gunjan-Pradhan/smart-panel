import { useEffect, useRef, useState, useCallback } from "react";
import { api, getToken } from "../api/client.js";

function getWebSocketUrl(deviceId) {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${protocol}//${host}/ws/live/${deviceId}`;
}

/**
 * Custom hook for managing WebSocket connection to FastAPI Live Pipeline
 * with fallback to Node-RED or simulated data.
 *
 * Returns { telemetry, connected, connectionText, sendCommand, setDeviceId, deviceId }.
 */
export function useWebSocket(initialDeviceId = "PANEL-0001") {
  const [deviceId, setDeviceId] = useState(initialDeviceId);
  const [telemetry, setTelemetry] = useState({});
  const [connected, setConnected] = useState(false);
  const [connectionText, setConnectionText] = useState("Connecting to FastAPI live stream...");
  const socketRef = useRef(null);

  useEffect(() => {
    let disposed = false;
    let retryTimer;

    function connect() {
      if (disposed) return;
      const targetUrl = getWebSocketUrl(deviceId);
      setConnectionText(`Connecting to live stream (${deviceId})...`);

      const ws = new WebSocket(targetUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setConnectionText(`Connected to Live Stream (${deviceId})`);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          // 1. Contract v1 telemetry broadcast from FastAPI live pipeline
          if (msg.type === "telemetry" && (msg.ch === 1 || msg.ch === 2)) {
            const chKey = msg.ch === 1 ? "circuit1" : "circuit2";
            const v = Number(msg.v) || 0;
            const i = Number(msg.i) || 0;
            const p = Number(msg.p) || 0;
            const s = Number(msg.s) || Math.round(v * i * 100) / 100;
            const q = Number(msg.q) || Math.round(Math.sqrt(Math.max(0, s * s - p * p)) * 100) / 100;
            const pf = Number(msg.pf) || 0;
            const relayOn = Boolean(msg.relay);

            setTelemetry((prev) => ({
              ...prev,
              uptime_s: msg.ts ? Math.floor(Date.now() / 1000 - msg.ts) : prev.uptime_s || 0,
              [chKey]: {
                ...(prev[chKey] || {}),
                valid: true,
                voltage_V: v,
                current_A: i,
                active_power_W: p,
                active_power_kW: Math.round((p / 1000) * 10000) / 10000,
                apparent_power_VA: s,
                reactive_power_var: q,
                frequency_Hz: Number(msg.f) || 50.0,
                power_factor_meter: pf,
                power_factor_calculated: s > 0 ? Math.round((p / s) * 1000) / 1000 : pf,
                energy_kWh: Number(msg.e_kwh) || 0,
                relay_on: relayOn,
                "relay/state": relayOn ? "ON" : "OFF",
                relay_mode: msg.state || "MANUAL",
                supply_status: v >= 180 && v <= 265 ? "NORMAL" : "OUT OF RANGE",
                fault: msg.state === "FAULT_TRIP" || msg.state === "LOCKOUT",
                over_voltage: v > 265,
                under_voltage: v < 180,
                over_current: msg.ch === 1 ? i > 16.0 : i > 10.0,
                last_updated: new Date().toLocaleTimeString(),
              },
            }));
          }
          // 2. Legacy / Node-RED combined object
          else if (msg.circuit1 || msg.circuit2) {
            setTelemetry(msg);
          }
        } catch (err) {
          console.error("Invalid telemetry packet:", err);
        }
      };

      ws.onerror = () => {
        setConnectionText("Live stream offline (using cached/REST)");
      };

      ws.onclose = () => {
        if (socketRef.current === ws) socketRef.current = null;
        setConnected(false);
        setConnectionText("Stream disconnected — reconnecting...");
        if (!disposed) retryTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      const ws = socketRef.current;
      socketRef.current = null;
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, [deviceId]);

  // Dispatch command: use FastAPI REST endpoint for audit logging & real ack tracking
  const sendCommand = useCallback(
    async (circuit, action) => {
      // Normalise action to "ON" or "OFF"
      const normalizedAction =
        typeof action === "string" ? action.toUpperCase() : action ? "ON" : "OFF";

      // If user has JWT token, route through FastAPI REST endpoint
      if (getToken()) {
        try {
          const result = await api.sendCommand(deviceId, Number(circuit), normalizedAction);
          // Optimistically update local state
          const chKey = Number(circuit) === 1 ? "circuit1" : "circuit2";
          setTelemetry((prev) => ({
            ...prev,
            [chKey]: {
              ...(prev[chKey] || {}),
              relay_on: normalizedAction === "ON",
              "relay/state": normalizedAction,
            },
          }));
          return result;
        } catch (err) {
          alert(`Command dispatch error: ${err.message}`);
          return null;
        }
      }

      // Fallback: send directly through WebSocket if not authenticated
      const ws = socketRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        alert("Please log in to dispatch commands or ensure live stream is connected.");
        return;
      }
      ws.send(JSON.stringify({ circuit: Number(circuit), relay: normalizedAction }));
    },
    [deviceId]
  );

  return { telemetry, connected, connectionText, sendCommand, setDeviceId, deviceId };
}
