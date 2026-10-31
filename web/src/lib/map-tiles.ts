/** Base maps for the project map. Each needs its attribution shown; swap or add one here (no other code changes).
 * Street: OpenStreetMap's standard tiles (light, interactive use with attribution, per its tile usage policy).
 * Satellite: Esri World Imagery (attribution required; check Esri's terms before heavier or commercial use). */
export interface TileLayerConfig {
  name: string;
  url: string;
  attribution: string;
  maxZoom: number;
}

export const BASE_MAPS: TileLayerConfig[] = [
  {
    name: "Street",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  {
    name: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    maxZoom: 18,
  },
];
