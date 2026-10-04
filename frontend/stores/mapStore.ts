import { create } from "zustand";

export type WeatherLayer = "onset" | "break" | "excess";
export type LeadWeek = 1 | 2 | 3 | 4;

export interface PanchayatFeature {
  id: number;
  name: string;
  block_name: string;
  district_name: string;
  state_name: string;
  onset_prob: number;
  break_prob: number;
  excess_rain_prob: number;
  p10_rainfall_mm: number;
  p50_rainfall_mm: number;
  p90_rainfall_mm: number;
  confidence: number;
  data_source: string;
  centroid_lon?: number;
  centroid_lat?: number;
}

interface MapState {
  selectedLayer: WeatherLayer;
  selectedWeek: LeadWeek;
  selectedPanchayat: PanchayatFeature | null;
  isDrawerOpen: boolean;
  webglSupported: boolean;
  isSimulatedBannerVisible: boolean;
  searchQuery: string;

  setSelectedLayer: (layer: WeatherLayer) => void;
  setSelectedWeek: (week: LeadWeek) => void;
  setSelectedPanchayat: (p: PanchayatFeature | null) => void;
  setDrawerOpen: (open: boolean) => void;
  setWebglSupported: (supported: boolean) => void;
  setSearchQuery: (q: string) => void;
  closeDrawer: () => void;
}

export const useMapStore = create<MapState>((set) => ({
  selectedLayer: "onset",
  selectedWeek: 1,
  selectedPanchayat: null,
  isDrawerOpen: false,
  webglSupported: true,
  isSimulatedBannerVisible: true,
  searchQuery: "",

  setSelectedLayer: (selectedLayer) => set({ selectedLayer }),
  setSelectedWeek: (selectedWeek) => set({ selectedWeek }),
  setSelectedPanchayat: (selectedPanchayat) =>
    set({ selectedPanchayat, isDrawerOpen: !!selectedPanchayat }),
  setDrawerOpen: (isDrawerOpen) => set({ isDrawerOpen }),
  setWebglSupported: (webglSupported) => set({ webglSupported }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  closeDrawer: () => set({ isDrawerOpen: false, selectedPanchayat: null }),
}));
