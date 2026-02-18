import styles from "./EmotionLegend.module.css";

export const EMOTION_COLORS = {
  happy: "#f59e0b",
  neutral: "#64748b",
  sad: "#2563eb",
  angry: "#dc2626",
  fear: "#7c3aed",
  surprise: "#10b981",
  disgust: "#16a34a",
};

function EmotionLegend() {
  return (
    <div className={styles.legendRow}>
      {Object.entries(EMOTION_COLORS).map(([label, color]) => (
        <span key={label} className={styles.item}>
          <span className={styles.swatch} style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

export default EmotionLegend;
