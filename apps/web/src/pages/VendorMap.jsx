import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { Link } from 'react-router-dom';
import { fetchVendors } from '../api/vendors';
import { vendorsData } from '../data/vendorsData';

import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

const NTU_CENTER = [1.3483, 103.6831];
const DISPLAY_FONT = "'Fraunces', serif";

export default function VendorMap() {
  const [vendors, setVendors] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    fetchVendors("", controller.signal)
      .then(setVendors)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const mappedVendors = vendors.filter((vendor) => vendorsData[vendor.id]);

  return (
    <div className="relative z-0 rounded-2xl border border-border overflow-hidden">
      <MapContainer
        center={NTU_CENTER}
        zoom={15}
        scrollWheelZoom={false}
        style={{ height: '400px', width: '100%' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {mappedVendors.map((vendor) => {
          const { lat, lng } = vendorsData[vendor.id];
          return (
            <Marker key={vendor.id} position={[lat, lng]}>
              <Popup>
                <div className="min-w-[160px] font-sans">
                  <strong className="text-base" style={{ fontFamily: DISPLAY_FONT }}>
                    {vendor.name}
                  </strong>
                  <br />
                  <span className="text-sm text-muted-foreground">
                    {vendor.location} · ⭐ {vendor.average_rating ?? vendor.average_google_rating ?? '—'}
                  </span>
                  <br />
                  <Link to={`/food/vendors/${vendor.id}`} className="text-primary text-sm font-semibold hover:underline">
                    View Menu &amp; Reviews →
                  </Link>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}