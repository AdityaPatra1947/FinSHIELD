"use client";
import { useEffect, useRef } from "react";

/** Finn the fox: a friendly fraud guard. Suspicious transactions bounce off his shield; approved ones drift past. */
const CORAL = "#EF8557", CORAL_D = "#c9622f", BLUE = "#226192", INK = "#16324a", IVORY = "#F7F1E6", SAND = "#DFD8CA";

export default function HeroArt() {
  const ref = useRef<SVGSVGElement>(null);

  // eyes follow the pointer a little (skipped for reduced motion)
  useEffect(() => {
    const svg = ref.current;
    if (!svg || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const move = (e: PointerEvent) => {
      const r = svg.getBoundingClientRect();
      const dx = (e.clientX - (r.left + r.width / 2)) / window.innerWidth;
      const dy = (e.clientY - (r.top + r.height * 0.45)) / window.innerHeight;
      svg.style.setProperty("--px", `${Math.max(-1, Math.min(1, dx * 2.2)) * 4}px`);
      svg.style.setProperty("--py", `${Math.max(-1, Math.min(1, dy * 2.2)) * 3}px`);
    };
    window.addEventListener("pointermove", move);
    return () => window.removeEventListener("pointermove", move);
  }, []);

  return (
    <svg ref={ref} className="finn" viewBox="0 0 560 640" role="img"
      aria-label="Finn, a friendly fox guard, holds a blue shield with a check mark. Suspicious transactions bounce off it while approved ones pass by.">
      <defs>
        <radialGradient id="glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor={CORAL} stopOpacity=".55" /><stop offset="1" stopColor={CORAL} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* backdrop */}
      <circle cx="280" cy="330" r="246" fill={SAND} />
      <circle className="orbit" cx="280" cy="330" r="284" fill="none" stroke={BLUE} strokeOpacity=".35" strokeWidth="2" strokeDasharray="2 12" strokeLinecap="round" />
      <g fill={CORAL} className="twinkle">
        <path d="M70 120l5 13 13 5-13 5-5 13-5-13-13-5 13-5z" />
        <path className="t2" d="M492 96l4 10 10 4-10 4-4 10-4-10-10-4 10-4z" />
        <path className="t3" d="M508 470l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" />
      </g>
      <ellipse className="shadow" cx="280" cy="624" rx="150" ry="11" fill={BLUE} fillOpacity=".16" />

      {/* approved transactions drifting past (behind Finn) */}
      <g className="chip ok a">
        <rect width="124" height="32" rx="16" fill={IVORY} stroke={BLUE} strokeWidth="1.5" />
        <circle cx="16" cy="16" r="8" fill={BLUE} /><path d="M12.5 16l2.6 2.8 5-5.8" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <text x="32" y="21" fontSize="13" fontWeight="700" fill={BLUE} fontFamily="system-ui">₹450 approved</text>
      </g>
      <g className="chip ok b">
        <rect width="104" height="32" rx="16" fill={IVORY} stroke={BLUE} strokeWidth="1.5" />
        <circle cx="16" cy="16" r="8" fill={BLUE} /><path d="M12.5 16l2.6 2.8 5-5.800" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <text x="32" y="21" fontSize="13" fontWeight="700" fill={BLUE} fontFamily="system-ui">₹1,200 ok</text>
      </g>

      {/* Finn */}
      <g className="bob">
        <g className="tail">
          <path d="M356 580C446 584 508 520 474 424C460 388 424 396 428 432C432 474 402 508 352 510Z" fill={CORAL} />
          <path d="M472 428C462 394 430 398 428 432C444 418 458 416 472 428Z" fill={IVORY} />
        </g>
        <path d="M204 404Q280 372 356 404L374 604L186 604Z" fill={CORAL} />
        <path d="M214 410Q176 452 192 514" fill="none" stroke={CORAL} strokeWidth="36" strokeLinecap="round" />
        <path d="M346 410Q384 452 368 514" fill="none" stroke={CORAL} strokeWidth="36" strokeLinecap="round" />
        <path d="M210 384Q280 414 350 384L358 416Q280 448 202 416Z" fill={BLUE} />
        <path d="M216 398Q280 426 344 398" fill="none" stroke={IVORY} strokeWidth="3" strokeDasharray="6 6" strokeLinecap="round" />
        <g className="ear l"><path d="M176 264L188 148L254 220Z" fill={CORAL} /><path d="M192 226L198 178L238 218Z" fill={BLUE} /></g>
        <g className="ear r"><path d="M384 264L372 148L306 220Z" fill={CORAL} /><path d="M368 226L362 178L322 218Z" fill={BLUE} /></g>
        <path d="M168 262Q172 214 206 204Q280 188 354 204Q388 214 392 262Q396 336 280 386Q164 336 168 262Z" fill={CORAL} />
        <path d="M168 272Q190 342 280 386Q370 342 392 272Q346 324 280 318Q214 324 168 272Z" fill={IVORY} />
        <g className="eye"><ellipse cx="238" cy="290" rx="12" ry="15" fill={INK} /><circle className="pupil" cx="241" cy="285" r="4" fill="#fff" /></g>
        <g className="eye"><ellipse cx="322" cy="290" rx="12" ry="15" fill={INK} /><circle className="pupil" cx="325" cy="285" r="4" fill="#fff" /></g>
        <path d="M220 266L252 275M340 266L308 275" stroke={INK} strokeWidth="5" strokeLinecap="round" />
        <ellipse cx="280" cy="340" rx="14" ry="10" fill={INK} />
        <path d="M262 354Q280 369 298 354" fill="none" stroke={INK} strokeWidth="3.5" strokeLinecap="round" />
        <circle cx="206" cy="326" r="11" fill={CORAL} fillOpacity=".35" /><circle cx="354" cy="326" r="11" fill={CORAL} fillOpacity=".35" />

        <circle className="halo" cx="280" cy="520" r="120" fill="url(#glow)" />
        <g className="shield">
          <path d="M280 418L364 446V518C364 566 328 598 280 614C232 598 196 566 196 518V446Z" fill={BLUE} stroke={IVORY} strokeWidth="6" strokeLinejoin="round" />
          <path d="M280 436L350 459V518C350 556 322 584 280 598C238 584 210 556 210 518V459Z" fill="none" stroke={CORAL} strokeWidth="2" strokeDasharray="5 6" />
          <circle cx="280" cy="520" r="36" fill={IVORY} />
          <path d="M262 520l13 14 25-30" fill="none" stroke={BLUE} strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
        </g>
        <ellipse cx="194" cy="522" rx="23" ry="27" fill={CORAL} /><path d="M184 534v-10M194 536v-12M204 534v-10" stroke={CORAL_D} strokeWidth="2.5" strokeLinecap="round" />
        <ellipse cx="366" cy="522" rx="23" ry="27" fill={CORAL} /><path d="M356 534v-10M366 536v-12M376 534v-10" stroke={CORAL_D} strokeWidth="2.5" strokeLinecap="round" />
      </g>

      {/* suspicious transactions bouncing off the shield */}
      <g className="hit r">
        <g className="chip bad">
          <rect width="116" height="34" rx="8" fill={IVORY} stroke={CORAL} strokeWidth="2" />
          <path d="M16 9l9 16H7z" fill={CORAL} /><path d="M16 14v5M16 21.5v.5" stroke="#2a1308" strokeWidth="2" strokeLinecap="round" />
          <text x="32" y="22" fontSize="13" fontWeight="700" fill="#8a3a14" fontFamily="system-ui">₹8,040 · 0.99</text>
        </g>
        <g className="spark"><path d="M0-14l4 10 10 4-10 4-4 10-4-10-10-4 10-4z" fill={CORAL} /><circle r="18" fill="none" stroke={CORAL} strokeWidth="2" /></g>
      </g>
      <g className="hit l">
        <g className="chip bad">
          <rect width="108" height="34" rx="8" fill={IVORY} stroke={CORAL} strokeWidth="2" />
          <path d="M16 9l9 16H7z" fill={CORAL} /><path d="M16 14v5M16 21.5v.5" stroke="#2a1308" strokeWidth="2" strokeLinecap="round" />
          <text x="32" y="22" fontSize="13" fontWeight="700" fill="#8a3a14" fontFamily="system-ui">₹5,000 · new</text>
        </g>
        <g className="spark"><path d="M0-14l4 10 10 4-10 4-4 10-4-10-10-4 10-4z" fill={CORAL} /><circle r="18" fill="none" stroke={CORAL} strokeWidth="2" /></g>
      </g>
    </svg>
  );
}
