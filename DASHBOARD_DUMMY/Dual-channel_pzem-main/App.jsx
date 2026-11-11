import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import {
  LayoutDashboard,
  Gauge,
  Sliders,
  Lightbulb,
  HeartPulse,
  BrainCircuit,
  PanelLeft,
  X,
  Clock,
  ShieldCheck,
  Activity,
  Power,
  SlidersHorizontal,
  Timer,
} from 'lucide-react';
import './index.css';

// Use explicit IPv4 127.0.0.1 and dedicated /ws/smartpanel path to avoid macOS IPv6 & Node-RED config collisions
const WS_HOST =
  typeof window !== 'undefined' &&
  window.location.hostname &&
  window.location.hostname !== 'localhost'
    ? window.location.hostname
    : '127.0.0.1';
const WS_URL = `ws://${WS_HOST}:1880/ws/smartpanel`;

const PEAK_LIMIT_W = 4000;
const TARIFF_INR = 7.5;

const INITIAL_LOAD_1 = {
  name: 'Industrial Load',
  v: 0.0,
  i: 0.0,
  p: 0.0,
  e: 0.0,
  f: 50.0,
  pfMeter: 1.0,
  pfCalc: 1.0,
  s: 0.0,
  q: 0.0,
  ssr: false,
  fault: null,
  anomaly: 0.0,
  health: 98,
  retry_count: 0,
  commsHealth: 100.0,
  okCount: 0,
  errCount: 0,
  relayMismatch: false,
  voltGain: 1.0,
  currGain: 1.0,
  powGain: 1.0,
  opHours: 0.0,
  loadHours: 0.0,
};

const INITIAL_LOAD_2 = {
  name: 'Household Load',
  v: 0.0,
  i: 0.0,
  p: 0.0,
  e: 0.0,
  f: 50.0,
  pfMeter: 1.0,
  pfCalc: 1.0,
  s: 0.0,
  q: 0.0,
  ssr: false,
  fault: null,
  anomaly: 0.0,
  health: 98,
  retry_count: 0,
  commsHealth: 100.0,
  okCount: 0,
  errCount: 0,
  relayMismatch: false,
  voltGain: 1.0,
  currGain: 1.0,
  powGain: 1.0,
  opHours: 0.0,
  loadHours: 0.0,
};

const INITIAL_HEARTBEAT = {
  device_id: 'SP01',
  wifi_rssi: -52,
  mqtt_ok: true,
  active_modes: [2, 3, 8],
};

const NAV_ITEMS = [
  { id: 'overview', label: 'Dashboard Overview', Icon: LayoutDashboard },
  { id: 'standard', label: 'Standard Monitoring', Icon: Gauge },
  { id: 'derived', label: 'Detailed Derived Parameter Analysis', Icon: Activity },
  { id: 'modes', label: 'Optimization Modes', Icon: Sliders },
  { id: 'tips', label: 'Energy Saving Tips & Cost Insights', Icon: Lightbulb },
  { id: 'health', label: 'Load Health Monitoring', Icon: HeartPulse },
  { id: 'ai_summary', label: 'AI Based Summary & Executive Diagnostics', Icon: BrainCircuit },
];

const generateInitialHistory = () =>
  Array.from({ length: 10 }, (_, idx) => ({
    slot: `00:0${idx}`,
    v1: 0,
    i1: 0,
    p_load1: 0,
    v2: 0,
    i2: 0,
    p_load2: 0,
    s_va: 0,
    q_var: 0,
    e_kwh: 0,
  }));

const TOOLTIP_STYLE = {
  background: 'rgba(18, 22, 28, 0.95)',
  border: '1px solid rgba(255, 255, 255, 0.15)',
  borderRadius: '10px',
  fontSize: '12px',
  color: '#f4f6f9',
};

function EcgWaveformStrip({ isOnline }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationId;
    let offset = 0;

    const sampleBeat = (x) => {
      const cycle = ((x % 130) + 130) % 130;
      if (cycle < 20) return Math.sin((cycle / 20) * Math.PI) * 4;
      if (cycle < 35) return 0;
      if (cycle < 42) return -((cycle - 35) / 7) * 5;
      if (cycle < 51) return -5 + ((cycle - 42) / 9) * 35;
      if (cycle < 60) return 30 - ((cycle - 51) / 9) * 38;
      if (cycle < 68) return -8 + ((cycle - 60) / 8) * 8;
      if (cycle < 84) return 0;
      if (cycle < 108) return Math.sin(((cycle - 84) / 24) * Math.PI) * 7.5;
      return 0;
    };

    const render = () => {
      const width = canvas.width;
      const height = canvas.height;
      const midY = height / 2;

      ctx.clearRect(0, 0, width, height);

      ctx.strokeStyle = 'rgba(255, 255, 255, 0.035)';
      ctx.lineWidth = 1;
      for (let x = 0; x < width; x += 20) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += 12) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.lineWidth = 1.8;

      if (!isOnline) {
        ctx.strokeStyle = '#ff453a';
        ctx.shadowColor = 'rgba(255, 69, 58, 0.7)';
        ctx.shadowBlur = 8;
        ctx.moveTo(0, midY);
        ctx.lineTo(width, midY);
        ctx.stroke();
      } else {
        const grad = ctx.createLinearGradient(0, 0, width, 0);
        grad.addColorStop(0, 'rgba(225, 230, 235, 0.08)');
        grad.addColorStop(0.35, 'rgba(225, 230, 235, 0.45)');
        grad.addColorStop(0.85, 'rgba(240, 245, 250, 0.95)');
        grad.addColorStop(1, '#ffffff');

        ctx.strokeStyle = grad;
        ctx.shadowColor = 'rgba(225, 230, 235, 0.55)';
        ctx.shadowBlur = 6;

        for (let x = 0; x < width; x++) {
          const y = midY - sampleBeat(x - offset);
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
        offset = (offset + 0.62) % 130;
      }

      animationId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animationId);
  }, [isOnline]);

  return (
    <div className="ecg-canvas-wrap">
      <canvas ref={canvasRef} width={340} height={48} />
    </div>
  );
}

function CircularMetricGauge({ label, value, max, unit }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(100, Math.max(0, (Number(value) / max) * 100));
  const dashOffset = circumference - (pct / 100) * circumference;

  return (
    <div className="mini-gauge-box">
      <div className="mini-gauge-label">{label}</div>
      <div className="mini-gauge-svg-wrap">
        <svg width="104" height="104" viewBox="0 0 104 104">
          <circle
            cx="52"
            cy="52"
            r={radius}
            fill="rgba(15, 19, 25, 0.5)"
            stroke="rgba(255, 255, 255, 0.08)"
            strokeWidth="7"
          />
          <circle
            cx="52"
            cy="52"
            r={radius}
            fill="none"
            stroke="#e1e6eb"
            strokeWidth="7"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            transform="rotate(-90 52 52)"
            style={{ transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div className="mini-gauge-center">
          <span className="mini-gauge-val">{value}</span>
          <span className="mini-gauge-unit">{unit}</span>
        </div>
      </div>
    </div>
  );
}

function CircuitStandardColumn({ load, history, vKey, iKey }) {
  const sApparent = Number((load.v * load.i).toFixed(1));
  const qReactive = Number(Math.sqrt(Math.max(0, sApparent ** 2 - load.p ** 2)).toFixed(1));
  const qsRatio = sApparent > 0 ? Number((qReactive / sApparent).toFixed(3)) : 0;

  return (
    <div className="glass-card circuit-column">
      <div className="card-header">
        <div className="card-title">{load.name}</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={`status-pill-badge ${load.ssr ? 'live' : 'fault'}`}>
            {load.ssr ? 'RELAY ACTIVE (ON)' : 'RELAY OPEN (OFF)'}
          </span>
          <span className="status-pill-badge">VALID RMS</span>
        </div>
      </div>

      <div className="gauge-quad-grid">
        <CircularMetricGauge label="Voltage Gauge" value={load.v} max={260} unit="V RMS" />
        <CircularMetricGauge label="Current Gauge" value={load.i} max={30} unit="A RMS" />
        <CircularMetricGauge label="Power Gauge" value={load.p} max={4000} unit="W" />
        <CircularMetricGauge label="Energy Gauge" value={load.e} max={100} unit="kWh" />
      </div>

      <div className="mini-chart-box">
        <div className="metric-label">Live RMS Voltage Graph (V)</div>
        <div className="chart-body">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 6, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="slot" stroke="rgba(255,255,255,0.4)" fontSize={10} tickLine={false} />
              <YAxis domain={['auto', 'auto']} stroke="rgba(255,255,255,0.4)" fontSize={10} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Area
                type="monotone"
                dataKey={vKey}
                name="Voltage (V)"
                stroke="#e1e6eb"
                strokeWidth={2}
                fill="rgba(225, 230, 235, 0.12)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mini-chart-box">
        <div className="metric-label">Live RMS Current Graph (A)</div>
        <div className="chart-body">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history} margin={{ top: 6, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="slot" stroke="rgba(255,255,255,0.4)" fontSize={10} tickLine={false} />
              <YAxis domain={[0, 30]} stroke="rgba(255,255,255,0.4)" fontSize={10} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Line
                type="monotone"
                dataKey={iKey}
                name="Current (A)"
                stroke="#70b6ff"
                strokeWidth={2.2}
                dot={{ r: 2.5, fill: '#e1e6eb' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="ac-quality-strip">
        <div className="ac-stat-tile">
          <div className="metric-label">Line Frequency</div>
          <div className="ac-stat-val">{load.f} Hz</div>
          <div className="metric-sub">Nominal 50.0 Hz</div>
        </div>
        <div className="ac-stat-tile">
          <div className="metric-label">Power Factor (PF)</div>
          <div className="ac-stat-val">{load.pfMeter}</div>
          <div className="metric-sub">{load.pfMeter >= 0.95 ? 'Resistive' : 'Inductive'}</div>
        </div>
        <div className="ac-stat-tile">
          <div className="metric-label">Reactive Ratio (Q/S)</div>
          <div className="ac-stat-val">{qsRatio}</div>
          <div className="metric-sub">Q: {qReactive} VAR</div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [activeSlide, setActiveSlide] = useState('overview');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [load1, setLoad1] = useState(INITIAL_LOAD_1);
  const [load2, setLoad2] = useState(INITIAL_LOAD_2);
  const [heartbeat, setHeartbeat] = useState(INITIAL_HEARTBEAT);
  const [history, setHistory] = useState(generateInitialHistory);
  const [wsConnected, setWsConnected] = useState(false);
  const [rxPackets, setRxPackets] = useState(0);

  const wsRef = useRef(null);
  const cmdLockUntilRef = useRef({ 1: 0, 2: 0 });
  const latestLoadsRef = useRef({ load1: INITIAL_LOAD_1, load2: INITIAL_LOAD_2 });

  useEffect(() => {
    latestLoadsRef.current = { load1, load2 };
  }, [load1, load2]);

  const numOr = (obj, fallback, ...keys) => {
    if (!obj) return fallback;
    for (const k of keys) {
      if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') {
        const n = Number(obj[k]);
        if (!Number.isNaN(n)) return n;
      }
    }
    return fallback;
  };

  useEffect(() => {
    let ws;
    let reconnectTimer;
    let unmounted = false;

    const unpackPayload = (rawEventData) => {
      let parsed = rawEventData;
      if (typeof parsed === 'string') {
        parsed = JSON.parse(parsed);
      }
      if (parsed && typeof parsed.payload === 'string') {
        parsed = JSON.parse(parsed.payload);
      } else if (parsed && typeof parsed.payload === 'object' && parsed.payload !== null) {
        parsed = parsed.payload;
      }
      if (typeof parsed === 'string') {
        parsed = JSON.parse(parsed);
      }
      return parsed;
    };

    const mapCircuit = (c, prev, channelNum) => {
      const v = Number(numOr(c, prev.v, 'voltage_V', 'v', 'voltage').toFixed(1));
      const i = Number(numOr(c, prev.i, 'current_A', 'i', 'current').toFixed(3));
      const p = Number(numOr(c, prev.p, 'active_power_W', 'p', 'power').toFixed(1));
      const e = Number(numOr(c, prev.e, 'energy_kWh', 'e', 'energy').toFixed(3));
      const f = Number(numOr(c, prev.f, 'frequency_Hz', 'f', 'frequency').toFixed(2));
      const pfMeter = Number(numOr(c, prev.pfMeter, 'power_factor_meter', 'pf', 'power_factor').toFixed(2));

      const s = Number(numOr(c, v * i, 'apparent_power_VA', 's').toFixed(1));
      const qCalc = Math.sqrt(Math.max(0, s * s - p * p));
      const q = Number(numOr(c, qCalc, 'reactive_power_var', 'q').toFixed(1));
      const pfCalc =
        s > 0.5
          ? Number(numOr(c, Math.min(1, p / s), 'power_factor_calculated').toFixed(3))
          : pfMeter;

      // Respect 2.5s lock after manual button click so old MQTT packets cannot snap button backward
      let ssr = prev.ssr;
      if (Date.now() > cmdLockUntilRef.current[channelNum]) {
        const relayRaw = c['relay/state'] ?? c.relay_on ?? c.relay ?? c.relay_state;
        if (relayRaw !== undefined) {
          ssr =
            relayRaw === 'ON' ||
            relayRaw === true ||
            relayRaw === 'true' ||
            relayRaw === 1;
        }
      }

      const isFault =
        c.fault === true ||
        c.fault === 'true' ||
        c.fault === 'FAULT';

      const mismatchRaw = c.relay_mismatch;
      const relayMismatch =
        mismatchRaw === true ||
        mismatchRaw === 'true' ||
        (!ssr && i > 0.05);

      return {
        ...prev,
        v,
        i,
        p,
        e,
        f,
        pfMeter,
        pfCalc,
        s,
        q,
        ssr,
        fault: isFault ? 'FAULT DETECTED' : null,
        commsHealth: Number(numOr(c, prev.commsHealth, 'communication_health_percent').toFixed(1)),
        okCount: Math.round(numOr(c, prev.okCount, 'ok_count')),
        errCount: Math.round(numOr(c, prev.errCount, 'error_count')),
        opHours: numOr(c, prev.opHours, 'operating_hours'),
        loadHours: numOr(c, prev.loadHours, 'load_hours'),
        voltGain: numOr(c, prev.voltGain, 'voltage_gain'),
        currGain: numOr(c, prev.currGain, 'current_gain'),
        powGain: numOr(c, prev.powGain, 'power_gain'),
        relayMismatch,
      };
    };

    const connect = () => {
      if (unmounted) return;
      try {
        ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!unmounted) setWsConnected(true);
        };

        ws.onclose = () => {
          if (!unmounted) {
            setWsConnected(false);
            reconnectTimer = setTimeout(connect, 2000);
          }
        };

        ws.onerror = () => {
          ws.close();
        };

        ws.onmessage = (event) => {
          try {
            const raw = unpackPayload(event.data);
            if (!raw || typeof raw !== 'object') return;

            setRxPackets((cnt) => cnt + 1);

            const c1 = raw.circuit1 || raw['energy/dual_pzem/circuit1'];
            const c2 = raw.circuit2 || raw['energy/dual_pzem/circuit2'];

            if (c1 && Object.keys(c1).length > 0) {
              setLoad1((prev) => mapCircuit(c1, prev, 1));
            }
            if (c2 && Object.keys(c2).length > 0) {
              setLoad2((prev) => mapCircuit(c2, prev, 2));
            }
          } catch (err) {
            console.warn('WS parse warning:', err);
          }
        };
      } catch (err) {
        setWsConnected(false);
        reconnectTimer = setTimeout(connect, 2000);
      }
    };

    connect();

    return () => {
      unmounted = true;
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  // Append live hardware readings to charts every 2 seconds without resetting interval
  useEffect(() => {
    const chartTimer = setInterval(() => {
      const { load1: l1, load2: l2 } = latestLoadsRef.current;
      const now = new Date();
      const label = `${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
      setHistory((prev) => [
        ...prev.slice(1),
        {
          slot: label,
          v1: l1.v,
          i1: l1.i,
          p_load1: Math.round(l1.p),
          v2: l2.v,
          i2: l2.i,
          p_load2: Math.round(l2.p),
          s_va: Math.round(l1.s + l2.s),
          q_var: Math.round(l1.q + l2.q),
          e_kwh: Number((l1.e + l2.e).toFixed(3)),
        },
      ]);
    }, 2000);
    return () => clearInterval(chartTimer);
  }, []);

  const derived = useMemo(() => {
    const p_total = Number((load1.p + load2.p).toFixed(1));
    const i_total = Number((load1.i + load2.i).toFixed(2));
    const s_total = Number((load1.s + load2.s).toFixed(1));
    const q_total = Number((load1.q + load2.q).toFixed(1));
    const e_total = Number((load1.e + load2.e).toFixed(3));
    const v_avg = Number(((load1.v + load2.v) / 2).toFixed(1));
    const v_dev_pct = v_avg > 0 ? Number(((Math.abs(v_avg - 230) / 230) * 100).toFixed(2)) : 0;
    const household_share = p_total > 0 ? Math.round((load2.p / p_total) * 100) : 0;
    const avg_health = Math.round((load1.health + load2.health) / 2);
    const max_anomaly_pct = Number((Math.max(load1.anomaly, load2.anomaly) * 100).toFixed(1));
    const peak_ratio = Math.min(100, Math.round((p_total / PEAK_LIMIT_W) * 100));
    const est_bill_inr = Number((e_total * TARIFF_INR).toFixed(2));

    const pv2_c1 = load1.v > 0 ? Number(((load1.p / (load1.v ** 2)) * 1000).toFixed(3)) : 0;
    const pv2_c2 = load2.v > 0 ? Number(((load2.p / (load2.v ** 2)) * 1000).toFixed(3)) : 0;
    const qs_c1 = load1.s > 0 ? Number((load1.q / load1.s).toFixed(3)) : 0;
    const qs_c2 = load2.s > 0 ? Number((load2.q / load2.s).toFixed(3)) : 0;

    const p1Series = history.map((h) => h.p_load1);
    const meanP1 = p1Series.reduce((a, b) => a + b, 0) / (p1Series.length || 1);
    const stdP1 = Math.sqrt(
      p1Series.reduce((acc, val) => acc + (val - meanP1) ** 2, 0) / (p1Series.length || 1)
    );
    const cv_c1 = meanP1 > 0 ? Number(((stdP1 / meanP1) * 100).toFixed(2)) : 0;

    const ch1_duty_cycle =
      load1.opHours > 0 ? Number(((load1.loadHours / load1.opHours) * 100).toFixed(1)) : 0;

    return {
      p_total,
      i_total,
      s_total,
      q_total,
      e_total,
      v_avg,
      v_dev_pct,
      household_share,
      avg_health,
      max_anomaly_pct,
      peak_ratio,
      est_bill_inr,
      pv2_c1,
      pv2_c2,
      qs_c1,
      qs_c2,
      cv_c1,
      ch1_duty_cycle,
    };
  }, [load1, load2, history]);

  const toggleSSR = (channel) => {
    const isCh1 = channel === 1;
    const nextState = !(isCh1 ? load1.ssr : load2.ssr);
    const relayCmd = nextState ? 'ON' : 'OFF';

    // Lock out stale MQTT echo overwrites for 2.5 seconds
    cmdLockUntilRef.current[channel] = Date.now() + 2500;

    if (isCh1) setLoad1((prev) => ({ ...prev, ssr: nextState }));
    else setLoad2((prev) => ({ ...prev, ssr: nextState }));

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ circuit: channel, relay: relayCmd }));
    }
  };

  const toggleMode = (modeId) => {
    const exists = heartbeat.active_modes.includes(modeId);
    const updated = exists
      ? heartbeat.active_modes.filter((m) => m !== modeId)
      : [...heartbeat.active_modes, modeId];
    setHeartbeat((prev) => ({ ...prev, active_modes: updated }));
  };

  const ringRadius = 138;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringDashOffset = ringCircumference - (derived.peak_ratio / 100) * ringCircumference;

  return (
    <>
      <div className="ambient-backdrop">
        <div className="ambient-blob-1" />
        <div className="ambient-blob-2" />
      </div>

      <div className="app-shell">
        <aside className={`glass-sidebar ${sidebarOpen ? 'open' : ''}`}>
          <div className="sidebar-inner">
            <div className="sidebar-header">
              <div className="sidebar-brand">
                <Activity size={18} />
                <span>SMART PANEL HUD</span>
              </div>
              <button
                className="circle-badge-btn"
                onClick={() => setSidebarOpen(false)}
                title="Collapse Sidebar"
              >
                <X size={13} />
              </button>
            </div>

            <span className="sidebar-status-tag">
              {wsConnected ? `Live Stream (${rxPackets} pkts)` : 'Connecting WS...'}
            </span>

            <nav className="sidebar-nav">
              {NAV_ITEMS.map(({ id, label, Icon }) => (
                <button
                  key={id}
                  className={`sidebar-item ${activeSlide === id ? 'active' : ''}`}
                  onClick={() => setActiveSlide(id)}
                >
                  <Icon size={17} strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              ))}
            </nav>
          </div>
        </aside>

        <main className="hud-wrapper">
          <header className="hud-topbar">
            <div className="hud-brand">
              <button
                className={`sidebar-toggle-btn ${sidebarOpen ? 'active' : ''}`}
                onClick={() => setSidebarOpen((prev) => !prev)}
                title="Toggle Navigation Sidebar"
              >
                <PanelLeft size={15} />
                <span>{sidebarOpen ? 'Hide Menu' : 'Sidebar'}</span>
              </button>
              <span className={`status-dot ${wsConnected ? '' : 'offline'}`} />
              <span>SMART ELECTRICAL PANEL [{heartbeat.device_id}]</span>
            </div>

            <div className="hud-pills">
              <span className="hud-pill">
                Node-RED WS:{' '}
                <strong>
                  {wsConnected ? `CONNECTED • RX: ${rxPackets}` : 'DISCONNECTED'}
                </strong>
              </span>
              <span className="hud-pill">Freq: <strong>{load1.f} Hz</strong></span>
              <span className="hud-pill">V_dev: <strong>{derived.v_dev_pct}%</strong></span>
              <span className="hud-pill">Est. Cost: <strong>₹{derived.est_bill_inr}</strong></span>
            </div>
          </header>

          {activeSlide === 'overview' && (
            <>
              <section className="upper-grid">
                {/* Left Column Stack */}
                <div className="side-stack">
                  <div className="glass-card">
                    <div className="card-header">
                      <span className="card-title">Industrial Load</span>
                      <span className="status-pill-badge">CH 1</span>
                    </div>
                    <div className="dual-metrics">
                      <div>
                        <div className="metric-label">RMS Voltage (v)</div>
                        <div className="metric-big">{load1.v}<span className="metric-unit">V</span></div>
                        <div className="metric-sub">PF: {load1.pfMeter}</div>
                      </div>
                      <div>
                        <div className="metric-label">RMS Current (i)</div>
                        <div className="metric-big">{load1.i}<span className="metric-unit">A</span></div>
                        <div className="metric-sub">Active P: {load1.p} W</div>
                      </div>
                    </div>
                  </div>

                  <div className="glass-card">
                    <div className="card-header">
                      <span className="card-title">
                        <ShieldCheck size={16} color="#70b6ff" />
                        PZEM-1 Status & Control
                      </span>
                      <button
                        className={`circle-badge-btn ${load1.ssr ? 'active' : 'off'}`}
                        onClick={() => toggleSSR(1)}
                        title={`Command Relay 1 ${load1.ssr ? 'OFF' : 'ON'}`}
                      >
                        <Power size={13} />
                      </button>
                    </div>

                    <div className="ecg-monitor-panel">
                      <EcgWaveformStrip isOnline={load1.ssr} />
                      <div className="ecg-status-strip">
                        <span style={{ color: load1.ssr ? 'var(--mac-silver)' : '#ff453a', fontWeight: 500 }}>
                          {load1.ssr
                            ? `Comms Health: ${load1.commsHealth}% • ${load1.okCount} OK / ${load1.errCount} ERR`
                            : 'CIRCUIT DE-ENERGIZED (FLATLINE)'}
                        </span>
                        <span>{load1.ssr ? `${load1.f} Hz` : 'OFFLINE'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="glass-card">
                    <div className="card-header">
                      <span className="card-title">
                        <Timer size={16} color="#70b6ff" />
                        Industrial Equipment Utilization
                      </span>
                      <span className="status-pill-badge live">CH 1</span>
                    </div>
                    <div className="dual-metrics" style={{ marginTop: 6, marginBottom: 2 }}>
                      <div>
                        <div className="metric-label">Motor Duty Cycle</div>
                        <div className="metric-big">
                          {derived.ch1_duty_cycle}
                          <span className="metric-unit">%</span>
                        </div>
                        <div className="metric-sub">Active Running Fraction</div>
                      </div>
                      <div>
                        <div className="metric-label">Active Load Time</div>
                        <div className="metric-big">
                          {Number(load1.loadHours || 0).toFixed(1)}
                          <span className="metric-unit">h</span>
                        </div>
                        <div className="metric-sub">Total Service: {Number(load1.opHours || 0).toFixed(1)} h</div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Center Gauge */}
                <div className="center-ring-container">
                  <div className="ring-svg-wrap">
                    <svg width="100%" height="100%" viewBox="0 0 380 380">
                      <defs>
                        <filter id="macGlow" x="-30%" y="-30%" width="160%" height="160%">
                          <feGaussianBlur stdDeviation="8" result="blur" />
                          <feMerge>
                            <feMergeNode in="blur" />
                            <feMergeNode in="SourceGraphic" />
                          </feMerge>
                        </filter>
                        <linearGradient id="macRingGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                          <stop offset="0%" stopColor="#ffffff" />
                          <stop offset="50%" stopColor="#8be9fd" />
                          <stop offset="100%" stopColor="#0a84ff" />
                        </linearGradient>
                      </defs>
                      <circle cx="190" cy="190" r="172" fill="none" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="1.5" />
                      <circle cx="190" cy="190" r="160" fill="none" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="4" strokeDasharray="36 145 55 180" strokeLinecap="round" filter="url(#macGlow)" />
                      <circle cx="190" cy="190" r={ringRadius} fill="rgba(15, 19, 25, 0.5)" stroke="rgba(255, 255, 255, 0.1)" strokeWidth="11" />
                      <circle
                        cx="190"
                        cy="190"
                        r={ringRadius}
                        fill="none"
                        stroke="url(#macRingGrad)"
                        strokeWidth="9"
                        strokeDasharray={ringCircumference}
                        strokeDashoffset={ringDashOffset}
                        strokeLinecap="round"
                        transform="rotate(-90 190 190)"
                        filter="url(#macGlow)"
                        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
                      />
                      <circle cx="190" cy={190 - ringRadius} r="5.5" fill="#ffffff" filter="url(#macGlow)" />
                      <circle cx="190" cy="190" r={120} fill="none" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="1" />
                    </svg>
                    <div className="ring-center-overlay">
                      <div className="ring-title">Current =<br />Consumption</div>
                      <div className="ring-live-value">{Math.round(derived.p_total)} W</div>
                      <div className="ring-sub-stats">
                        <span>{derived.i_total} A</span><span>•</span><span>{derived.v_avg} V</span><span>•</span><span>{derived.peak_ratio}% of 4kW</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right Column Stack */}
                <div className="side-stack">
                  <div className="glass-card">
                    <div className="card-header">
                      <span className="card-title">Household Load</span>
                      <span className="status-pill-badge">CH 2</span>
                    </div>
                    <div className="dual-metrics">
                      <div>
                        <div className="metric-label">Power Share</div>
                        <div className="metric-big">{derived.household_share}<span className="metric-unit">%</span></div>
                        <div className="metric-sub">{load2.p} W</div>
                      </div>
                      <div>
                        <div className="metric-label">Current</div>
                        <div className="metric-big">{load2.i}<span className="metric-unit">A</span></div>
                        <div className="metric-sub">PF {load2.pfMeter}</div>
                      </div>
                    </div>
                  </div>

                  <div className="glass-card">
                    <div className="card-header">
                      <span className="card-title">
                        <Activity size={16} color="#70b6ff" />
                        PZEM-2 Status & Control
                      </span>
                      <button
                        className={`circle-badge-btn ${load2.ssr ? 'active' : 'off'}`}
                        onClick={() => toggleSSR(2)}
                        title={`Command Relay 2 ${load2.ssr ? 'OFF' : 'ON'}`}
                      >
                        <Power size={13} />
                      </button>
                    </div>

                    <div className="ecg-monitor-panel">
                      <EcgWaveformStrip isOnline={load2.ssr} />
                      <div className="ecg-status-strip">
                        <span style={{ color: load2.ssr ? 'var(--mac-silver)' : '#ff453a', fontWeight: 500 }}>
                          {load2.ssr
                            ? `Comms Health: ${load2.commsHealth}% • ${load2.okCount} OK / ${load2.errCount} ERR`
                            : 'CIRCUIT DE-ENERGIZED (FLATLINE)'}
                        </span>
                        <span>{load2.ssr ? `${load2.f} Hz` : 'OFFLINE'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="glass-card modes-card-balanced">
                    <div className="card-header">
                      <span className="card-title">
                        <Sliders size={16} color="#70b6ff" />
                        Optimization Modes
                      </span>
                      <span className="status-pill-badge">AUTO</span>
                    </div>
                    <div className="mode-icons-grid">
                      {[
                        { id: 2, label: 'Schedule', sub: 'Mode 2', Icon: Clock },
                        { id: 3, label: 'Peak Shed', sub: 'Mode 3', Icon: Sliders },
                        { id: 4, label: 'Idle Cut', sub: 'Mode 4', Icon: Power },
                        { id: 8, label: 'AI Core', sub: 'Mode 8', Icon: BrainCircuit },
                      ].map(({ id, label, sub, Icon }) => {
                        const isActive = heartbeat.active_modes.includes(id);
                        return (
                          <button
                            key={id}
                            className={`mode-btn ${isActive ? 'active' : ''}`}
                            onClick={() => toggleMode(id)}
                          >
                            <Icon size={20} strokeWidth={1.6} />
                            <span className="mode-name">{label}</span>
                            <span className="mode-sub">{sub}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </section>

              {/* Bottom 3 Charts */}
              <section className="bottom-charts-grid">
                <div className="glass-card chart-card">
                  <div className="card-header"><span className="card-title">Active Power P (W)</span></div>
                  <div className="chart-body">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <defs>
                          <linearGradient id="p1Fill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#e1e6eb" stopOpacity={0.4} />
                            <stop offset="95%" stopColor="#e1e6eb" stopOpacity={0.01} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="slot" stroke="rgba(255,255,255,0.4)" fontSize={11} tickLine={false} />
                        <YAxis domain={[0, 4000]} stroke="rgba(255,255,255,0.4)" fontSize={11} tickLine={false} />
                        <Tooltip contentStyle={TOOLTIP_STYLE} />
                        <Area type="monotone" dataKey="p_load1" name="Industrial P (W)" stroke="#e1e6eb" strokeWidth={2} fill="url(#p1Fill)" />
                        <Area type="monotone" dataKey="p_load2" name="Household P (W)" stroke="#70b6ff" strokeWidth={1.6} fillOpacity={0} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="glass-card chart-card">
                  <div className="card-header"><span className="card-title">Apparent (S) & Reactive (Q) Power</span></div>
                  <div className="chart-body">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="slot" stroke="rgba(255,255,255,0.4)" fontSize={11} tickLine={false} />
                        <YAxis domain={[0, 4200]} stroke="rgba(255,255,255,0.4)" fontSize={11} tickLine={false} />
                        <Tooltip contentStyle={TOOLTIP_STYLE} />
                        <Area type="monotone" dataKey="s_va" name="Apparent S (VA)" stroke="#e1e6eb" strokeWidth={2} fill="rgba(255,255,255,0.1)" />
                        <Area type="monotone" dataKey="q_var" name="Reactive Q (VAR)" stroke="#ff9f0a" strokeWidth={1.5} fillOpacity={0} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="glass-card chart-card">
                  <div className="card-header"><span className="card-title">Cumulative Energy (kWh)</span></div>
                  <div className="chart-body">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={history} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="slot" stroke="rgba(255,255,255,0.4)" fontSize={11} tickLine={false} />
                        <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} tickLine={false} />
                        <Tooltip contentStyle={TOOLTIP_STYLE} />
                        <Bar dataKey="e_kwh" name="Total Energy (kWh)" fill="#e1e6eb" radius={[3, 3, 0, 0]} barSize={12} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </section>
            </>
          )}

          {activeSlide === 'standard' && (
            <>
              <div className="glass-card slide-header-banner">
                <div className="slide-title-group">
                  <h2>Standard Monitoring</h2>
                </div>
                <span className="status-pill-badge live">1 Hz LIVE</span>
              </div>

              <section className="dual-circuit-grid">
                <CircuitStandardColumn load={load1} history={history} vKey="v1" iKey="i1" />
                <CircuitStandardColumn load={load2} history={history} vKey="v2" iKey="i2" />
              </section>
            </>
          )}

          {activeSlide === 'derived' && (
            <>
              <div className="glass-card slide-header-banner">
                <div className="slide-title-group">
                  <h2>Detailed Derived Parameter Analysis</h2>
                </div>
                <span className="status-pill-badge">v1.0</span>
              </div>

              <section className="kpi-grid-4">
                <div className="glass-card">
                  <div className="metric-label">Total Apparent Power (S)</div>
                  <div className="metric-big">{derived.s_total}<span className="metric-unit">VA</span></div>
                  <div className="metric-sub">C1: {load1.s} VA | C2: {load2.s} VA</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Total Reactive Power (Q)</div>
                  <div className="metric-big">{derived.q_total}<span className="metric-unit">VAR</span></div>
                  <div className="metric-sub">Q/S C1: {derived.qs_c1} | C2: {derived.qs_c2}</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Normalized P/V² (Conductance)</div>
                  <div className="metric-big">{derived.pv2_c1}<span className="metric-unit">mS</span></div>
                  <div className="metric-sub">C1: {derived.pv2_c1} mS | C2: {derived.pv2_c2} mS</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Power Steadiness (CV %)</div>
                  <div className="metric-big">{derived.cv_c1}<span className="metric-unit">%</span></div>
                  <div className="metric-sub">Grid V Deviation: {derived.v_dev_pct}%</div>
                </div>
              </section>

              <div className="glass-card">
                <div className="card-header">
                  <span className="card-title">
                    <Activity size={16} color="#70b6ff" />
                    Dual Power Factor Tracking: PZEM Hardware vs. Computed (True P/S)
                  </span>
                  <span className="status-pill-badge live">EDGE VECTOR VERIFIED</span>
                </div>
                <div className="dual-circuit-grid" style={{ gap: 14 }}>
                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">Industrial Load</span>
                      <span className="log-row-sub">
                        PZEM Register PF: <strong>{load1.pfMeter}</strong> &nbsp;|&nbsp; True Vector (P/S): <strong>{load1.pfCalc}</strong> &nbsp;|&nbsp;
                        ΔPF: {Math.abs(load1.pfMeter - load1.pfCalc).toFixed(3)}
                      </span>
                    </div>
                    <span className="status-pill-badge">PF CONSISTENT</span>
                  </div>
                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">Household Load</span>
                      <span className="log-row-sub">
                        PZEM Register PF: <strong>{load2.pfMeter}</strong> &nbsp;|&nbsp; True Vector (P/S): <strong>{load2.pfCalc}</strong> &nbsp;|&nbsp;
                        ΔPF: {Math.abs(load2.pfMeter - load2.pfCalc).toFixed(3)}
                      </span>
                    </div>
                    <span className="status-pill-badge live">UNITY PF</span>
                  </div>
                </div>
              </div>

              <div className="glass-card">
                <div className="card-header">
                  <span className="card-title">
                    <SlidersHorizontal size={16} color="#70b6ff" />
                    Hardware Calibration Gains (Stored in ESP32 Flash Preferences)
                  </span>
                  <span className="status-pill-badge">0.90 – 1.10</span>
                </div>
                <div className="dual-circuit-grid" style={{ gap: 14 }}>
                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">Circuit 1 Flash Gains (Namespace: pzemcal)</span>
                      <span className="log-row-sub">
                        Voltage Gain (vg): <strong>{Number(load1.voltGain || 1).toFixed(4)}</strong> &nbsp;|&nbsp;
                        Current Gain (ig): <strong>{Number(load1.currGain || 1).toFixed(4)}</strong> &nbsp;|&nbsp;
                        Power Gain (pg): <strong>{Number(load1.powGain || 1).toFixed(4)}</strong>
                      </span>
                    </div>
                    <span className="status-pill-badge">CALIBRATED</span>
                  </div>
                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">Circuit 2 Flash Gains (Namespace: pzemcal2)</span>
                      <span className="log-row-sub">
                        Voltage Gain (vg): <strong>{Number(load2.voltGain || 1).toFixed(4)}</strong> &nbsp;|&nbsp;
                        Current Gain (ig): <strong>{Number(load2.currGain || 1).toFixed(4)}</strong> &nbsp;|&nbsp;
                        Power Gain (pg): <strong>{Number(load2.powGain || 1).toFixed(4)}</strong>
                      </span>
                    </div>
                    <span className="status-pill-badge">CALIBRATED</span>
                  </div>
                </div>
              </div>

              <section className="dual-circuit-grid">
                <div className="glass-card chart-card" style={{ height: 280 }}>
                  <div className="card-header">
                    <span className="card-title">Apparent (S) vs Reactive (Q) Trajectory</span>
                  </div>
                  <div className="chart-body">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={history} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                        <XAxis dataKey="slot" stroke="rgba(255,255,255,0.4)" fontSize={11} />
                        <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} />
                        <Tooltip contentStyle={TOOLTIP_STYLE} />
                        <Area type="monotone" dataKey="s_va" name="Apparent S (VA)" stroke="#e1e6eb" fill="rgba(255,255,255,0.12)" />
                        <Area type="monotone" dataKey="q_var" name="Reactive Q (VAR)" stroke="#ff9f0a" fill="rgba(255,159,10,0.1)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="glass-card">
                  <div className="card-header">
                    <span className="card-title">Per-Channel Derived Comparison</span>
                  </div>
                  <div className="glass-list-stack">
                    <div className="glass-log-row">
                      <div className="log-row-main">
                        <span className="log-row-title">Circuit 1 Reactive Ratio (Q/S)</span>
                        <span className="log-row-sub">Inductive motor reactive signature</span>
                      </div>
                      <span className="status-pill-badge">{derived.qs_c1}</span>
                    </div>
                    <div className="glass-log-row">
                      <div className="log-row-main">
                        <span className="log-row-title">Circuit 2 Reactive Ratio (Q/S)</span>
                        <span className="log-row-sub">Resistive / household lighting bank</span>
                      </div>
                      <span className="status-pill-badge">{derived.qs_c2}</span>
                    </div>
                    <div className="glass-log-row">
                      <div className="log-row-main">
                        <span className="log-row-title">Voltage-Normalized Power (P/V²)</span>
                        <span className="log-row-sub">Immune to supply voltage swings</span>
                      </div>
                      <span className="status-pill-badge">C1: {derived.pv2_c1} | C2: {derived.pv2_c2}</span>
                    </div>
                  </div>
                </div>
              </section>
            </>
          )}

          {activeSlide === 'modes' && (
            <>
              <div className="glass-card slide-header-banner">
                <div className="slide-title-group">
                  <h2>Optimization Modes</h2>
                </div>
                <span className="status-pill-badge">SAFETY FIRST</span>
              </div>

              <div className="glass-card">
                <div className="card-header">
                  <span className="card-title">Mandatory Core Modes</span>
                </div>
                <div className="kpi-grid-3">
                  {[
                    { name: 'Monitor Only', desc: 'Continuous 1 Hz RMS & energy acquisition across both channels.' },
                    { name: 'Threshold Protection', desc: 'Local ESP32 safety cutoffs from verified component ratings.' },
                    { name: 'Anomaly Detection', desc: 'Rolling Z-score & statistical deviation watch.' },
                  ].map((m) => (
                    <div key={m.name} className="glass-log-row">
                      <div className="log-row-main">
                        <span className="log-row-title">{m.name}</span>
                        <span className="log-row-sub">{m.desc}</span>
                      </div>
                      <span className="status-pill-badge live">ALWAYS ON</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="glass-card">
                <div className="card-header">
                  <span className="card-title">Optional Optimization Modes</span>
                </div>
                <div className="glass-list-stack">
                  {[
                    { id: 2, name: 'Schedule Control (Mode 2)', desc: 'Time-window relay automation defined by user schedule.' },
                    { id: 3, name: 'Peak Load Management (Mode 3)', desc: `Alert / shed non-critical load above ${PEAK_LIMIT_W} W demand ceiling.` },
                    { id: 4, name: 'Idle / Standby Detection (Mode 4)', desc: 'Detects sustained phantom draw near empty-channel floor.' },
                    { id: 5, name: 'Energy Budget Watch (Mode 5)', desc: 'Tracks cumulative kWh against daily/monthly tariff targets.' },
                    { id: 6, name: 'Power Factor Alert (Mode 6)', desc: 'Flags sustained inductive lag when PF drops below 0.90.' },
                    { id: 8, name: 'Predictive Health Advisory (Mode 8)', desc: 'Tracks long-term drift from clean load baseline.' },
                  ].map((mode) => {
                    const enabled = heartbeat.active_modes.includes(mode.id);
                    return (
                      <div key={mode.id} className="glass-log-row">
                        <div className="log-row-main">
                          <span className="log-row-title">{mode.name}</span>
                          <span className="log-row-sub">{mode.desc}</span>
                        </div>
                        <button
                          className={`relay-action-btn ${enabled ? '' : 'off'}`}
                          onClick={() => toggleMode(mode.id)}
                        >
                          {enabled ? 'ENABLED' : 'DISABLED'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {activeSlide === 'tips' && (
            <>
              <div className="glass-card slide-header-banner">
                <div className="slide-title-group">
                  <h2>Energy Saving Tips & Cost Insights</h2>
                </div>
                <span className="status-pill-badge">TARIFF: ₹{TARIFF_INR}/kWh</span>
              </div>

              <section className="kpi-grid-3">
                <div className="glass-card">
                  <div className="metric-label">Cumulative Panel Energy</div>
                  <div className="metric-big">{derived.e_total}<span className="metric-unit">kWh</span></div>
                  <div className="metric-sub">Estimated Running Cost: ₹{derived.est_bill_inr}</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Peak Demand Utilization</div>
                  <div className="metric-big">{derived.peak_ratio}<span className="metric-unit">%</span></div>
                  <div className="metric-sub">{Math.round(derived.p_total)} W of {PEAK_LIMIT_W} W Limit</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Reactive Demand Overhead</div>
                  <div className="metric-big">{derived.q_total}<span className="metric-unit">VAR</span></div>
                  <div className="metric-sub">Apparent S: {derived.s_total} VA</div>
                </div>
              </section>

              <div className="glass-card">
                <div className="card-header">
                  <span className="card-title">Recommendations</span>
                </div>
                <div className="glass-list-stack">
                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">
                        <Lightbulb size={16} color="#70b6ff" />
                        Industrial Power Factor Optimization (PF: {load1.pfMeter})
                      </span>
                      <span className="log-row-sub">
                        {load1.pfMeter < 0.95
                          ? `Industrial Load draws ${load1.q} VAR reactive power. Adding shunt capacitor compensation reduces line current.`
                          : 'Industrial load power factor is operating within high efficiency bounds.'}
                      </span>
                    </div>
                    <span className={`status-pill-badge ${load1.pfMeter < 0.95 ? 'warn' : 'live'}`}>
                      {load1.pfMeter < 0.95 ? 'PF ADVISORY' : 'OPTIMAL'}
                    </span>
                  </div>

                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">
                        <Clock size={16} color="#70b6ff" />
                        Off-Peak Load Scheduling
                      </span>
                      <span className="log-row-sub">
                        Household load accounts for {derived.household_share}% ({load2.p} W) of active load. Enabling Mode 2 Schedule prevents idle overnight consumption.
                      </span>
                    </div>
                    <span className="status-pill-badge">SCHEDULE TIP</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeSlide === 'health' && (
            <>
              <div className="glass-card slide-header-banner">
                <div className="slide-title-group">
                  <h2>Load Health Monitoring</h2>
                </div>
                <span className="status-pill-badge live">SYSTEM: {derived.avg_health}%</span>
              </div>

              <section className="dual-circuit-grid">
                {[
                  { ch: 1, data: load1 },
                  { ch: 2, data: load2 },
                ].map(({ ch, data }) => (
                  <div key={ch} className="glass-card">
                    <div className="card-header">
                      <span className="card-title">{data.name}</span>
                      <span className={`status-pill-badge ${data.fault ? 'fault' : 'live'}`}>
                        {data.fault ? 'FAULT DETECTED' : 'HEALTHY'}
                      </span>
                    </div>
                    <div className="dual-metrics" style={{ marginBottom: 14 }}>
                      <div>
                        <div className="metric-label">Equipment Health Score</div>
                        <div className="metric-big">{data.health}<span className="metric-unit">%</span></div>
                        <div className="metric-sub">Baseline RMS Consistency</div>
                      </div>
                      <div>
                        <div className="metric-label">Anomaly Deviation</div>
                        <div className="metric-big">
                          {Number((data.anomaly * 100).toFixed(1))}
                          <span className="metric-unit">%</span>
                        </div>
                        <div className="metric-sub">Rolling Z-Score Watch</div>
                      </div>
                    </div>
                    <div className="glass-list-stack">
                      <div className="glass-log-row">
                        <span className="log-row-sub">Auto-Retry Counter</span>
                        <strong>{data.retry_count} / 3 Retries</strong>
                      </div>

                      <div className="glass-log-row">
                        <span className="log-row-sub">Relay Contact Integrity Indicator</span>
                        <strong style={{ color: data.relayMismatch ? '#ff453a' : '#30d158' }}>
                          {data.relayMismatch
                            ? 'ALERT: SSR LEAKAGE / CONTACT WELD DETECTED'
                            : 'SSR CONTACT NORMAL — NO LEAKAGE'}
                        </strong>
                      </div>
                    </div>
                  </div>
                ))}
              </section>
            </>
          )}

          {activeSlide === 'ai_summary' && (
            <>
              <div className="glass-card slide-header-banner">
                <div className="slide-title-group">
                  <h2>AI Based Summary & Executive Diagnostics</h2>
                </div>
                <span className="status-pill-badge">ADVISORY ONLY</span>
              </div>

              <section className="kpi-grid-3">
                <div className="glass-card">
                  <div className="metric-label">Combined Active Load</div>
                  <div className="metric-big">{Math.round(derived.p_total)}<span className="metric-unit">W</span></div>
                  <div className="metric-sub">Mean Grid Voltage: {derived.v_avg} V</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Peak Anomaly Index</div>
                  <div className="metric-big">{derived.max_anomaly_pct}<span className="metric-unit">%</span></div>
                  <div className="metric-sub">Below 15% Threshold</div>
                </div>
                <div className="glass-card">
                  <div className="metric-label">Active Optional Modes</div>
                  <div className="metric-big">{heartbeat.active_modes.length}</div>
                  <div className="metric-sub">Confirmed Rules Active</div>
                </div>
              </section>

              <div className="glass-card">
                <div className="card-header">
                  <span className="card-title">
                    <BrainCircuit size={18} color="#70b6ff" />
                    System Summary
                  </span>
                </div>
                <div className="glass-list-stack">
                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">Industrial Load</span>
                      <span className="log-row-sub">
                        Operating at {load1.p} W ({load1.i} A, PF {load1.pfMeter}, Q/S {derived.qs_c1}). Steadiness CV is {derived.cv_c1}%.
                      </span>
                    </div>
                    <span className="status-pill-badge live">STEADY</span>
                  </div>

                  <div className="glass-log-row">
                    <div className="log-row-main">
                      <span className="log-row-title">Household Load</span>
                      <span className="log-row-sub">
                        Operating at {load2.p} W ({load2.i} A, PF {load2.pfMeter}, Q/S {derived.qs_c2}). Near-unity power factor.
                      </span>
                    </div>
                    <span className="status-pill-badge live">NEAR-UNITY PF</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </>
  );
}