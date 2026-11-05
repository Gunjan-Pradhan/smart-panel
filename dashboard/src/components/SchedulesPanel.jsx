/**
 * SchedulesPanel: Local Schedules and Timers management (Workstream 7).
 * Connects to /schedules CRUD API and syncs to ESP32 over MQTT.
 */
import { useState, useEffect } from "react";
import { api } from "../api/client.js";

const DAYS = [
  { bit: 1, label: "Mon" },
  { bit: 2, label: "Tue" },
  { bit: 4, label: "Wed" },
  { bit: 8, label: "Thu" },
  { bit: 16, label: "Fri" },
  { bit: 32, label: "Sat" },
  { bit: 64, label: "Sun" },
];

export default function SchedulesPanel({ defaultDeviceId = "PANEL-0001" }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // Form state
  const [name, setName] = useState("");
  const [channel, setChannel] = useState(1);
  const [selectedDays, setSelectedDays] = useState(31); // Mon-Fri default
  const [onTime, setOnTime] = useState("06:00:00");
  const [offTime, setOffTime] = useState("08:00:00");
  const [timezone, setTimezone] = useState("Asia/Kolkata");

  async function refresh() {
    try {
      setLoading(true);
      const list = await api.listSchedules();
      setSchedules(list);
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

  function toggleDay(bit) {
    setSelectedDays((prev) => (prev & bit ? prev & ~bit : prev | bit));
  }

  function formatDays(mask) {
    const active = DAYS.filter((d) => (mask & d.bit) !== 0).map((d) => d.label);
    if (active.length === 7) return "Every Day";
    if (active.length === 5 && (mask & 31) === 31) return "Weekdays (Mon-Fri)";
    if (active.length === 2 && (mask & 96) === 96) return "Weekends (Sat-Sun)";
    return active.join(", ") || "None";
  }

  async function handleToggleEnabled(sched) {
    try {
      await api.updateSchedule(sched.id, { enabled: !sched.enabled });
      refresh();
    } catch (err) {
      alert("Failed to update schedule: " + err.message);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm("Delete this timer schedule?")) return;
    try {
      await api.deleteSchedule(id);
      refresh();
    } catch (err) {
      alert("Failed to delete: " + err.message);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    if (selectedDays === 0) {
      alert("Please select at least one day of the week.");
      return;
    }
    if (onTime === offTime) {
      alert("On time and Off time must be different.");
      return;
    }

    try {
      await api.createSchedule({
        device_id: defaultDeviceId,
        ch: Number(channel),
        name,
        days_of_week: selectedDays,
        on_time: onTime.length === 5 ? `${onTime}:00` : onTime,
        off_time: offTime.length === 5 ? `${offTime}:00` : offTime,
        timezone,
        enabled: true,
      });
      setShowCreate(false);
      setName("");
      refresh();
    } catch (err) {
      alert("Create schedule failed: " + err.message);
    }
  }

  return (
    <section className="schedules-panel">
      <div className="panel-header-row">
        <div>
          <h3>⏱️ Local Channel Schedules & Automated Timers</h3>
          <p className="subtext">
            Schedules execute automatically on the hardware even during internet outages.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className="ai-btn"
            onClick={() => setShowCreate(!showCreate)}
          >
            {showCreate ? "Cancel" : "+ New Timer Schedule"}
          </button>
          <button className="ai-btn" onClick={refresh} disabled={loading}>
            ↻
          </button>
        </div>
      </div>

      {error && <p className="fault">{error}</p>}

      {showCreate && (
        <form className="create-schedule-form" onSubmit={handleCreate}>
          <h4>Add New Timer Schedule</h4>
          <div className="form-row">
            <label>
              Schedule Name:
              <input
                type="text"
                required
                placeholder="e.g. Morning Water Pump"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Target Channel:
              <select
                value={channel}
                onChange={(e) => setChannel(Number(e.target.value))}
              >
                <option value={1}>Channel 1 — Motor (16A)</option>
                <option value={2}>Channel 2 — Sensitive Load (10A)</option>
              </select>
            </label>
          </div>

          <div className="form-row">
            <label>
              Turn ON Time:
              <input
                type="time"
                required
                value={onTime.substring(0, 5)}
                onChange={(e) => setOnTime(e.target.value)}
              />
            </label>
            <label>
              Turn OFF Time:
              <input
                type="time"
                required
                value={offTime.substring(0, 5)}
                onChange={(e) => setOffTime(e.target.value)}
              />
            </label>
            <label>
              Timezone:
              <input
                type="text"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              />
            </label>
          </div>

          <div className="days-selector">
            <span>Repeat on:</span>
            <div className="day-pills">
              {DAYS.map((d) => (
                <button
                  type="button"
                  key={d.bit}
                  className={`day-pill ${(selectedDays & d.bit) !== 0 ? "active" : ""}`}
                  onClick={() => toggleDay(d.bit)}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <button type="submit" className="on-button" style={{ marginTop: "1rem" }}>
            Save & Sync to Device
          </button>
        </form>
      )}

      {schedules.length === 0 && !loading && !error && (
        <p className="subtext">
          No automated schedules configured. Click "+ New Timer Schedule" to add one.
        </p>
      )}

      <div className="schedules-grid">
        {schedules.map((s) => (
          <div className={`schedule-card ${s.enabled ? "active" : "disabled"}`} key={s.id}>
            <div className="schedule-header">
              <div>
                <strong>{s.name}</strong>
                <span className="profile-ch-tag">Channel {s.ch}</span>
              </div>
              <span className={`badge ${s.enabled ? "on" : "off"}`}>
                {s.enabled ? "ENABLED" : "DISABLED"}
              </span>
            </div>

            <div className="schedule-details">
              <div className="time-range">
                <span className="time-badge on">ON: {s.on_time}</span>
                <span className="time-arrow">➜</span>
                <span className="time-badge off">OFF: {s.off_time}</span>
              </div>
              <p className="days-label">📅 {formatDays(s.days_of_week)}</p>
              <p className="subtext">Device: {s.device_id} ({s.timezone})</p>
            </div>

            <div className="schedule-actions">
              <button
                className={s.enabled ? "off-button" : "on-button"}
                onClick={() => handleToggleEnabled(s)}
              >
                {s.enabled ? "Disable" : "Enable"}
              </button>
              <button
                className="delete-button"
                onClick={() => handleDelete(s.id)}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

