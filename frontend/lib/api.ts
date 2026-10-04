/**
 * Typed API Client generated from FastAPI OpenAPI Schema (/backend/openapi.json).
 * Generated via openapi-typescript and typed request wrappers.
 */
import type { paths, components } from "./schema";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type SchemaPanchayatForecast = components["schemas"];

export async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const token = typeof window !== "undefined" ? localStorage.getItem("pannaga_access_token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      errorDetail = errJson.detail || JSON.stringify(errJson);
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

// ─── Typed API Endpoints ──────────────────────────────────────────────────────

export const api = {
  // Geo & Map data
  geo: {
    getPanchayatsGeoJson: (leadWeek: number = 1, blockId?: number) => {
      const q = new URLSearchParams({ lead_week: String(leadWeek) });
      if (blockId) q.append("block_id", String(blockId));
      return fetchApi<any>(`/api/v1/geo/geojson/panchayats?${q.toString()}`);
    },
    search: (query: string) => {
      return fetchApi<{ query: string; results: any[] }>(`/api/v1/geo/search?q=${encodeURIComponent(query)}`);
    },
    lookup: (lat: number, lon: number) => {
      return fetchApi<any>(`/api/v1/geo/lookup?lat=${lat}&lon=${lon}`);
    },
    getBlockTileUrl: (leadWeek: number = 1) => {
      return `${API_BASE}/api/v1/geo/tiles/blocks/{z}/{x}/{y}.pbf?lead_week=${leadWeek}`;
    },
    getPanchayatTileUrl: (leadWeek: number = 1) => {
      return `${API_BASE}/api/v1/geo/tiles/panchayats/{z}/{x}/{y}.pbf?lead_week=${leadWeek}`;
    },
  },

  // Forecasts
  forecasts: {
    getPanchayat: (panchayatId: number) => {
      return fetchApi<any>(`/api/v1/forecasts/panchayat/${panchayatId}`);
    },
  },

  // Advisories
  advisories: {
    list: (leadWeek?: number) => {
      const q = leadWeek ? `?lead_week=${leadWeek}` : "";
      return fetchApi<{ advisories: any[]; simulated_banner: boolean }>(`/api/v1/advisories${q}`);
    },
    get: (id: number, lang: string = "en") => {
      return fetchApi<any>(`/api/v1/advisories/${id}?lang=${lang}`);
    },
    translate: (id: number, lang: string) => {
      return fetchApi<any>(`/api/v1/advisories/${id}/translate/${lang}`);
    },
  },

  // Auth & Profile
  auth: {
    requestOtp: (phone: string) => {
      return fetchApi<{ message: string; dev_otp?: string }>(`/api/v1/auth/request-otp`, {
        method: "POST",
        body: JSON.stringify({ phone_number: phone }),
      });
    },
    verifyOtp: (phone: string, otp: string) => {
      return fetchApi<{ message: string; access_token: string; user: any }>(`/api/v1/auth/verify-otp`, {
        method: "POST",
        body: JSON.stringify({ phone_number: phone, otp }),
      });
    },
  },
  me: {
    get: () => fetchApi<any>(`/api/v1/me`),
    updateProfile: (data: {
      preferred_language?: string;
      panchayat_id?: number;
      crop_type?: string;
      irrigation_source?: string;
      farm_size_acres?: number;
      soil_type?: string;
      whatsapp_consent?: boolean;
      sms_consent?: boolean;
      opt_out?: boolean;
    }) => {
      return fetchApi<any>(`/api/v1/me`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    updateCropStatus: (status: string) => {
      return fetchApi<any>(`/api/v1/me/crop-status`, {
        method: "PATCH",
        body: JSON.stringify({ crop_status: status }),
      });
    },
  },
  officer: {
    getQueue: (blockId?: number) => {
      const q = blockId ? `?block_id=${blockId}` : "";
      return fetchApi<{ count: number; queue: any[] }>(`/api/v1/officer/queue${q}`);
    },
    approve: (advisoryId: number, notes?: string) => {
      return fetchApi<{ message: string; advisory_id: number; audio_url?: string }>(
        `/api/v1/officer/advisories/${advisoryId}/approve`,
        {
          method: "POST",
          body: JSON.stringify({ notes }),
        }
      );
    },
    reject: (advisoryId: number, notes?: string) => {
      return fetchApi<{ message: string; advisory_id: number }>(
        `/api/v1/officer/advisories/${advisoryId}/reject`,
        {
          method: "POST",
          body: JSON.stringify({ notes }),
        }
      );
    },
    previewTranslation: (advisoryId: number, lang: string) => {
      return fetchApi<any>(`/api/v1/officer/advisories/${advisoryId}/translate/${lang}`);
    },
    broadcast: (advisoryIds: number[], channel: "SMS" | "WHATSAPP" = "SMS", confirm: boolean = false) => {
      return fetchApi<{ results: any[] }>(`/api/v1/officer/broadcast`, {
        method: "POST",
        body: JSON.stringify({
          advisory_ids: advisoryIds,
          channel,
          confirm,
        }),
      });
    },
    getDelivery: (advisoryId?: number) => {
      const q = advisoryId ? `?advisory_id=${advisoryId}` : "";
      return fetchApi<{ count: number; logs: any[] }>(`/api/v1/officer/delivery${q}`);
    },
  },
};

