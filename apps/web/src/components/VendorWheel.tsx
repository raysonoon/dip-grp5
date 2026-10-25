import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { ArrowRight, MapPin, RotateCw, Sparkles, Star, Utensils, X } from "lucide-react";
import { fetchVendors, type parseVendor } from "../api/vendors";
import { chooseWheelSpin, completeWheelVendor, type WheelVendor } from "../lib/vendorWheel.js";
import "./vendorWheel.css";

const COLORS = ["#f9d9a7", "#edb5af", "#abd2c7", "#b8cce6", "#e1c7e6", "#e8dca0"];
const point = (angle: number, radius: number) => ({ x: 180 + radius * Math.sin(angle * Math.PI / 180), y: 180 - radius * Math.cos(angle * Math.PI / 180) });

function WheelFace({ vendors, rotation, duration }: { vendors: WheelVendor[]; rotation: number; duration: number }) {
  const size = 360 / vendors.length;
  return <div className="vendor-wheel-disc" aria-hidden="true">
    <div className="vendor-wheel-pointer" />
    <svg viewBox="0 0 360 360" style={{ transform: `rotate(${rotation}deg)`, transitionDuration: `${duration}ms` }}>
      {vendors.map((vendor, index) => {
        const start = point(index * size, 169);
        const end = point((index + 1) * size, 169);
        const label = point((index + 0.5) * size, vendors.length <= 8 ? 112 : 139);
        const shortName = vendor.name.length > 17 ? `${vendor.name.slice(0, 16)}…` : vendor.name;
        return <g key={vendor.id}>
          {vendors.length === 1 ? <circle cx="180" cy="180" r="169" fill={COLORS[0]} stroke="white" strokeWidth="2" /> : <path d={`M180 180 L${start.x} ${start.y} A169 169 0 ${size > 180 ? 1 : 0} 1 ${end.x} ${end.y} Z`} fill={COLORS[index % COLORS.length]} stroke="white" strokeWidth="2" />}
          <text x={label.x} y={label.y} textAnchor="middle" dominantBaseline="middle" transform={vendors.length <= 8 ? `rotate(${(index + 0.5) * size - 90} ${label.x} ${label.y})` : undefined} fontSize={vendors.length > 30 ? 9 : 12} fontWeight="700" fill="#283438">{vendors.length <= 8 ? shortName : index + 1}</text>
        </g>;
      })}
    </svg>
    <div className="vendor-wheel-hub"><Utensils size={23} /><span>FOODIE</span></div>
  </div>;
}

type Props = {
  vendors: WheelVendor[];
  onRemove: (vendorId: number) => void;
  onClose: () => void;
};

export default function VendorWheel({ vendors, onRemove, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const spinningRef = useRef(false);
  const rotationRef = useRef(0);
  const [rotation, setRotation] = useState(0);
  const [duration, setDuration] = useState(3600);
  const [stage, setStage] = useState<"ready" | "spinning" | "result">("ready");
  const [winner, setWinner] = useState<WheelVendor | null>(null);
  const [spinVendors, setSpinVendors] = useState(vendors);
  const [catalog, setCatalog] = useState<ReturnType<typeof parseVendor>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const resultRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      dialog?.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetchVendors("", controller.signal)
      .then((items) => { if (!controller.signal.aborted) setCatalog(items); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    if (stage === "result") resultRef.current?.focus({ preventScroll: true });
  }, [stage]);

  function spin(candidates = vendors) {
    if (spinningRef.current || candidates.length === 0 || loading) return;
    spinningRef.current = true;
    const next = chooseWheelSpin(candidates, rotationRef.current);
    const spinDuration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 3600;
    setSpinVendors(candidates);
    setWinner(null);
    setStage("spinning");
    setDuration(spinDuration);
    rotationRef.current = next.rotation;
    setRotation(next.rotation);
    timerRef.current = setTimeout(() => {
      spinningRef.current = false;
      setWinner(next.vendor);
      setStage("result");
    }, spinDuration);
  }

  function removeAndSpin() {
    if (!winner || vendors.length < 2 || spinningRef.current || loading) return;
    const remaining = vendors.filter((vendor) => vendor.id !== winner.id);
    onRemove(winner.id);
    spin(remaining);
  }

  const selected = winner ? completeWheelVendor(winner, catalog) : null;
  const displayVendors = (stage === "ready" ? vendors : spinVendors).map((vendor) => completeWheelVendor(vendor, catalog));

  return createPortal(<dialog ref={dialogRef} className="vendor-wheel-dialog" aria-labelledby="vendor-wheel-title" onCancel={onClose}>
    <div className="vendor-wheel-content">
      <header className="vendor-wheel-header">
        <div><p><Sparkles size={14} aria-hidden="true" /> A LITTLE HELP DECIDING</p><h2 id="vendor-wheel-title">Spin the wheel</h2></div>
        <button type="button" className="vendor-wheel-close" onClick={onClose} aria-label="Close spin the wheel" autoFocus><X size={20} /></button>
      </header>
      <div className="vendor-wheel-body">
        <div className="vendor-wheel-visual">
          <WheelFace vendors={displayVendors} rotation={rotation} duration={duration} />
          <p className="vendor-wheel-count">{vendors.length} {vendors.length === 1 ? "place" : "places"} from this chat · Equal chance for every place</p>
          <details className="vendor-wheel-places"><summary>Places on this wheel</summary><ol>{displayVendors.map((vendor, index) => <li key={vendor.id}><span>{index + 1}.</span> {vendor.name}</li>)}</ol></details>
        </div>
        <div className="vendor-wheel-side">
          {selected ? <section aria-label="Selected vendor" className="vendor-wheel-result">
            <p className="vendor-wheel-eyebrow">YOUR NEXT MAKAN STOP</p>
            <h3 ref={resultRef} tabIndex={-1}>{selected.name}</h3>
            <p><MapPin size={16} aria-hidden="true" />{selected.location ?? "Location unavailable"}</p>
            <p><Utensils size={16} aria-hidden="true" />{selected.category ?? "Category unavailable"}</p>
            <p><Star size={16} aria-hidden="true" />{selected.rating != null ? `${selected.rating.toFixed(1)} / 5` : "Rating unavailable"}</p>
            <div className="vendor-wheel-actions">
              <Link to={`/vendors/${selected.id}`} className="vendor-wheel-primary" onClick={onClose}>View More <ArrowRight size={16} aria-hidden="true" /></Link>
              <button type="button" className="vendor-wheel-secondary" onClick={() => spin()} disabled={loading}><RotateCw size={16} aria-hidden="true" /> Spin again</button>
              <button type="button" className="vendor-wheel-remove" onClick={removeAndSpin} disabled={vendors.length < 2 || loading}>Remove and spin again</button>
              {vendors.length < 2 && <small>One place left. Get more recommendations before removing it.</small>}
            </div>
          </section> : <div className="vendor-wheel-ready">
            <div className="vendor-wheel-ready-icon"><Utensils size={27} aria-hidden="true" /></div>
            <h3>{stage === "spinning" ? "Finding your next bite…" : "Too many good choices?"}</h3>
            <p>Let the wheel choose from the places Foodie has shared in this chat.</p>
            <button type="button" className="vendor-wheel-primary" disabled={stage === "spinning" || loading || vendors.length === 0} onClick={() => spin()}><RotateCw size={17} aria-hidden="true" />{loading ? "Loading places…" : stage === "spinning" ? "Spinning…" : "Spin the wheel"}</button>
          </div>}
          {error && <div role="status" className="vendor-wheel-load-error">Some details couldn't be loaded. Your chat's places are still on the wheel. <button type="button" disabled={stage === "spinning" || loading} onClick={() => setAttempt((value) => value + 1)}>Try again</button></div>}
          <p className="vendor-wheel-status" role="status">{stage === "spinning" ? "Spinning the wheel…" : selected ? `Selected ${selected.name}.` : loading ? "Loading vendor details…" : "Ready when you are."}</p>
        </div>
      </div>
    </div>
  </dialog>, document.body);
}
