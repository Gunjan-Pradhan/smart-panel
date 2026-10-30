/**
 * Metric: small labelled value tile.
 */
export function fmt(value, decimals = 2) {
  if (value === null || value === undefined || value === "") return "--";
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(decimals) : "--";
}

export default function Metric({ label, value, unit, decimals }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>
        {fmt(value, decimals)}
        {unit ? ` ${unit}` : ""}
      </strong>
    </div>
  );
}

