/**
 * ProfilesPanel: Displays user-owned load profiles, learned signatures,
 * and Safe Limits policy management (Workstream 3 & 8).
 */
import { useState, useEffect } from "react";
import { api } from "../api/client.js";
import { fmt } from "./Metric.jsx";

export default function ProfilesPanel() {
  const [profiles, setProfiles] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [editingLimitsId, setEditingLimitsId] = useState(null);
  const [customLimits, setCustomLimits] = useState({ current: "", power: "" });

  async function refresh() {
    try {
      setLoading(true);
      const data = await api.listProfiles();
      setProfiles(data);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleConfirmProfile(id) {
    try {
      await api.confirmProfile(id);
      refresh();
    } catch (err) {
      alert("Failed to confirm profile: " + err.message);
    }
  }

  async function handleConfirmLimits(profile, custom = false) {
    try {
      const payload = {};
      if (custom && customLimits.current) {
        payload.confirmed_current_limit_a = parseFloat(customLimits.current);
      }
      if (custom && customLimits.power) {
        payload.confirmed_power_limit_w = parseFloat(customLimits.power);
      }
      await api.confirmProfileLimits(profile.id, payload);
      setEditingLimitsId(null);
      refresh();
    } catch (err) {
      alert("Failed to confirm limits: " + err.message);
    }
  }

  async function handleRejectLimits(profileId) {
    if (!window.confirm("Reject proposed limits and keep hardware safety defaults?")) return;
    try {
      await api.rejectProfileLimits(profileId);
      refresh();
    } catch (err) {
      alert("Failed to reject limits: " + err.message);
    }
  }

  return (
    <section className="profiles-panel">
      <div className="panel-header-row">
        <div>
          <h3>📋 Saved Load Profiles & Safe Limits</h3>
          <p className="subtext">
            Hardware Hard-Caps: CH1 (Motor) = 16.0 A / 3680 W · CH2 (Sensitive) = 10.0 A / 2300 W
          </p>
        </div>
        <button className="ai-btn" onClick={refresh} disabled={loading}>
          {loading ? "Refreshing..." : "↻ Refresh Profiles"}
        </button>
      </div>

      {error && <p className="fault">{error}</p>}

      {profiles.length === 0 && !loading && !error && (
        <p className="subtext">
          No load profiles learned yet. Start a learning session from the AI Intelligence tab.
        </p>
      )}

      <div className="profiles-grid">
        {profiles.map((p) => {
          const ch = p.channel_last_seen || 1;
          const hardCapA = ch === 1 ? 16.0 : 10.0;
          const hardCapW = ch === 1 ? 3680 : 2300;
          const hasProposed =
            p.limits_status === "PROPOSED" ||
            (p.proposed_current_limit_a != null && p.limits_status !== "CONFIRMED");

          return (
            <div className="profile-card" key={p.id}>
              <div className="profile-header">
                <div>
                  <strong>{p.display_name}</strong>
                  <span className="profile-ch-tag">Channel {ch}</span>
                </div>
                <div className="profile-badges">
                  {p.user_confirmed ? (
                    <span className="badge on">Profile Confirmed</span>
                  ) : (
                    <span className="badge off">Unconfirmed</span>
                  )}
                  {p.limits_status === "CONFIRMED" && (
                    <span className="badge on">Limits Active</span>
                  )}
                  {p.limits_status === "PROPOSED" && (
                    <span className="badge warning">Limits Proposed</span>
                  )}
                </div>
              </div>

              {/* Electrical Fingerprint Measurements */}
              <div className="ai-info-grid">
                <div className="ai-info-item">
                  <span>Nominal Power</span>
                  <strong>{fmt(p.nominal_power_w, 1)} W</strong>
                </div>
                <div className="ai-info-item">
                  <span>Nominal Current</span>
                  <strong>{fmt(p.nominal_current_a, 3)} A</strong>
                </div>
                <div className="ai-info-item">
                  <span>Hardware Hard-Cap</span>
                  <strong>{hardCapA} A / {hardCapW} W</strong>
                </div>
              </div>

              {/* Safe Limits Policy Section */}
              <div className="limits-box">
                <h4>🛡️ Safe Limits Policy</h4>
                <div className="limits-detail-grid">
                  <div>
                    <span className="subtext">Proposed Limits (+25% Headroom):</span>
                    <strong>
                      {p.proposed_current_limit_a
                        ? `${fmt(p.proposed_current_limit_a, 2)} A · ${fmt(p.proposed_power_limit_w, 1)} W`
                        : "None (Run learning first)"}
                    </strong>
                  </div>
                  <div>
                    <span className="subtext">Active Enforced Limits:</span>
                    <strong className={p.limits_status === "CONFIRMED" ? "normal" : ""}>
                      {p.confirmed_current_limit_a
                        ? `${fmt(p.confirmed_current_limit_a, 2)} A · ${fmt(p.confirmed_power_limit_w, 1)} W`
                        : `Default Cap: ${hardCapA} A · ${hardCapW} W`}
                    </strong>
                  </div>
                </div>

                {/* Operator Decision Actions */}
                {hasProposed && p.limits_status !== "CONFIRMED" && (
                  <div className="limits-action-bar">
                    <p className="limits-prompt">
                      Proposed limits detected. Operator confirmation required to activate protection thresholds:
                    </p>
                    <div className="limits-buttons">
                      <button
                        className="on-button"
                        onClick={() => handleConfirmLimits(p, false)}
                      >
                        ✓ Accept Proposed Limits
                      </button>
                      <button
                        className="off-button"
                        onClick={() => handleRejectLimits(p.id)}
                      >
                        ✗ Reject Limits
                      </button>
                      <button
                        className="ai-btn"
                        onClick={() => {
                          setEditingLimitsId(editingLimitsId === p.id ? null : p.id);
                          setCustomLimits({
                            current: String(p.proposed_current_limit_a || ""),
                            power: String(p.proposed_power_limit_w || ""),
                          });
                        }}
                      >
                        ✎ Custom Edit
                      </button>
                    </div>

                    {editingLimitsId === p.id && (
                      <div className="custom-limits-form">
                        <label>
                          Current Limit (A, max {hardCapA}A):
                          <input
                            type="number"
                            step="0.1"
                            max={hardCapA}
                            value={customLimits.current}
                            onChange={(e) =>
                              setCustomLimits({ ...customLimits, current: e.target.value })
                            }
                          />
                        </label>
                        <label>
                          Power Limit (W, max {hardCapW}W):
                          <input
                            type="number"
                            step="10"
                            max={hardCapW}
                            value={customLimits.power}
                            onChange={(e) =>
                              setCustomLimits({ ...customLimits, power: e.target.value })
                            }
                          />
                        </label>
                        <button
                          className="on-button"
                          onClick={() => handleConfirmLimits(p, true)}
                        >
                          Save & Activate Custom Limits
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {!p.user_confirmed && (
                <div style={{ marginTop: "1rem" }}>
                  <button
                    className="ai-btn"
                    onClick={() => handleConfirmProfile(p.id)}
                  >
                    Confirm Baseline Profile
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
