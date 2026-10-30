/**
 * CircuitCard: full live telemetry card for one PZEM channel.
 * Preserves the original reference dashboard layout.
 */
import Metric from "./Metric.jsx";

const SECTIONS = [
  {
    title: "Electrical Parameters",
    items: [
      ["Voltage", "voltage_V", "V", 2],
      ["Current", "current_A", "A", 3],
      ["Frequency", "frequency_Hz", "Hz", 1],
      ["Load", "load_percent", "%", 2],
    ],
  },
  {
    title: "Power Measurements",
    items: [
      ["Active Power", "active_power_W", "W", 2],
      ["Active Power", "active_power_kW", "kW", 4],
      ["Apparent Power", "apparent_power_VA", "VA", 2],
      ["Reactive Power", "reactive_power_var", "var", 2],
    ],
  },
  {
    title: "Power Factor",
    items: [
      ["PZEM Power Factor", "power_factor_meter", "", 3],
      ["Calculated Power Factor", "power_factor_calculated", "", 3],
    ],
  },
  {
    title: "Energy Measurements",
    items: [
      ["Total Active Energy", "energy_kWh", "kWh", 6],
      ["Session Energy", "session_energy_kWh", "kWh", 6],
      ["Reactive Energy", "reactive_energy_kvarh", "kvarh", 6],
    ],
  },
  {
    title: "Statistics",
    items: [
      ["Minimum Voltage", "voltage_min_V", "V", 2],
      ["Maximum Voltage", "voltage_max_V", "V", 2],
      ["Maximum Current", "current_max_A", "A", 3],
      ["Peak Power", "peak_power_W", "W", 2],
    ],
  },
  {
    title: "Communication Statistics",
    items: [
      ["Reading Count", "reading_count", "", 0],
      ["Successful Reads", "ok_count", "", 0],
      ["Failed Reads", "error_count", "", 0],
      ["Communication Health", "communication_health_percent", "%", 1],
    ],
  },
  {
    title: "Calibration Gains",
    items: [
      ["Voltage Gain", "voltage_gain", "", 4],
      ["Current Gain", "current_gain", "", 4],
      ["Power Gain", "power_gain", "", 4],
    ],
  },
  {
    title: "Operating Time",
    items: [
      ["Monitor Operating Time", "operating_hours", "h", 2],
      ["Load Running Time", "load_hours", "h", 2],
    ],
  },
];

const FAULTS = [
  ["Overvoltage", "over_voltage"],
  ["Undervoltage", "under_voltage"],
  ["Overcurrent", "over_current"],
  ["PZEM Alarm", "pzem_alarm"],
  ["Latched Fault", "latched_fault"],
];

export default function CircuitCard({ id, data, connected, sendCommand }) {
  const relayOn =
    data["relay/state"] === "ON" || data.relay_on === true;
  const valid = data.valid === true;
  const fault = data.fault === true;

  return (
    <section className="circuit-card">
      <div className="card-heading">
        <div>
          <p className="eyebrow">CHANNEL {id}</p>
          <h2>Circuit {id}</h2>
          <p className="subtext">PZEM-004T Energy Meter</p>
        </div>
        <span className={`badge ${relayOn ? "on" : "off"}`}>
          Relay {relayOn ? "ON" : "OFF"}
        </span>
      </div>

      <div className="status-grid">
        <div className="status-box">
          <span>Meter</span>
          <strong className={valid ? "normal" : "warning"}>
            {valid ? "VALID DATA" : "NO VALID DATA"}
          </strong>
        </div>
        <div className="status-box">
          <span>Supply</span>
          <strong>{data.supply_status || "NO DATA"}</strong>
        </div>
        <div className="status-box">
          <span>Fault</span>
          <strong className={fault ? "fault" : "normal"}>
            {fault ? "FAULT" : "NORMAL"}
          </strong>
        </div>
        <div className="status-box">
          <span>Relay Mode</span>
          <strong>{data.relay_mode || "MANUAL"}</strong>
        </div>
      </div>

      {SECTIONS.map((section) => (
        <details className="parameter-section" key={section.title} open>
          <summary>{section.title}</summary>
          <div className="metrics">
            {section.items.map(([label, key, unit, decimals]) => (
              <Metric
                key={key}
                label={label}
                value={data[key]}
                unit={unit}
                decimals={decimals}
              />
            ))}
          </div>
        </details>
      ))}

      <details className="parameter-section" open>
        <summary>Protection and Fault Indicators</summary>
        <div className="fault-list">
          {FAULTS.map(([label, key]) => (
            <div className="fault-item" key={key}>
              <span>{label}</span>
              <strong className={data[key] === true ? "fault" : "normal"}>
                {data[key] === true ? "ACTIVE" : "CLEAR"}
              </strong>
            </div>
          ))}
        </div>
      </details>

      <details className="parameter-section">
        <summary>Relay Wiring Diagnostics</summary>
        <div className="fault-item">
          <span>Relay state</span>
          <strong>{relayOn ? "ON" : "OFF"}</strong>
        </div>
        <div className="fault-item">
          <span>Current while relay OFF</span>
          <strong className={data.relay_mismatch ? "fault" : "normal"}>
            {data.relay_mismatch ? "MISMATCH" : "OK"}
          </strong>
        </div>
      </details>

      <div className="controls">
        <button
          className="on-button"
          disabled={!connected}
          onClick={() => sendCommand(id, "ON")}
        >
          Turn ON
        </button>
        <button
          className="off-button"
          disabled={!connected}
          onClick={() => sendCommand(id, "OFF")}
        >
          Turn OFF
        </button>
      </div>

      <p className="control-note">
        Manual dashboard control. Faults are displayed but do not
        automatically switch the relay.
      </p>
    </section>
  );
}

