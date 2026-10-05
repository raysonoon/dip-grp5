import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Circle,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import { Link } from "react-router-dom";

import { fetchNearbyVendors, fetchVendors } from "../api/vendors";
import {
  formatDistance,
  rankVendors,
  sortByRating,
  vendorRating,
} from "../lib/vendorRanking";

import icon from "leaflet/dist/images/marker-icon.png";
import iconShadow from "leaflet/dist/images/marker-shadow.png";

const NTU_CENTER = [1.3483, 103.6831];
const MIN_DISTANCE_KM = 0.2;
const MAX_DISTANCE_KM = 2;

// Approximate campus spots, from the same estimates as the vendor coordinates.
const CAMPUS_LOCATIONS = [
  { label: "North Spine", lat: 1.3477, lng: 103.68 },
  { label: "South Spine", lat: 1.3466, lng: 103.6822 },
  { label: "The Arc", lat: 1.3454, lng: 103.6785 },
  { label: "NIE", lat: 1.35, lng: 103.679 },
  { label: "Hall 9 (Canteen 9)", lat: 1.3435, lng: 103.6795 },
  { label: "Hall 11 (Canteen 11)", lat: 1.344, lng: 103.679 },
  { label: "Hall 14 (Canteen 14)", lat: 1.3505, lng: 103.687 },
  { label: "North Hill", lat: 1.3502, lng: 103.6875 },
  { label: "Pioneer Hall", lat: 1.347, lng: 103.691 },
];

const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});

const SelectedIcon = L.divIcon({
  className: "",
  html: '<div class="w-8 h-8 rounded-full bg-primary border-4 border-white shadow-lg animate-pulse"></div>',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
  popupAnchor: [0, -16],
});

const UserIcon = L.divIcon({
  className: "",
  html: '<div class="w-4 h-4 rounded-full bg-blue-500 border-2 border-white shadow"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function displayError(error) {
  return error instanceof Error ? error.message : "Something went wrong";
}

function hasCoordinates(vendor) {
  const point = vendor.map_coordinates;
  return point != null && Number.isFinite(point.lat) && Number.isFinite(point.lng);
}

function ratingText(vendor) {
  const rating = vendorRating(vendor);
  return rating == null ? "No rating yet" : `⭐ ${rating.toFixed(1)}`;
}

function describeLocation(location, geoStatus) {
  if (location?.source === "gps") return "Showing vendors near your current location.";
  if (location?.source === "campus") return `Showing vendors near ${location.label}.`;
  if (location?.source === "map") return "Showing vendors near the point you picked on the map.";
  if (geoStatus === "requesting") return "Finding your location…";
  if (geoStatus === "denied") {
    return "Location access was denied. Choose where you are below to get recommendations. Until then, all campus vendors are shown.";
  }
  if (geoStatus === "unavailable") {
    return "We couldn't determine your location. Choose where you are below to get recommendations. Until then, all campus vendors are shown.";
  }
  return "Share your location or choose where you are below to get recommendations. All campus vendors are shown.";
}

// Fits the map to the search radius, and flies to the selected vendor.
function MapViewController({ location, maxDistanceM, selected }) {
  const map = useMap();
  const lat = location?.lat ?? null;
  const lng = location?.lng ?? null;
  const selectedId = selected?.id ?? null;
  const selectedLat = selected?.map_coordinates?.lat ?? null;
  const selectedLng = selected?.map_coordinates?.lng ?? null;

  useEffect(() => {
    if (lat === null || lng === null) {
      map.setView(NTU_CENTER, 15);
      return;
    }
    map.fitBounds(L.latLng(lat, lng).toBounds(maxDistanceM * 2), {
      animate: true,
      padding: [20, 20],
    });
  }, [map, lat, lng, maxDistanceM]);

  useEffect(() => {
    if (selectedId === null || selectedLat === null || selectedLng === null) return;
    map.flyTo([selectedLat, selectedLng], Math.max(map.getZoom(), 16));
  }, [map, selectedId, selectedLat, selectedLng]);

  return null;
}

function MapClickHandler({ enabled, onPick }) {
  useMapEvents({
    click(event) {
      if (enabled) onPick(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

function VendorMarker({ vendor, isSelected, onSelect }) {
  const markerRef = useRef(null);
  const { lat, lng } = vendor.map_coordinates;

  useEffect(() => {
    if (isSelected) markerRef.current?.openPopup();
  }, [isSelected]);

  return (
    <Marker
      ref={markerRef}
      position={[lat, lng]}
      icon={isSelected ? SelectedIcon : DefaultIcon}
      zIndexOffset={isSelected ? 1000 : 0}
      eventHandlers={{ click: () => onSelect(vendor.id) }}
    >
      <Popup>
        <div className="min-w-[190px] font-sans">
          <strong className="text-base font-display">{vendor.name}</strong>
          <p className="text-sm text-muted-foreground mt-1">
            {vendor.category ?? "Food"} · {ratingText(vendor)}
          </p>
          <p className="text-sm text-muted-foreground">{vendor.location ?? "NTU"}</p>
          <p className="text-sm text-muted-foreground">
            {vendor.opening_hours ?? "Opening hours not available"}
          </p>
          {vendor.distance_m != null && (
            <p className="text-sm font-semibold mt-1">{formatDistance(vendor.distance_m)} away</p>
          )}
          <Link
            to={`/vendors/${vendor.id}`}
            className="text-primary text-sm font-semibold hover:underline block mt-2"
          >
            View More →
          </Link>
        </div>
      </Popup>
    </Marker>
  );
}

function RecommendationItem({ vendor, rank, isSelected, onSelect, itemRef }) {
  return (
    <li
      ref={itemRef}
      className={`rounded-xl border bg-card transition-colors ${
        isSelected ? "border-primary ring-2 ring-primary/30" : "border-border"
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect(vendor.id)}
        aria-pressed={isSelected}
        className="w-full text-left p-4 cursor-pointer"
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-semibold text-foreground">
            {rank}. {vendor.name}
          </h3>
          {vendor.distance_m != null && (
            <span className="shrink-0 text-xs font-semibold text-primary bg-primary/10 px-2 py-1 rounded-full">
              {formatDistance(vendor.distance_m)}
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          {vendor.category ?? "Food"} · {ratingText(vendor)}
        </p>
        <p className="text-sm text-muted-foreground mt-1">📍 {vendor.location ?? "NTU"}</p>
        <p className="text-sm text-muted-foreground mt-1">
          🕒 {vendor.opening_hours ?? "Opening hours not available"}
        </p>
      </button>
      <div className="px-4 pb-4">
        <Link
          to={`/vendors/${vendor.id}`}
          className="text-primary text-sm font-semibold hover:underline"
        >
          View More →
        </Link>
      </div>
    </li>
  );
}

export default function MapPage() {
  const [location, setLocation] = useState(null); // { lat, lng, source, label? }
  const [geoStatus, setGeoStatus] = useState("idle");
  const [pickMode, setPickMode] = useState(false);

  const [maxDistanceKm, setMaxDistanceKm] = useState(MAX_DISTANCE_KM);
  const [minRating, setMinRating] = useState(0);
  const [distancePriority, setDistancePriority] = useState(50); // 0 = rating, 100 = distance

  const [vendors, setVendors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedId, setSelectedId] = useState(null);
  const itemRefs = useRef({});

  const hasLocation = location !== null;
  const lat = location?.lat ?? null;
  const lng = location?.lng ?? null;
  const maxDistanceM = Math.round(maxDistanceKm * 1000);
  // Without a location the overview ignores the server-side filters.
  const queryDistanceM = hasLocation ? maxDistanceM : 0;
  const queryMinRating = hasLocation ? minRating : 0;

  const requestLocation = useCallback(({ override = false } = {}) => {
    if (!("geolocation" in navigator)) {
      setGeoStatus("unavailable");
      return;
    }
    setGeoStatus("requesting");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const gps = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          source: "gps",
        };
        setGeoStatus("granted");
        // A location chosen by hand wins over a late GPS fix, unless GPS was asked for.
        setLocation((current) =>
          !override && current && current.source !== "gps" ? current : gps,
        );
      },
      (error) => {
        setGeoStatus(error.code === error.PERMISSION_DENIED ? "denied" : "unavailable");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  }, []);

  useEffect(() => {
    requestLocation();
  }, [requestLocation]);

  // Nearby vendors (distance from PostGIS) when we have a location, otherwise everything.
  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setLoadError("");

    const timer = window.setTimeout(() => {
      const request =
        lat !== null && lng !== null
          ? fetchNearbyVendors({
              lat,
              lng,
              maxDistanceM: queryDistanceM,
              minRating: queryMinRating,
              signal: controller.signal,
            })
          : fetchVendors("", controller.signal);

      request
        .then(setVendors)
        .catch((error) => {
          if (error.name !== "AbortError") setLoadError(displayError(error));
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsLoading(false);
        });
    }, 250);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [lat, lng, queryDistanceM, queryMinRating, reloadKey]);

  const recommendations = useMemo(() => {
    if (hasLocation) {
      return rankVendors(vendors, {
        maxDistanceM,
        distanceWeight: distancePriority / 100,
      });
    }
    return sortByRating(vendors.filter((vendor) => (vendorRating(vendor) ?? 0) >= minRating));
  }, [hasLocation, vendors, maxDistanceM, distancePriority, minRating]);

  const mappedVendors = recommendations.filter(hasCoordinates);
  const selectedVendor = recommendations.find((vendor) => vendor.id === selectedId) ?? null;

  useEffect(() => {
    if (selectedId === null) return;
    itemRefs.current[selectedId]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedId]);

  const handleCampusChange = (event) => {
    const chosen = CAMPUS_LOCATIONS.find((place) => place.label === event.target.value);
    setPickMode(false);
    if (chosen) {
      setLocation({ lat: chosen.lat, lng: chosen.lng, source: "campus", label: chosen.label });
    }
  };

  const handleMapPick = (pickedLat, pickedLng) => {
    setLocation({ lat: pickedLat, lng: pickedLng, source: "map" });
    setPickMode(false);
  };

  const priorityLabel =
    distancePriority > 50 ? "Closest first" : distancePriority < 50 ? "Best rated first" : "Balanced";

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-foreground font-display">Find food near you</h1>
        <p className="text-muted-foreground mt-1">
          Vendors ranked by how close they are and how well they are rated.
        </p>
      </header>

      <section className="mb-4 rounded-xl border border-border bg-card p-4">
        <p role="status" aria-live="polite" className="text-sm text-foreground">
          {describeLocation(location, geoStatus)}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => requestLocation({ override: true })}
            disabled={geoStatus === "requesting"}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold cursor-pointer hover:opacity-90 disabled:opacity-60 disabled:cursor-default"
          >
            Use my location
          </button>

          <label htmlFor="campus-location" className="sr-only">
            Choose a campus location
          </label>
          <select
            id="campus-location"
            value={location?.source === "campus" ? location.label : ""}
            onChange={handleCampusChange}
            className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
          >
            <option value="">Choose where you are…</option>
            {CAMPUS_LOCATIONS.map((place) => (
              <option key={place.label} value={place.label}>
                {place.label}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => setPickMode((on) => !on)}
            aria-pressed={pickMode}
            className={`px-4 py-2 rounded-lg border text-sm font-semibold cursor-pointer ${
              pickMode ? "border-primary text-primary" : "border-border text-foreground"
            }`}
          >
            {pickMode ? "Cancel picking" : "Pick on map"}
          </button>

          {hasLocation && (
            <button
              type="button"
              onClick={() => setLocation(null)}
              className="px-4 py-2 rounded-lg border border-border text-sm font-semibold cursor-pointer"
            >
              Clear location
            </button>
          )}
        </div>
      </section>

      <section
        aria-label="Filters"
        className="mb-6 grid gap-5 rounded-xl border border-border bg-card p-4 md:grid-cols-3"
      >
        <div>
          <label htmlFor="max-distance" className="block text-sm font-semibold text-foreground">
            Max distance: {maxDistanceKm.toFixed(1)} km
          </label>
          <input
            id="max-distance"
            type="range"
            min={MIN_DISTANCE_KM}
            max={MAX_DISTANCE_KM}
            step={0.1}
            value={maxDistanceKm}
            disabled={!hasLocation}
            onChange={(event) => setMaxDistanceKm(Number(event.target.value))}
            className="mt-2 w-full accent-primary disabled:opacity-50"
          />
          {!hasLocation && (
            <p className="text-xs text-muted-foreground">Set a location to filter by distance.</p>
          )}
        </div>

        <div>
          <label htmlFor="min-rating" className="block text-sm font-semibold text-foreground">
            Minimum rating: {minRating.toFixed(1)} ★
          </label>
          <input
            id="min-rating"
            type="range"
            min={0}
            max={5}
            step={0.5}
            value={minRating}
            onChange={(event) => setMinRating(Number(event.target.value))}
            className="mt-2 w-full accent-primary"
          />
        </div>

        <div>
          <label htmlFor="priority" className="block text-sm font-semibold text-foreground">
            Prioritise: {priorityLabel}
          </label>
          <input
            id="priority"
            type="range"
            min={0}
            max={100}
            step={5}
            value={distancePriority}
            disabled={!hasLocation}
            onChange={(event) => setDistancePriority(Number(event.target.value))}
            className="mt-2 w-full accent-primary disabled:opacity-50"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Rating</span>
            <span>Distance</span>
          </div>
        </div>
      </section>

      {pickMode && (
        <p className="mb-2 text-sm font-semibold text-primary">
          Click anywhere on the map to set your location.
        </p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="relative z-0 overflow-hidden rounded-2xl border border-border">
          <MapContainer
            center={NTU_CENTER}
            zoom={15}
            scrollWheelZoom
            className="h-[560px] w-full"
          >
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            />
            <MapViewController
              location={location}
              maxDistanceM={maxDistanceM}
              selected={selectedVendor && hasCoordinates(selectedVendor) ? selectedVendor : null}
            />
            <MapClickHandler enabled={pickMode} onPick={handleMapPick} />

            {hasLocation && (
              <>
                <Circle
                  center={[lat, lng]}
                  radius={maxDistanceM}
                  pathOptions={{ color: "#C41230", weight: 1, fillOpacity: 0.05 }}
                />
                <Marker position={[lat, lng]} icon={UserIcon}>
                  <Popup>You are here</Popup>
                </Marker>
              </>
            )}

            {mappedVendors.map((vendor) => (
              <VendorMarker
                key={vendor.id}
                vendor={vendor}
                isSelected={vendor.id === selectedId}
                onSelect={setSelectedId}
              />
            ))}
          </MapContainer>
        </div>

        <aside>
          <h2 className="mb-3 text-lg font-bold text-foreground">
            {hasLocation ? "Recommended for you" : "All campus vendors"}
            {!isLoading && !loadError && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({recommendations.length})
              </span>
            )}
          </h2>

          {isLoading && <p className="text-muted-foreground">Finding vendors…</p>}

          {!isLoading && loadError && (
            <div role="alert" className="text-destructive">
              <p>Could not load vendors: {loadError}</p>
              <button
                type="button"
                className="mt-1 cursor-pointer text-sm font-semibold underline"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                Try again
              </button>
            </div>
          )}

          {!isLoading && !loadError && recommendations.length === 0 && (
            <p className="text-muted-foreground">
              {hasLocation
                ? `No vendors within ${maxDistanceKm.toFixed(1)} km match your filters. Try a larger distance, a lower minimum rating, or choose a campus location.`
                : "No vendors match your filters."}
            </p>
          )}

          {!isLoading && !loadError && recommendations.length > 0 && (
            <ul className="flex max-h-[560px] flex-col gap-3 overflow-y-auto pr-1">
              {recommendations.map((vendor, index) => (
                <RecommendationItem
                  key={vendor.id}
                  vendor={vendor}
                  rank={index + 1}
                  isSelected={vendor.id === selectedId}
                  onSelect={setSelectedId}
                  itemRef={(element) => {
                    itemRefs.current[vendor.id] = element;
                  }}
                />
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}