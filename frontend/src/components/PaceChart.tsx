import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface PaceChartPoint {
  date: string;
  value: number;
  label?: string;
}

interface PaceChartProps {
  data: PaceChartPoint[];
  color?: string;
  /** Formats the raw numeric value for the tooltip/axis (e.g. seconds -> "1:52.3"). */
  formatValue?: (value: number) => string;
  /** Lower values read as improvement (pace, time) - inverts the axis so gains trend upward visually. */
  invertY?: boolean;
}

export function PaceChart({ data, color = "#3ddc97", formatValue, invertY = true }: PaceChartProps) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: "#8b93a7", fontSize: 12 }}
          axisLine={{ stroke: "#262c3d" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "#8b93a7", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          reversed={invertY}
          width={52}
          tickFormatter={(v: number) => (formatValue ? formatValue(v) : String(v))}
        />
        <Tooltip
          contentStyle={{
            background: "#1a1f2e",
            border: "1px solid #262c3d",
            borderRadius: 8,
            fontSize: 13,
          }}
          labelStyle={{ color: "#8b93a7" }}
          formatter={(value: number) => [formatValue ? formatValue(value) : value, undefined]}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={{ r: 3, fill: color }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
