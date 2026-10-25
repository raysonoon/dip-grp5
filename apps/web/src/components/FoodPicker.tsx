import { useEffect, useRef, useState } from "react";
import { ChevronsUpDown, Sparkles } from "lucide-react";
import { FOOD_OPTIONS, foodRollTarget } from "../lib/foodPicker.js";

export type FoodType = typeof FOOD_OPTIONS[number];
const ROW_HEIGHT = 52;
const WINDOW_HEIGHT = ROW_HEIGHT * 4;
const CENTRE_OFFSET = (WINDOW_HEIGHT - ROW_HEIGHT) / 2;
const ROLL_DURATION = 3200;
const ROLL_ROWS = Array.from({ length: 6 }, () => FOOD_OPTIONS).flat();

export default function FoodPicker({ latestPick, onPick, onRecommend }: {
  latestPick: FoodType | null;
  onPick: (food: FoodType) => void;
  onRecommend: () => void;
}) {
  const initialChoice = Math.max(0, FOOD_OPTIONS.findIndex((food) => food.id === latestPick?.id));
  const [trackIndex, setTrackIndex] = useState(FOOD_OPTIONS.length + initialChoice);
  const [rolling, setRolling] = useState(false);
  const [animate, setAnimate] = useState(false);
  const [winner, setWinner] = useState<FoodType | null>(latestPick);
  const rollingRef = useRef(false);
  const currentChoice = useRef(initialChoice);
  const pendingChoice = useRef(0);
  const revealTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const animationFrames = useRef<number[]>([]);

  useEffect(() => () => {
    if (revealTimer.current) clearTimeout(revealTimer.current);
    animationFrames.current.forEach(cancelAnimationFrame);
  }, []);

  function completeRoll() {
    if (!rollingRef.current) return;
    if (revealTimer.current) clearTimeout(revealTimer.current);
    currentChoice.current = pendingChoice.current;
    setWinner(FOOD_OPTIONS[pendingChoice.current]);
    onPick(FOOD_OPTIONS[pendingChoice.current]);
    setRolling(false);
    rollingRef.current = false;
  }

  function roll() {
    if (rollingRef.current) return;
    const next = foodRollTarget(currentChoice.current, FOOD_OPTIONS.length);
    pendingChoice.current = next.selectedIndex;
    setWinner(null);
    setAnimate(false);
    rollingRef.current = true;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setTrackIndex(FOOD_OPTIONS.length + next.selectedIndex);
      completeRoll();
      return;
    }
    setRolling(true);
    setTrackIndex(next.resetIndex);
    animationFrames.current = [requestAnimationFrame(() => {
      animationFrames.current = [requestAnimationFrame(() => {
        setAnimate(true);
        setTrackIndex(next.targetIndex);
        revealTimer.current = setTimeout(completeRoll, ROLL_DURATION + 100);
        animationFrames.current = [];
      })];
    })];
  }

  return (
    <div className="food-picker-panel" role="tabpanel" id="foodie-picker-panel" aria-labelledby="foodie-picker-tab" aria-busy={rolling}>
      <div className="food-picker-kicker"><Sparkles size={12} /> WHAT SHALL WE EAT?</div>
      <h3>Let's roll for food.</h3>
      <p className="food-picker-intro">All {FOOD_OPTIONS.length} food types. One happy decision.</p>

      <div className={`food-picker-frame ${rolling ? "is-rolling" : ""}`} aria-hidden="true">
        <div className="food-picker-viewport" style={{ height: WINDOW_HEIGHT }}>
          <div className="food-picker-focus" style={{ top: CENTRE_OFFSET, height: ROW_HEIGHT }} />
          <div className="food-picker-track" style={{ transform: `translateY(${CENTRE_OFFSET - trackIndex * ROW_HEIGHT}px)`, transition: animate ? `transform ${ROLL_DURATION}ms cubic-bezier(.12,.72,.12,1)` : "none" }} onTransitionEnd={(event) => {
            if (event.target === event.currentTarget && event.propertyName === "transform") completeRoll();
          }}>
            {ROLL_ROWS.map((food, index) => (
              <div className={`food-picker-row ${!rolling && index === trackIndex ? "is-selected" : ""}`} style={{ height: ROW_HEIGHT }} key={`${index}-${food.id}`}>
                <span className="food-picker-emoji">{food.emoji}</span><span className="food-picker-name">{food.label}</span>
              </div>
            ))}
          </div>
          <span className="food-picker-marker">›</span>
        </div>
      </div>

      <button className="food-picker-roll" type="button" onClick={roll} disabled={rolling}>
        <ChevronsUpDown size={18} /> {rolling ? "Picking your next meal…" : winner ? "PICK AGAIN" : "PICK MY NEXT MEAL"}
      </button>
      <div className="food-picker-result" role="status" aria-live="polite" aria-atomic="true">
        {winner ? <strong>{winner.emoji} {winner.label} it is! Let's makan.</strong> : <span>{rolling ? "Round and round we go…" : "Tap to roll. See what you're having!"}</span>}
      </div>
      {winner && !rolling && <button type="button" className="food-picker-recommend" onClick={onRecommend}>Find places for {winner.label} <span aria-hidden="true">↗</span></button>}
      <details className="food-picker-options"><summary>See all {FOOD_OPTIONS.length} food types</summary><ul>{FOOD_OPTIONS.map((food) => <li key={food.id}>{food.emoji} {food.label}</li>)}</ul></details>
    </div>
  );
}
