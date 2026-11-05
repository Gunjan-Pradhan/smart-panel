/**
 * EventsPanel: Displays real-time protection events, anomaly detections,
 * and hardware trip logs for Channel 1 & 2.
 */
import { useState, useEffect } from "react";
import { api } from "../api/client.js";

export default function EventsPanel() {
  const [channel, setChannel] = useState(1);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function fetchEvents(ch) {
    try {
      setLoading(true);
      const data = await api.getAnomalyEvents(ch);
      setEvents(data);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchEvents(channel);
  }, [channel]);

  return (
    <section className="events-panel">
      <div className="panel-header-row">
        <div>
          <h3>🛡️ Protection Events & Anomaly Audit Log</h3>
          <p className="subtext">
            Historical fault trips, safe limits violations, and AI-flagged electrical anomalies.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className={`tab ${channel === 1 ? "active" : ""}`}
            onClick={() => setChannel(1)}
          >
            Channel 1 (Motor)
          </button>
          <button
            className={`tab ${channel === 2 ? "active" : ""}`}
            onClick={() => setChannel(2)}
          >
            Channel 2 (Sensitive)
          </button>
          <button className="ai-btn" onClick={() => fetchEvents(channel)}>
            ↻
          </button>
        </div>
      </div>

      {error && <p className="fault">{error}</p>}

      {events.length === 0 && !loading && !error && (
        <p className="subtext" style={{ padding: "1rem" }}>
          No anomalies or trip events recorded for Channel {channel}. All systems normal.
        </p>
      )}

      <div className="events-list">
        {events.map((ev) => {
          const isCritical = ev.severity === "critical";
          const isWarning = ev.severity === "warning";
          const badgeClass = isCritical ? "fault" : isWarning ? "warning" : "normal";

          return (
            <div className={`event-card ${badgeClass}`} key={ev.id}>
              <div className="event-header">
                <div>
                  <span className={`badge ${badgeClass}`}>{ev.severity.toUpperCase()}</span>
                  <strong>{ev.event_type}</strong>
                </div>
                <span className="subtext">{new Date(ev.timestamp).toLocaleString()}</span>
              </div>

              <p className="event-message">{ev.message}</p>

              {ev.flags && ev.flags.length > 0 && (
                <div className="event-flags">
                  {ev.flags.map((flag, idx) => (
                    <span className="flag-pill" key={idx}>
                      {flag}
                    </span>
                  ))}
                </div>
              )}

              {ev.metrics && (
                <div className="event-metrics">
                  {ev.metrics.z_voltage != null && (
                    <span>Z(V): {ev.metrics.z_voltage}</span>
                  )}
                  {ev.metrics.z_current != null && (
                    <span>Z(I): {ev.metrics.z_current}</span>
                  )}
                  {ev.metrics.z_power != null && (
                    <span>Z(P): {ev.metrics.z_power}</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

