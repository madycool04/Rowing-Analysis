import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface HrZoneDatum {
  zone: number;
  label: string;
  pct: number;
  time_s: number;
}

const ZONE_COLORS = ["#4f6a8f", "#3ddc97", "#e0a94a", "#e07a3f", "#e0575b"];

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function HRChart({ zones }: { zones: HrZoneDatum[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={zones} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#262c3d" horizontal={false} />
        <XAxis
          type="number"
          domain={[0, 100]}
          tick={{ fill: "#8b93a7", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          unit="%"
        />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: "#8b93a7", fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip
          contentStyle={{
            background: "#1a1f2e",
            border: "1px solid #262c3d",
            borderRadius: 8,
            fontSize: 13,
          }}
          labelStyle={{ color: "#e8eaf0" }}
          formatter={(value, _name, item) => [
            `${Number(value).toFixed(0)}% (${formatDuration((item?.payload as HrZoneDatum | undefined)?.time_s ?? 0)})`,
            "Time in zone",
          ]}
        />
        <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
          {zones.map((z) => (
            <Cell key={z.zone} fill={ZONE_COLORS[(z.zone - 1) % ZONE_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
