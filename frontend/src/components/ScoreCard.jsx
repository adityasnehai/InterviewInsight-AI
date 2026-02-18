import styles from "./ScoreCard.module.css";

function ScoreCard({ title, score, subtitle, icon }) {
  return (
    <article className={styles.card}>
      <div className={styles.headerRow}>
        <p>{title}</p>
        {icon ? <span className={styles.icon}>{icon}</span> : null}
      </div>
      <h3>{Number.isFinite(score) ? `${score.toFixed(1)}%` : "-"}</h3>
      {subtitle ? <small>{subtitle}</small> : null}
    </article>
  );
}

export default ScoreCard;
