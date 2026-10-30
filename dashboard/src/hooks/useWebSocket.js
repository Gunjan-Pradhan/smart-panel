import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL =
  import.meta.env.VITE_WS_URL || "ws://localhost:1880/ws/energy";

/**
 * Custom hook for managing WebSocket connection to Node-RED.
 * Returns { telemetry, connected, connectionText, sendCommand }.
 */
export function useWebSocket() {
  const [telemetry, setTelemetry] = useState({});
  const [connected, setConnected] = useState(false);
  const [connectionText, setConnectionText] = useState("Connecting...");
  const socketRef = useRef(null);

  useEffect(() => {
    let disposed = false;
    let retryTimer;

    function connect() {
      if (disposed) return;
      setConnectionText("Connecting...");

      const ws = new WebSocket(WS_URL);
      socketRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setConnectionText("Connected to Node-RED");
      };

      ws.onmessage = (event) => {
        try {
          setTelemetry(JSON.parse(event.data));
        } catch (err) {
          console.error("Invalid telemetry:", err);
        }
      };

      ws.onerror = () => setConnectionText("Connection error");

      ws.onclose = () => {
        if (socketRef.current === ws) socketRef.current = null;
        setConnected(false);
        setConnectionText("Disconnected — reconnecting");
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
  }, []);

  const sendCommand = useCallback((circuit, relay) => {
    const ws = socketRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      alert("Node-RED is not connected.");
      return;
    }
    ws.send(JSON.stringify({ circuit, relay }));
  }, []);

  return { telemetry, connected, connectionText, sendCommand };
}

