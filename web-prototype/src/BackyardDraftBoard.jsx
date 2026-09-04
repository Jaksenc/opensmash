import { useEffect, useMemo, useState } from "react";
import "./backyard.css";

const CLASS_COLORS = {
  captain: "#ffd166",
  rushdown: "#ef476f",
  zoner: "#06d6a0",
  tricky: "#c77dff",
  control: "#4cc9f0",
  heavy: "#f78c6b",
};

function salaryFmt(n) {
  if (n == null) return "—";
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

// Generated sprite pack (scripts/backyard_sprites.py) when present,
// backyard ref art otherwise (works before sprites are built).
function SpriteImg({ slug, fallback, alt }) {
  const [src, setSrc] = useState(`/backyard-art/${slug}/portrait_medium.png`);
  useEffect(() => setSrc(`/backyard-art/${slug}/portrait_medium.png`), [slug]);
  return (
    <img
      src={src}
      onError={() => { if (src !== fallback) setSrc(fallback); }}
      alt={alt}
      loading="lazy"
    />
  );
}

export default function BackyardDraftBoard({ onQuickMatch }) {
  const [fighters, setFighters] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("All");
  const [team, setTeam] = useState([]);
  const CAP = 400000;

  useEffect(() => {
    let cancelled = false;
    fetch("/api/backyard-starter")
      .then((r) => {
        if (!r.ok) throw new Error(`Draft board unavailable (${r.status})`);
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setFighters(data.fighters || []);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => { cancelled = true; };
  }, []);

  const positions = useMemo(() => {
    if (!fighters) return ["All"];
    return ["All", ...new Set(fighters.map((f) => f.position))];
  }, [fighters]);

  const visible = useMemo(() => {
    if (!fighters) return [];
    return filter === "All" ? fighters : fighters.filter((f) => f.position === filter);
  }, [fighters, filter]);

  const spent = team.reduce((sum, slug) => {
    const f = (fighters || []).find((x) => x.slug === slug);
    return sum + (f?.salary || 0);
  }, 0);
  const remaining = CAP - spent;

  function toggleDraft(slug) {
    setTeam((prev) => (prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug]));
  }

  return (
    <section className="byd-board" aria-labelledby="byd-title">
      <div className="byd-head">
        <div>
          <p className="byd-eyebrow">Backyard Designers × DesignCrit</p>
          <h2 id="byd-title">Draft board — starter 12</h2>
          <p className="byd-sub">
            Seven-slot dream team, 400k follower cap. Art-only preview works with no ROM or API keys;
            full 3D bundles unlock quick match when baked.
          </p>
        </div>
        <div className="byd-cap" aria-live="polite">
          <span className="byd-cap-spent">{spent.toLocaleString()}</span>
          <span className="byd-cap-of"> / {CAP.toLocaleString()} spent</span>
          <span className={remaining < 0 ? "byd-cap-over" : "byd-cap-left"}>
            {remaining < 0 ? `${Math.abs(remaining).toLocaleString()} over` : `${remaining.toLocaleString()} left`}
          </span>
          {team.length > 0 && <button className="byd-clear" type="button" onClick={() => setTeam([])}>Clear team ({team.length})</button>}
        </div>
      </div>

      <div className="byd-filters" role="tablist" aria-label="Filter by position">
        {positions.map((p) => (
          <button
            key={p}
            role="tab"
            aria-selected={filter === p}
            className={filter === p ? "byd-filter is-active" : "byd-filter"}
            type="button"
            onClick={() => setFilter(p)}
          >
            {p}
          </button>
        ))}
      </div>

      {error && <p className="byd-error">{error} — run <code>python3 scripts/fetch_backyard_roster.py --starter-only</code> then restart <code>pnpm dev:safe</code>.</p>}
      {!fighters && !error && <p className="byd-loading">Scouting the yard…</p>}

      <div className="byd-grid">
        {(visible || []).map((f) => {
          const drafted = team.includes(f.slug);
          const color = CLASS_COLORS[f.positionClass] || "#fff";
          return (
            <article key={f.slug} className={drafted ? "byd-card is-drafted" : "byd-card"}>
              <button className="byd-card-main" type="button" onClick={() => toggleDraft(f.slug)} aria-pressed={drafted}>
                <span className="byd-art">
                  <SpriteImg slug={f.slug} fallback={f.art} alt={`${f.display} backyard art`} />
                </span>
                <span className="byd-badges">
                  <span className="byd-pos">{f.position}</span>
                  {f.positionClass && (
                    <span className="byd-class" style={{ borderColor: color, color }}>
                      {f.positionLabel || f.positionClass} · {f.base}
                    </span>
                  )}
                </span>
                <span className="byd-name">{f.display} <span className="byd-nick">{f.nick}</span></span>
                <span className="byd-meta">@{f.handle} · {salaryFmt(f.salary)} followers</span>
                <span className="byd-playstyle">{f.playstyle}</span>
              </button>
              <div className="byd-actions">
                <button
                  className="byd-draft"
                  type="button"
                  onClick={() => toggleDraft(f.slug)}
                >
                  {drafted ? "Undraft" : "Draft"}
                </button>
                <a className="byd-scout" href={f.rosterUrl} target="_blank" rel="noreferrer">Scout ↗</a>
                {onQuickMatch && (
                  <button className="byd-quick" type="button" onClick={() => onQuickMatch(f)}>
                    Quick match ↗
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
