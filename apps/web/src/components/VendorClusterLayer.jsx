import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { useNavigate } from "react-router-dom";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import "./vendorMap.css";
import { vendorLatLng } from "../lib/locationBoundaries.js";

export function googleMapsDirectionsUrl(name, lat, lng) {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${name} ${lat},${lng}`)}`;
}

export const pinIcon = L.divIcon({
  className: "vendor-pin-wrapper",
  html: '<span class="vendor-pin"></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
  popupAnchor: [0, -10],
});
const selectedPinIcon = L.divIcon({
  className: "vendor-pin-wrapper",
  html: '<span class="vendor-pin vendor-pin--selected"></span>',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
  popupAnchor: [0, -12],
});

function line(parent, text, className) {
  const el = L.DomUtil.create("div", className, parent);
  el.textContent = text; // textContent: vendor data is never parsed as HTML
  return el;
}

function buildPopup(vendor, point, navigate, extraLines) {
  const root = L.DomUtil.create("div", "vendor-popup");

  const nameRow = L.DomUtil.create("div", "", root);
  nameRow.style.display = "flex";
  nameRow.style.alignItems = "baseline";
  nameRow.style.justifyContent = "flex-start";
  nameRow.style.gap = "0.35rem";

  const name = L.DomUtil.create("span", "", nameRow);
  name.textContent = vendor.name;
  name.style.fontWeight = "600";

  const rating = vendor.average_rating ?? vendor.average_google_rating;
  const ratingEl = L.DomUtil.create("span", "", nameRow);
  ratingEl.textContent = rating != null ? `⭐ ${rating.toFixed(1)}` : "No rating yet";

  const meta = [vendor.category, vendor.cuisine].filter(Boolean).join(" · ");
  if (meta) line(root, meta);
  if (vendor.location) line(root, vendor.location);

  extraLines.forEach((t) => line(root, t));

  const row = L.DomUtil.create("div", "", root);
  const more = L.DomUtil.create("a", "", row);
  more.href = `/vendors/${vendor.id}`;
  more.textContent = "View More →";
  more.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    navigate(`/vendors/${vendor.id}`);
  });

  const dir = L.DomUtil.create("a", "", row);
  dir.href = googleMapsDirectionsUrl(vendor.name, point.lat, point.lng);
  dir.target = "_blank";
  dir.rel = "noopener noreferrer";
  dir.textContent = "Directions →";
  dir.style.marginLeft = "12px";
  return root;
}

/**
 * Renders vendors as a Leaflet.markercluster group inside a react-leaflet <MapContainer>.
 * Props: vendors, selectedId (optional highlight, opens popup), onSelect(id),
 * getExtraLines(vendor) -> string[] (optional extra popup lines, e.g. distance).
 */
export default function VendorClusterLayer({ vendors, selectedId = null, onSelect, getExtraLines }) {
  const map = useMap();
  const navigate = useNavigate();
  const clusterRef = useRef(null);
  const markersRef = useRef(new Map());
  const lastOpenedRef = useRef(null);
  const cbRef = useRef({});
  cbRef.current = { navigate, onSelect, getExtraLines };

  useEffect(() => {
    const cluster = L.markerClusterGroup({
      maxClusterRadius: 50,
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      zoomToBoundsOnClick: true,
    });
    const markers = new Map();
    (vendors ?? []).forEach((vendor) => {
      const point = vendorLatLng(vendor);
      if (!point) return;
      const marker = L.marker([point.lat, point.lng], { icon: pinIcon, title: vendor.name });
      marker.bindPopup(() =>
        buildPopup(vendor, point, cbRef.current.navigate, cbRef.current.getExtraLines?.(vendor) ?? []),
      );
      marker.on("click", () => cbRef.current.onSelect?.(vendor.id));
      markers.set(String(vendor.id), marker);
      cluster.addLayer(marker);
    });
    map.addLayer(cluster);
    clusterRef.current = cluster;
    markersRef.current = markers;
    return () => {
      map.removeLayer(cluster);
      clusterRef.current = null;
      markersRef.current = new Map();
    };
  }, [map, vendors]);

  useEffect(() => {
    markersRef.current.forEach((marker, id) => {
      marker.setIcon(id === String(selectedId) ? selectedPinIcon : pinIcon);
    });
    const marker = selectedId == null ? null : markersRef.current.get(String(selectedId));
    if (!marker || lastOpenedRef.current === String(selectedId)) return;
    lastOpenedRef.current = String(selectedId);
    // zoom/uncluster until the marker is visible, then open its popup
    clusterRef.current?.zoomToShowLayer(marker, () => marker.openPopup());
  }, [selectedId, vendors]);

  useEffect(() => {
    if (selectedId == null) lastOpenedRef.current = null;
  }, [selectedId]);

  return null;
}