import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface WorkoutChartPoint {
  splitLabel: string;
  value: number | null;
}

interface WorkoutChartProps {
  data: WorkoutChartPoint[];
  color?: string;
  unit?: string;
  yDomain?: [number | "auto", number | "auto"];
  /** When true, a lower value is "better" (e.g. pace) - inverts the Y axis so improvement reads as "up". */
  invertY?: boolean;
}

export function WorkoutChart({ data, color = "#3ddc97", unit = "", yDomain, invertY = false }: WorkoutChartProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" vertical={false} />
        <XAxis
          dataKey="splitLabel"
          tick={{ fill: "#8b93a7", fontSize: 12 }}
          axisLine={{ stroke: "#262c3d" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "#8b93a7", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          domain={yDomain ?? ["auto", "auto"]}
          reversed={invertY}
          width={44}
        />
        <Tooltip
          contentStyle={{
            background: "#1a1f2e",
            border: "1px solid #262c3d",
            borderRadius: 8,
            fontSize: 13,
          }}
          labelStyle={{ color: "#8b93a7" }}
          formatter={(value: number) => [`${value}${unit}`, undefined]}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={{ r: 3, fill: color }}
          activeDot={{ r: 5 }}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
