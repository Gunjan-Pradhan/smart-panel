/**
 * AIPanel: unified panel for AI-powered features per channel.
 * - Learning session control
 * - Load recognition status
 * - Mode suggestions with Accept button
 * - Anomaly detection status
 */
import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client.js";
import { fmt } from "./Metric.jsx";

function SeverityBadge({ severity }) {
  const cls =
    severity === "critical"
      ? "fault"
      : severity === "warning"
      ? "warning"
      : "normal";
  return <strong className={cls}>{severity.toUpperCase()}</strong>;
}

function LearningSection({ channel }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const s = await api.getLearningStatus(channel);
      setSession(s);
    } catch {
      /* no active session */
    }
  }, [channel]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function startLearning() {
    setError("");
    setLoading(true);
    try {
      const s = await api.startLearning(channel, true);
      setSession(s);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function cancelLearning() {
    if (!session) return;
    try {
      await api.cancelLearning(session.id);
      setSession(null);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="ai-section">
      <h4>🎓 Load Learning</h4>
      {error && <p className="fault">{error}</p>}
      {session ? (
        <div className="ai-info-grid">
          <div className="ai-info-item">
            <span>Status</span>
            <strong className={session.status === "learning" ? "warning" : "normal"}>
              {session.status.toUpperCase()}
            </strong>
          </div>
          <div className="ai-info-item">
            <span>Valid Samples</span>
            <strong>{session.valid_count}</strong>
          </div>
          <div className="ai-info-item">
            <span>Excluded</span>
            <strong>{session.excluded_count}</strong>
          </div>
          {session.status === "learning" && (
            <button className="cancel-btn" onClick={cancelLearning}>
              Cancel Session
            </button>
          )}
        </div>
      ) : (
        <div>
          <p className="subtext">No active session on this channel.</p>
          <button className="ai-btn" onClick={startLearning} disabled={loading}>
            {loading ? "Starting..." : "Start Learning Session"}
          </button>
        </div>
      )}
    </div>
  );
}

function RecognitionSection({ channel }) {
  const [latest, setLatest] = useState(null);

  useEffect(() => {
    api
      .getLatestRecognition(channel)
      .then(setLatest)
      .catch(() => {});
  }, [channel]);

  if (!latest) {
    return (
      <div className="ai-section">
        <h4>🔍 Load Recognition</h4>
        <p className="subtext">No recognition events yet.</p>
      </div>
    );
  }

  const stateClass =
    latest.state === "recognized"
      ? "normal"
      : latest.state === "ambiguous"
      ? "warning"
      : "fault";

  return (
    <div className="ai-section">
      <h4>🔍 Load Recognition</h4>
      <div className="ai-info-grid">
        <div className="ai-info-item">
          <span>Match State</span>
          <strong className={stateClass}>{latest.state.toUpperCase()}</strong>
        </div>
        <div className="ai-info-item">
          <span>Similarity</span>
          <strong>{fmt(latest.similarity_score, 1)}%</strong>
        </div>
        <div className="ai-info-item">
          <span>Feedback</span>
          <strong>{latest.user_feedback}</strong>
        </div>
      </div>
    </div>
  );
}

function SuggestionsSection({ channel }) {
  const [suggestions, setSuggestions] = useState([]);
  const [accepted, setAccepted] = useState({});

  useEffect(() => {
    api
      .getChannelSuggestions(channel)
      .then(setSuggestions)
      .catch(() => {});
  }, [channel]);

  async function handleAccept(id) {
    try {
      await api.acceptSuggestion(id);
      setAccepted((prev) => ({ ...prev, [id]: true }));
    } catch (err) {
      alert("Failed to accept: " + err.message);
    }
  }

  if (suggestions.length === 0) {
    return (
      <div className="ai-section">
        <h4>💡 Mode Suggestions</h4>
        <p className="subtext">No suggestions yet. Complete a learning session first.</p>
      </div>
    );
  }

  return (
    <div className="ai-section">
      <h4>💡 Mode Suggestions</h4>
      {suggestions.map((s) => (
        <div className="suggestion-card" key={s.id}>
          <div className="suggestion-header">
            <strong>{s.mode_name.toUpperCase()}</strong>
            <span className="eyebrow">{s.rule_id}</span>
          </div>
          <p className="suggestion-reason">{s.reason_text}</p>
          {accepted[s.id] ? (
            <span className="normal">✓ Accepted</span>
          ) : (
            <button className="ai-btn" onClick={() => handleAccept(s.id)}>
              Accept Suggestion
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function AnomalySection({ channel, liveData }) {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    api
      .getAnomalyEvents(channel)
      .then(setEvents)
      .catch(() => {});
  }, [channel]);

  return (
    <div className="ai-section">
      <h4>⚠️ Anomaly Detection</h4>
      {liveData && liveData.valid && (
        <div className="ai-info-grid">
          <div className="ai-info-item">
            <span>Live Voltage</span>
            <strong>{fmt(liveData.voltage_V, 1)} V</strong>
          </div>
          <div className="ai-info-item">
            <span>Live Current</span>
            <strong>{fmt(liveData.current_A, 3)} A</strong>
          </div>
          <div className="ai-info-item">
            <span>Live Power</span>
            <strong>{fmt(liveData.active_power_W, 1)} W</strong>
          </div>
        </div>
      )}
      {events.length > 0 && (
        <details className="parameter-section" open>
          <summary>Recent Anomaly Events ({events.length})</summary>
          <div className="fault-list">
            {events.slice(0, 5).map((ev) => (
              <div className="fault-item" key={ev.id}>
                <span>{ev.type.replace("anomaly_", "").replace(/_/g, " ")}</span>
                <SeverityBadge severity={ev.severity} />
              </div>
            ))}
          </div>
        </details>
      )}
      {events.length === 0 && (
        <p className="subtext normal">No anomaly events recorded.</p>
      )}
    </div>
  );
}

export default function AIPanel({ channel, liveData }) {
  return (
    <section className="ai-panel">
      <div className="ai-panel-heading">
        <p className="eyebrow">AI INTELLIGENCE</p>
        <h3>Channel {channel} — Smart Features</h3>
      </div>
      <LearningSection channel={channel} />
      <RecognitionSection channel={channel} />
      <SuggestionsSection channel={channel} />
      <AnomalySection channel={channel} liveData={liveData} />
    </section>
  );
}

