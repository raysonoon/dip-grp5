import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { Link } from 'react-router-dom';
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
const BODY_FONT = "'Plus Jakarta Sans', sans-serif";

export default function VendorMap({ compact = false }) {
  const mapHeight = compact ? '400px' : '550px';

  const mapContent = (
    <div className="rounded-2xl border border-border overflow-hidden">
      <MapContainer
        center={NTU_CENTER}
        zoom={compact ? 15 : 16}
        scrollWheelZoom={!compact}
        style={{ height: mapHeight, width: '100%' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {vendorsData.map((vendor) => (
          <Marker key={vendor.id} position={[vendor.lat, vendor.lng]}>
            <Popup>
              <div style={{ fontFamily: BODY_FONT, minWidth: '160px' }}>
                <strong style={{ fontFamily: DISPLAY_FONT, fontSize: '1rem' }}>
                  {vendor.name}
                </strong>
                <br />
                <span style={{ fontSize: '0.85rem', color: '#6B6560' }}>
                  {vendor.canteen} · ⭐ {vendor.rating}
                </span>
                <br />
                <Link
                  to={`/food/vendors/${vendor.id}`}
                  style={{ color: '#C41230', fontSize: '0.85rem', fontWeight: 600 }}
                >
                  View Menu & Reviews →
                </Link>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );

  if (compact) {
    return mapContent;
  }

  return (
    <div className="min-h-screen bg-background pt-24 pb-16" style={{ fontFamily: BODY_FONT }}>
      <div className="max-w-7xl mx-auto px-6">
        <h1
          className="text-3xl md:text-4xl font-bold mb-2 text-foreground"
          style={{ fontFamily: DISPLAY_FONT }}
        >
          Vendor Map
        </h1>
        <p className="text-muted-foreground mb-8">
          Find food stalls across NTU canteens on the map below
        </p>
        {mapContent}
      </div>
    </div>
  );
}