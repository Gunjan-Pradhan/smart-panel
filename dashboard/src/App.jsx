/**
 * App.jsx — Smart Load Protection Panel Dashboard v2.5
 *
 * Full Capstone System Interface:
 * - Real-Time Telemetry Streaming via native FastAPI WebSocket (/ws/live/{device_id})
 * - Dual PZEM-004T Channel Telemetry & Relay Control with Real-Ack Tracking
 * - AI Load Recognition & Learning Engine
 * - Safe Limits Policy Management (Operator Confirmation of +25% Proposals)
 * - Local Hardware Schedules & Automated Timers
 * - Protection Events & Anomaly Audit Log
 */
import { useState, useEffect } from "react";
import "./App.css";

import { useWebSocket } from "./hooks/useWebSocket.js";
import { getToken, clearToken, api } from "./api/client.js";

import CircuitCard from "./components/CircuitCard.jsx";
import Metric, { fmt } from "./components/Metric.jsx";
import LoginForm from "./components/LoginForm.jsx";
import AIPanel from "./components/AIPanel.jsx";
import ProfilesPanel from "./components/ProfilesPanel.jsx";
import SchedulesPanel from "./components/SchedulesPanel.jsx";
import EventsPanel from "./components/EventsPanel.jsx";

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
  const [activeDeviceId, setActiveDeviceId] = useState("PANEL-0001");
  const { telemetry, connected, connectionText, sendCommand, setDeviceId } =
    useWebSocket(activeDeviceId);

  const [loggedIn, setLoggedIn] = useState(!!getToken());
  const [activeTab, setActiveTab] = useState("live");
  const [userDevices, setUserDevices] = useState([]);

  useEffect(() => {
    if (loggedIn) {
      api
        .getDevices()
        .then((devices) => {
          if (Array.isArray(devices) && devices.length > 0) {
            setUserDevices(devices);
            if (!devices.some((d) => d.device_id === activeDeviceId)) {
              setActiveDeviceId(devices[0].device_id);
              setDeviceId(devices[0].device_id);
            }
          }
        })
        .catch(() => {});
    }
  }, [loggedIn]);

  function handleDeviceChange(e) {
    const newId = e.target.value;
    setActiveDeviceId(newId);
    setDeviceId(newId);
  }

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
          <p className="eyebrow">SMART LOAD PROTECTION PANEL · ECE CAPSTONE</p>
          <h1>Dual-Circuit Energy & Protection Dashboard</h1>
          <p className="subtext">
            Autonomous protection, sub-cycle telemetry, AI load recognition & safe limits
          </p>
        </div>

        <div className="topbar-right">
          {userDevices.length > 0 && (
            <div className="device-picker">
              <label htmlFor="device-select">Device: </label>
              <select
                id="device-select"
                value={activeDeviceId}
                onChange={handleDeviceChange}
              >
                {userDevices.map((d) => (
                  <option key={d.id} value={d.device_id}>
                    {d.name} ({d.device_id})
                  </option>
                ))}
              </select>
            </div>
          )}

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
          📋 Profiles & Safe Limits
        </button>
        <button
          className={activeTab === "schedules" ? "tab active" : "tab"}
          onClick={() => setActiveTab("schedules")}
        >
          ⏱️ Local Schedules
        </button>
        <button
          className={activeTab === "events" ? "tab active" : "tab"}
          onClick={() => setActiveTab("events")}
        >
          🛡️ Protection & Events
        </button>
      </nav>

      {/* Combined Summary (always visible) */}
      <section className="summary-card">
        <div className="summary-header">
          <h2>Combined Circuit Summary — Panel {activeDeviceId}</h2>
          <span className="subtext">
            Channel 1: Inductive Motor (16A cap) · Channel 2: Sensitive Load (10A cap)
          </span>
        </div>
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
            ? "✓ Both energy meters reporting valid synchronized telemetry"
            : "⚠ Waiting for live PZEM meter streams..."}
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

      {/* Load Profiles & Safe Limits Tab */}
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

      {/* Local Schedules Tab */}
      {activeTab === "schedules" && (
        <>
          {loggedIn ? (
            <SchedulesPanel defaultDeviceId={activeDeviceId} />
          ) : (
            <section className="login-section">
              <LoginForm onLogin={() => setLoggedIn(true)} />
            </section>
          )}
        </>
      )}

      {/* Protection Events Tab */}
      {activeTab === "events" && (
        <>
          {loggedIn ? (
            <EventsPanel />
          ) : (
            <section className="login-section">
              <LoginForm onLogin={() => setLoggedIn(true)} />
            </section>
          )}
        </>
      )}

      <footer>
        ESP32-S3 WROOM · Dual PZEM-004T v3/v4 · FreeRTOS · Mosquitto MQTT · FastAPI · TimescaleDB
        · Advisory AI Engine
      </footer>
    </main>
  );
}
