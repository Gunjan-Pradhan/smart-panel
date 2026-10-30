/**
 * ProfilesPanel: displays user-owned load profiles with confirm/rename actions.
 */
import { useState, useEffect } from "react";
import { api } from "../api/client.js";
import { fmt } from "./Metric.jsx";

export default function ProfilesPanel() {
  const [profiles, setProfiles] = useState([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const data = await api.listProfiles();
      setProfiles(data);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function confirmProfile(id) {
    try {
      await api.confirmProfile(id);
      refresh();
    } catch (err) {
      alert("Failed: " + err.message);
    }
  }

  if (profiles.length === 0 && !error) {
    return (
      <section className="profiles-panel">
        <h3>📋 Saved Load Profiles</h3>
        <p className="subtext">No profiles yet. Start a learning session to create one.</p>
      </section>
    );
  }

  return (
    <section className="profiles-panel">
      <h3>📋 Saved Load Profiles</h3>
      {error && <p className="fault">{error}</p>}
      <div className="profiles-grid">
        {profiles.map((p) => (
          <div className="profile-card" key={p.id}>
            <div className="profile-header">
              <strong>{p.display_name}</strong>
              {p.user_confirmed ? (
                <span className="badge on">Confirmed</span>
              ) : (
                <span className="badge off">Unconfirmed</span>
              )}
            </div>
            <div className="ai-info-grid">
              <div className="ai-info-item">
                <span>Channel</span>
                <strong>{p.channel_last_seen || "Any"}</strong>
              </div>
              <div className="ai-info-item">
                <span>Power</span>
                <strong>{fmt(p.nominal_power_w, 1)} W</strong>
              </div>
              <div className="ai-info-item">
                <span>Current</span>
                <strong>{fmt(p.nominal_current_a, 3)} A</strong>
              </div>
            </div>
            {p.notes && <p className="subtext">{p.notes}</p>}
            {!p.user_confirmed && (
              <button
                className="ai-btn"
                onClick={() => confirmProfile(p.id)}
              >
                Confirm Profile
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

