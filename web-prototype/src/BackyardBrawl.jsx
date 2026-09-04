import { useEffect, useRef, useState } from "react";
import "./backyard.css";

// Backyard Brawl: a tiny canvas platform fighter for the starter-12 roster.
// No ROM, no engine, no keys — portraits + stock sprites as fighters,
// position classes as kits, Smash-style % damage and blast KOs.
//
// Kits (special, cooldown 180 frames):
//   rushdown fox      DASH STRIKE  fast long lunge
//   zoner link        CURSOR       pixel-arrow projectile
//   tricky purin/ness SNOOZE       slow wave (halves foe speed)
//   control yoshi     EGG SHELL    2s of armor
//   heavy donkey      BEAM SLAM    big close AoE
//   captain mario     SPIRAL       arcing football
//
// Controls P1: A/D move · W jump (x2) · J jab · K special · Esc exits.

const W = 960;
const H = 540;
const FLOOR_Y = 460;
const MAIN = { x0: 180, x1: 780 };
const PLATS = [
  { x0: 120, x1: 320, y: 340 },
  { x0: 640, x1: 840, y: 340 },
];
const GRAV = 0.7;
const STOCKS = 3;
const ROUND_FRAMES = 60 * 60;

const KITS = {
  rushdown: { speed: 4.6, jump: 13.5, special: "dash", label: "DASH STRIKE" },
  zoner: { speed: 4.0, jump: 13.0, special: "cursor", label: "CURSOR" },
  tricky: { speed: 3.9, jump: 13.2, special: "snooze", label: "SNOOZE" },
  control: { speed: 4.0, jump: 12.6, special: "egg", label: "EGG SHELL" },
  heavy: { speed: 3.4, jump: 12.0, special: "slam", label: "BEAM SLAM" },
  captain: { speed: 4.2, jump: 13.0, special: "spiral", label: "SPIRAL" },
};

function kitFor(f) {
  return KITS[f?.positionClass] || KITS.captain;
}

function makeFighter(f, x, dir) {
  return {
    f, x, y: FLOOR_Y - 60, vx: 0, vy: 0, dir,
    pct: 0, stocks: STOCKS, jumps: 0, onGround: false,
    stun: 0, cool: 0, armor: 0, slow: 0, dead: 0, flash: 0,
  };
}

export default function BackyardBrawl({ p1, cpu, onExit }) {
  const canvasRef = useRef(null);
  const [result, setResult] = useState("");
  const [round, setRound] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const imgs = new Map();
    for (const f of [p1, cpu]) {
      const img = new Image();
      img.src = `/backyard-art/${f.slug}/portrait_medium.png`;
      img.onerror = () => { img.src = f.art; };
      imgs.set(f.slug, img);
    }
    try {
      new Audio(`/backyard-art/${p1.slug}/announcer.wav`).play().catch(() => {});
    } catch { /* silent */ }

    const S = {
      a: makeFighter(p1, 300, 1),
      b: makeFighter(cpu, 660, -1),
      shots: [],
      waves: [],
      frame: 0,
      over: "",
      keys: {},
      go: 0,
    };

    function groundAt(x, y, vy) {
      if (vy < 0) return null;
      if (y <= FLOOR_Y && x >= MAIN.x0 && x <= MAIN.x1) return FLOOR_Y;
      for (const p of PLATS) {
        if (y <= p.y && y + vy >= p.y && x >= p.x0 && x <= p.x1) return p.y;
      }
      return null;
    }

    function hit(target, dmg, kbx, kby) {
      if (target.armor > 0 || target.dead > 0 || S.over) return;
      target.pct += dmg;
      const mult = 1 + target.pct / 90;
      target.vx = kbx * mult;
      target.vy = kby * mult;
      target.stun = Math.min(50, 10 + kbx * mult * 2.2);
      target.flash = 8;
      target.onGround = false;
    }

    function jab(m) {
      const foe = m === S.a ? S.b : S.a;
      m.lunge = 6;
      if (Math.abs(foe.x - m.x) < 62 && Math.abs(foe.y - m.y) < 70) {
        hit(foe, 6, 4.2 * m.dir, -3.2);
      }
    }

    function special(m) {
      if (m.cool > 0 || S.over) return;
      const foe = m === S.a ? S.b : S.a;
      const kit = kitFor(m.f);
      m.cool = 180;
      if (kit.special === "dash") {
        m.vx = 11 * m.dir;
        m.dashHit = true;
      } else if (kit.special === "cursor" || kit.special === "spiral") {
        S.shots.push({
          x: m.x + 20 * m.dir, y: m.y - 30, vx: 8 * m.dir,
          vy: kit.special === "spiral" ? -3.5 : 0, grav: kit.special === "spiral" ? 0.25 : 0,
          from: m, dmg: kit.special === "spiral" ? 11 : 9, color: kit.special === "spiral" ? "#ffd166" : "#4cc9f0",
        });
      } else if (kit.special === "snooze") {
        S.waves.push({ x: m.x, y: m.y - 20, r: 10, from: m });
      } else if (kit.special === "egg") {
        m.armor = 120;
      } else if (kit.special === "slam") {
        if (Math.abs(foe.x - m.x) < 120 && Math.abs(foe.y - m.y) < 110) {
          hit(foe, 14, 7.5 * (foe.x >= m.x ? 1 : -1), -6);
        }
        m.shock = 20;
      }
    }

    function stepFighter(m, foe, input) {
      const kit = kitFor(m.f);
      if (m.dead > 0) {
        // respawn countdown: gravity still applies, no control yet
        m.dead -= 1;
        if (m.dead > 0) {
          if (m.cool > 0) m.cool -= 1;
          if (m.armor > 0) m.armor -= 1;
          m.vy = Math.min(m.vy + GRAV, 16);
          m.y += m.vy;
          const g = groundAt(m.x, m.y, m.vy);
          if (g !== null && m.vy >= 0) {
            m.y = g; m.vy = 0; m.onGround = true; m.jumps = 0; m.dead = 0;
          }
          return;
        }
      }
      const slow = m.slow > 0 ? 0.55 : 1;
      if (m.slow > 0) m.slow -= 1;
      if (m.cool > 0) m.cool -= 1;
      if (m.armor > 0) m.armor -= 1;
      if (m.flash > 0) m.flash -= 1;
      if (m.shock > 0) m.shock -= 1;
      if (m.lunge > 0) m.lunge -= 1;

      const spd = kit.speed * slow;
      if (m.stun > 0) {
        m.stun -= 1;
      } else if (input) {
        if (input.left) { m.vx = Math.max(m.vx - 0.9 * slow, -spd); m.dir = -1; }
        if (input.right) { m.vx = Math.min(m.vx + 0.9 * slow, spd); m.dir = 1; }
        if (!input.left && !input.right && m.onGround) m.vx *= 0.78;
      } else if (m.onGround) m.vx *= 0.86;

      // dash strike connects mid-lunge
      if (m.dashHit && Math.abs(foe.x - m.x) < 58 && Math.abs(foe.y - m.y) < 70) {
        m.dashHit = false;
        hit(foe, 10, 6.5 * m.dir, -4);
      }
      if (m.dashHit && Math.abs(m.vx) < 3) m.dashHit = false;

      m.vy = Math.min(m.vy + GRAV, 16);
      m.x += m.vx;
      const g = groundAt(m.x, m.y, m.vy);
      if (g !== null && m.vy >= 0) {
        m.y = g; m.vy = 0; m.onGround = true; m.jumps = 0;
      } else {
        m.y += m.vy;
        m.onGround = false;
      }
      if (m.onGround) m.vx *= 0.985;

      if (m.x < -40 || m.x > W + 40 || m.y < -60 || m.y > H + 80) {
        if (m.dead > 0) {
          // respawning above the stage — not a new KO
          m.x = 480; m.y = -40; m.vx = 0; m.vy = 2;
        } else {
          m.stocks -= 1;
          m.vx = 0; m.vy = 0;
          if (m.stocks <= 0) {
            S.over = m === S.a ? cpu.display : p1.display;
          } else {
            m.dead = 90;
            m.x = 480; m.y = -40; m.vx = 0; m.vy = 2;
            m.pct = 0; m.armor = 120;
          }
        }
      }
    }

    function cpuInput() {
      const m = S.b, foe = S.a;
      const inp = { left: false, right: false };
      if (m.stun > 0 || S.over) return inp;
      const dx = foe.x - m.x;
      if (S.frame % 18 === 0) {
        S.cpuPlan = {
          chase: Math.abs(dx) > 52,
          toward: dx > 0 ? "right" : "left",
          jump: foe.y < m.y - 60 || Math.random() < 0.12 || m.x < MAIN.x0 || m.x > MAIN.x1,
          jab: Math.abs(dx) < 58 && Math.abs(foe.y - m.y) < 70,
          special: Math.abs(dx) > 130 && Math.abs(dx) < 480 && m.cool === 0 && Math.random() < 0.7,
        };
        // recover: steer back to stage
        if (m.x < MAIN.x0 - 30) S.cpuPlan = { ...S.cpuPlan, chase: true, toward: "right" };
        if (m.x > MAIN.x1 + 30) S.cpuPlan = { ...S.cpuPlan, chase: true, toward: "left" };
        if (m.y > FLOOR_Y + 40) S.cpuPlan.jump = true;
      }
      const p = S.cpuPlan || {};
      if (p.chase) inp[p.toward] = true;
      // jumps steer continuously; attacks fire once when the plan is made
      if (p.jump && (m.onGround || m.jumps < 2)) {
        m.vy = m.onGround ? -kitFor(m.f).jump : -11;
        m.onGround = false; m.jumps += 1;
      }
      if (S.frame % 18 === 0) {
        if (p.jab) jab(m);
        if (p.special) special(m);
      }
      return inp;
    }

    function onKey(e, down) {
      const k = e.key.toLowerCase();
      if (["a", "d", "w", "j", "k", " "].includes(k)) e.preventDefault();
      if (k === "escape" && down) { onExit(); return; }
      S.keys[k] = down;
      if (!down || S.over) return;
      if (k === "w") {
        const m = S.a;
        if (m.stun === 0 && (m.onGround || m.jumps < 2)) {
          m.vy = m.onGround ? -kitFor(m.f).jump : -11;
          m.onGround = false; m.jumps += 1;
        }
      }
      if (k === "j") { if (S.a.stun === 0) jab(S.a); }
      if (k === "k") special(S.a);
    }
    const kd = (e) => onKey(e, true);
    const ku = (e) => onKey(e, false);
    window.addEventListener("keydown", kd);
    window.addEventListener("keyup", ku);

    function drawFighter(m) {
      const img = imgs.get(m.f.slug);
      const R = 26;
      ctx.save();
      if (m.flash > 0 && m.flash % 4 < 2) ctx.globalAlpha = 0.45;
      if (m.armor > 0) {
        ctx.strokeStyle = "#ffd166";
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(m.x, m.y - 30, R + 6, 0, 7); ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(m.x, m.y - 30, R, 0, 7);
      ctx.fillStyle = "#171311"; ctx.fill();
      ctx.clip();
      if (img && img.complete && img.naturalWidth) ctx.drawImage(img, m.x - R, m.y - 30 - R, R * 2, R * 2);
      ctx.restore();
      ctx.fillStyle = "#f3eee4";
      ctx.font = "700 13px 'DM Mono', monospace";
      ctx.textAlign = "center";
      ctx.fillText(`${m.f.display}  ${Math.round(m.pct)}%`, m.x, m.y + 16);
      if (m.cool > 0) {
        ctx.fillStyle = "#6f6963";
        ctx.fillRect(m.x - 20, m.y + 20, 40 * (1 - m.cool / 180), 3);
      } else {
        ctx.fillStyle = "#ffd166";
        ctx.font = "700 10px 'DM Mono', monospace";
        ctx.fillText(kitFor(m.f).label + " (K)", m.x, m.y + 32);
      }
    }

    let raf = 0;
    function frame() {
      S.frame += 1;
      const input = {
        left: !!S.keys["a"],
        right: !!S.keys["d"],
      };
      stepFighter(S.a, S.b, input);
      stepFighter(S.b, S.a, cpuInput());

      // projectiles
      for (const s of S.shots) {
        s.x += s.vx; s.y += s.vy; s.vy += s.grav || 0;
        const foe = s.from === S.a ? S.b : S.a;
        if (!s.hit && Math.abs(foe.x - s.x) < 30 && Math.abs(foe.y - 30 - s.y) < 40) {
          s.hit = true;
          hit(foe, s.dmg, 5.5 * Math.sign(s.vx || 1), -3.5);
        }
      }
      S.shots = S.shots.filter((s) => !s.hit && s.x > -30 && s.x < W + 30 && s.y < H + 30);
      // snooze waves
      for (const wv of S.waves) {
        wv.r += 4;
        const foe = wv.from === S.a ? S.b : S.a;
        if (!wv.hit && Math.hypot(foe.x - wv.x, foe.y - 20 - wv.y) < wv.r) {
          wv.hit = true;
          foe.slow = 240;
          hit(foe, 4, 2 * (foe.x >= wv.x ? 1 : -1), -2);
        }
      }
      S.waves = S.waves.filter((wv) => wv.r < 150 && !wv.hit);

      if (!S.over && S.frame >= ROUND_FRAMES) {
        const [a, b] = [S.a, S.b];
        S.over = a.stocks !== b.stocks
          ? (a.stocks > b.stocks ? p1.display : cpu.display)
          : a.pct <= b.pct ? p1.display : cpu.display;
      }

      // ---- draw ----
      const bg = ctx.createLinearGradient(0, 0, 0, H);
      bg.addColorStop(0, "#1b1430"); bg.addColorStop(0.7, "#0e0c0b"); bg.addColorStop(1, "#090807");
      ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#ffd166";
      ctx.font = "900 15px 'Barlow Condensed', sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("★ BACKYARD BRAWL ★", W / 2, 24);
      // platforms
      ctx.fillStyle = "#3a2f28";
      ctx.fillRect(MAIN.x0, FLOOR_Y, MAIN.x1 - MAIN.x0, 14);
      ctx.fillStyle = "#57493a";
      ctx.fillRect(MAIN.x0, FLOOR_Y, MAIN.x1 - MAIN.x0, 3);
      for (const p of PLATS) {
        ctx.fillStyle = "#3a2f28"; ctx.fillRect(p.x0, p.y, p.x1 - p.x0, 10);
        ctx.fillStyle = "#57493a"; ctx.fillRect(p.x0, p.y, p.x1 - p.x0, 2);
      }
      // shots + waves + shocks
      for (const s of S.shots) {
        ctx.fillStyle = s.color;
        ctx.beginPath(); ctx.arc(s.x, s.y, 8, 0, 7); ctx.fill();
      }
      for (const wv of S.waves) {
        ctx.strokeStyle = "#c77dff"; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(wv.x, wv.y, wv.r, 0, 7); ctx.stroke();
      }
      for (const m of [S.a, S.b]) {
        if (m.shock > 0) {
          ctx.strokeStyle = "#f78c6b"; ctx.lineWidth = 4;
          ctx.beginPath(); ctx.arc(m.x, m.y - 30, 44 + (20 - m.shock), 0, 7); ctx.stroke();
        }
      }
      drawFighter(S.a);
      drawFighter(S.b);
      // HUD
      ctx.textAlign = "left";
      ctx.fillStyle = "#f3eee4";
      ctx.font = "700 14px 'DM Mono', monospace";
      ctx.fillText(`P1 ${"●".repeat(S.a.stocks)}${"○".repeat(Math.max(0, STOCKS - S.a.stocks))}`, 16, 30);
      ctx.textAlign = "right";
      ctx.fillText(`${"●".repeat(S.b.stocks)}${"○".repeat(Math.max(0, STOCKS - S.b.stocks))} CPU`, W - 16, 30);
      ctx.textAlign = "center";
      ctx.fillStyle = "#8d847a";
      const t = Math.max(0, Math.ceil((ROUND_FRAMES - S.frame) / 60));
      ctx.fillText(`0:${String(t).padStart(2, "0")}`, W / 2, 46);

      if (S.over && !result) {
        setResult(S.over);
      }
      if (!S.over) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("keydown", kd);
      window.removeEventListener("keyup", ku);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [round]);

  function rematch() {
    setResult("");
    setRound((r) => r + 1); // re-runs the effect: fresh fighters, same matchup
  }

  return (
    <section className="byd-brawl" aria-label="Backyard Brawl">
      <canvas ref={canvasRef} width={W} height={H} className="byd-brawl-canvas" tabIndex={0} />
      <div className="byd-brawl-bar">
        <span className="byd-brawl-hint">A/D move · W jump ×2 · J jab · K {kitFor(p1).label} · Esc exits</span>
        <span className="byd-brawl-match">{p1.display} vs {cpu.display} (CPU)</span>
        <button type="button" className="byd-clear" onClick={onExit}>Exit</button>
      </div>
      {result && (
        <div className="byd-brawl-result" role="status">
          <p>{result} wins!</p>
          <div>
            <button type="button" className="byd-draft" onClick={rematch}>Rematch</button>
            <button type="button" className="byd-draft" onClick={onExit}>Back to draft</button>
          </div>
        </div>
      )}
    </section>
  );
}
