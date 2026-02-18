import { EMOTION_COLORS } from "./EmotionLegend";
import styles from "./SegmentCard.module.css";

function SegmentCard({ segment, onReplay }) {
  const emotionAverages = Object.entries(segment.emotionAverages || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);

  const pitch = Number(segment.speechQualityMetrics?.pitch || 0);
  const speakingRate = Number(segment.speechQualityMetrics?.speaking_rate || 0);

  return (
    <article className={styles.card}>
      <div className={styles.headerRow}>
        <div>
          <h4>{segment.label}</h4>
          <p>
            {segment.startTime.toFixed(1)}s - {segment.endTime.toFixed(1)}s
          </p>
        </div>
        <button type="button" onClick={() => onReplay(segment.startTime, segment.endTime)}>
          Play Segment
        </button>
      </div>

      <div className={styles.grid}>
        <p>
          Engagement <strong>{segment.engagementScore.toFixed(1)}%</strong>
        </p>
        <p>
          Speech Fluency <strong>{segment.speechFluency.toFixed(1)}%</strong>
        </p>
        <p>
          Text Relevance <strong>{segment.textRelevanceScore.toFixed(1)}%</strong>
        </p>
        <p>
          Pitch <strong>{pitch.toFixed(1)}</strong>
        </p>
        <p>
          Speaking Rate <strong>{speakingRate.toFixed(1)} WPM</strong>
        </p>
        <p>
          Dominant Emotion <strong style={{ color: EMOTION_COLORS[segment.dominantEmotion] || "#334155" }}>{segment.dominantEmotion}</strong>
        </p>
      </div>

      <div className={styles.emotionsRow}>
        {emotionAverages.map(([emotion, value]) => (
          <span key={emotion}>
            {emotion}: <strong>{(Number(value) * 100).toFixed(1)}%</strong>
          </span>
        ))}
      </div>
    </article>
  );
}

export default SegmentCard;
