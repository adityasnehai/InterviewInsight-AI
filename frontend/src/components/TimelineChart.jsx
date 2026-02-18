import {
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import styles from "./TimelineChart.module.css";

function TimelineChart({
  title,
  data,
  lines,
  xKey = "timestamp",
  yLabel,
  onPointSelect,
  showBrush = true,
}) {
  const activeLines = lines.filter((item) => !item.hidden);

  return (
    <section className={styles.chartCard}>
      <div className={styles.chartHeading}>
        <h3>{title}</h3>
      </div>
      <div className={styles.chartBody}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 14, right: 24, left: 8, bottom: 8 }}
            onClick={(state) => {
              if (!onPointSelect || !state?.activePayload?.length) {
                return;
              }
              onPointSelect(state.activePayload[0].payload);
            }}
          >
            <CartesianGrid strokeDasharray="4 4" stroke="#cbd5e1" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft" } : undefined} />
            <Tooltip />
            <Legend />
            {activeLines.map((line) => (
              <Line
                key={line.key}
                type="monotone"
                dataKey={line.key}
                stroke={line.color}
                strokeWidth={2.2}
                dot={false}
                name={line.label}
                connectNulls
              />
            ))}
            {showBrush ? <Brush dataKey={xKey} height={20} stroke="#0f766e" travellerWidth={10} /> : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export default TimelineChart;
