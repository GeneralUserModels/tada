import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { RewardPoint } from "../../context/AppContext";

interface Props {
  data: RewardPoint[];
  elboScore: string | null;
}

export function RewardsChart({ data, elboScore }: Props) {
  return (
    <section className="glass-card flex-1" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card-header">
        <h2>Rewards</h2>
        <div className="chart-legend">
          <span className="legend-item">
            <span className="legend-dot legend-accuracy"></span>Accuracy
          </span>
          <span className="legend-item">
            <span className="legend-dot legend-formatting"></span>Formatting
          </span>
          <span className="legend-item">
            <span className="legend-dot legend-combined"></span>Combined
          </span>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 22, left: 36 }}>
          <CartesianGrid stroke="rgba(132,177,121,0.12)" />
          <XAxis
            dataKey="step"
            tick={{ fill: "#9BA896", fontSize: 10 }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#9BA896", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--glass)",
              border: "1px solid var(--glass-border)",
              borderRadius: "8px",
              fontSize: "11px",
            }}
          />
          <Line
            type="monotone"
            dataKey="accuracy"
            stroke="#5DA34E"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="formatting"
            stroke="#C9944B"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="combined"
            stroke="#2C3A28"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      </div>
      <div className="elbo-badge">{elboScore ?? "ELBO \u2014"}</div>
    </section>
  );
}
