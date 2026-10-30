/**
 * App.jsx — Smart Load Protection Panel Dashboard v2
 *
 * Combines the original live telemetry view (via Node-RED WebSocket)
 * with AI-powered features (via FastAPI REST API):
 * - Load learning and profile management
 * - Real-time load recognition with similarity scoring
 * - Optimization mode suggestions with operator acceptance
 * - Anomaly detection with Z-score alerts
 */
import { useState } from "react";
import "./App.css";

import { useWebSocket } from "./hooks/useWebSocket.js";
import { getToken, clearToken } from "./api/client.js";

import CircuitCard from "./components/CircuitCard.jsx";
import Metric, { fmt } from "./components/Metric.jsx";
import LoginForm from "./components/LoginForm.jsx";
import AIPanel from "./components/AIPanel.jsx";
import ProfilesPanel from "./components/ProfilesPanel.jsx";

const EMPTY_CIRCUIT = {
  valid: false,
  voltage_V: null,
  current_A: null,
  active_power_W: null,
  active_power_kW: null,
  apparent_power_VA: null,
  reactive_power_var: null,
  energy_kWh: null,
  session_energy_kWh: null,
  reactive_energy_kvarh: null,
  frequency_Hz: null,
  power_factor_meter: null,
  power_factor_calculated: null,
  load_percent: null,
  voltage_min_V: null,
  voltage_max_V: null,
  current_max_A: null,
  peak_power_W: null,
  reading_count: null,
  ok_count: null,
  error_count: null,
  communication_health_percent: null,
  voltage_gain: null,
  current_gain: null,
  power_gain: null,
  operating_hours: null,
  load_hours: null,
  relay_on: false,
  "relay/state": "OFF",
  relay_mode: "MANUAL",
  fault: false,
  over_voltage: false,
  under_voltage: false,
  over_current: false,
  pzem_alarm: false,
  latched_fault: false,
  relay_mismatch: false,
  supply_status: "NO DATA",
};

export default function App() {
  const { telemetry, connected, connectionText, sendCommand } = useWebSocket();
  const [loggedIn, setLoggedIn] = useState(!!getToken());
  const [activeTab, setActiveTab] = useState("live");

  const c1 = { ...EMPTY_CIRCUIT, ...(telemetry.circuit1 || {}) };
  const c2 = { ...EMPTY_CIRCUIT, ...(telemetry.circuit2 || {}) };
  const bothValid = c1.valid === true && c2.valid === true;

  const totals = [
    ["Combined Active Power", "active_power_W", "W", 2],
    ["Combined Apparent Power", "apparent_power_VA", "VA", 2],
    ["Combined Current", "current_A", "A", 3],
    ["Combined Active Energy", "energy_kWh", "kWh", 6],
  ];

  function sum(key) {
    return (Number(c1[key]) || 0) + (Number(c2[key]) || 0);
  }

  function handleLogout() {
    clearToken();
    setLoggedIn(false);
  }

  return (
    <main className="dashboard">
      <header className="topbar">
        <div>
          <p className="eyebrow">SMART LOAD PROTECTION PANEL</p>
          <h1>Dual-Circuit Energy Monitor</h1>
          <p className="subtext">
            Live measurements, AI load recognition, and optimization suggestions
          </p>
        </div>

        <div className="topbar-right">
          <div className={`connection ${connected ? "online" : "offline"}`}>
            <span className="status-dot" />
            {connectionText}
          </div>

          {loggedIn ? (
            <button className="logout-btn" onClick={handleLogout}>
              Sign Out
            </button>
          ) : null}
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="tab-nav">
        <button
          className={activeTab === "live" ? "tab active" : "tab"}
          onClick={() => setActiveTab("live")}
        >
          📊 Live Telemetry
        </button>
        <button
          className={activeTab === "ai" ? "tab active" : "tab"}
          onClick={() => setActiveTab("ai")}
        >
          🤖 AI Intelligence
        </button>
        <button
          className={activeTab === "profiles" ? "tab active" : "tab"}
          onClick={() => setActiveTab("profiles")}
        >
          📋 Load Profiles
        </button>
      </nav>

      {/* Combined Summary (always visible) */}
      <section className="summary-card">
        <h2>Combined Circuit Summary</h2>
        <div className="summary-grid">
          {totals.map(([label, key, unit, decimals]) => (
            <Metric
              key={key}
              label={label}
              value={sum(key)}
              unit={unit}
              decimals={decimals}
            />
          ))}
        </div>
        <p className={bothValid ? "normal" : "warning"}>
          {bothValid
            ? "Both meters have valid readings"
            : "One or both meters have missing or invalid readings"}
        </p>
        <p className="subtext">
          ESP32 uptime: {fmt(telemetry.uptime_s, 0)} seconds
        </p>
      </section>

      {/* Live Telemetry Tab */}
      {activeTab === "live" && (
        <section className="circuit-grid">
          <CircuitCard
            id={1}
            data={c1}
            connected={connected}
            sendCommand={sendCommand}
          />
          <CircuitCard
            id={2}
            data={c2}
            connected={connected}
            sendCommand={sendCommand}
          />
        </section>
      )}

      {/* AI Intelligence Tab */}
      {activeTab === "ai" && (
        <>
          {loggedIn ? (
            <section className="ai-grid">
              <AIPanel channel={1} liveData={c1} />
              <AIPanel channel={2} liveData={c2} />
            </section>
          ) : (
            <section className="login-section">
              <LoginForm onLogin={() => setLoggedIn(true)} />
            </section>
          )}
        </>
      )}

      {/* Load Profiles Tab */}
      {activeTab === "profiles" && (
        <>
          {loggedIn ? (
            <ProfilesPanel />
          ) : (
            <section className="login-section">
              <LoginForm onLogin={() => setLoggedIn(true)} />
            </section>
          )}
        </>
      )}

      <footer>
        ESP32-S3 WROOM · Dual PZEM-004T · MQTT · Node-RED · FastAPI · PostgreSQL + TimescaleDB
      </footer>
    </main>
  );
}

