/**
 * WeatherGPT — TypeScript Interface Definitions
 *
 * Generated for frontend integration (React, Next.js, Vue, Svelte, Angular).
 * Matches FastAPI Pydantic models in app/models/schemas.py.
 */

// ---------------------------------------------------------------------------
// Chat & Conversation Models
// ---------------------------------------------------------------------------

export interface ChatRequest {
  /** User's natural language weather or alert query */
  message: string;
  /** ISO 639-1 language code (e.g. 'en', 'hi', 'ta', 'te', 'bn', 'mr') */
  language?: string;
  /** Conversation session ID to preserve multi-turn memory */
  session_id?: string | null;
}

export interface ChatResponse {
  /** Natural language response phrased by the assistant */
  reply: string;
  /** Response language code */
  language: string;
  /**
   * Structured weather or alert data payload executed by the deterministic tool.
   * Useful for rendering widgets, temperature cards, and forecast timelines alongside the message.
   */
  data?: ForecastPoint | ForecastTimeline | AlertListResponse | Record<string, any> | null;
  /** Session ID preserved for subsequent turns */
  session_id?: string | null;
  /** Data sources cited (e.g. ['open-meteo', 'gfs', 'sachet-ndma', 'imd']) */
  sources: string[];
}

export interface VoiceChatResponse {
  /** Speech-to-Text transcript of the user's input audio */
  transcript_in: string;
  /** Natural language reply in user's selected language */
  reply_text: string;
  /** Base64-encoded audio (WAV/MP3) for auto-playing voice response */
  reply_audio_base64?: string | null;
  /** Response language code */
  language: string;
  /** Session ID */
  session_id?: string | null;
  /** Data sources cited */
  sources: string[];
}

// ---------------------------------------------------------------------------
// Language & Voice Models
// ---------------------------------------------------------------------------

export interface LanguageItem {
  code: string;
  name: string;
}

export interface LanguagesResponse {
  languages: LanguageItem[];
  count: number;
}

// ---------------------------------------------------------------------------
// Numerical Weather & Forecast Models
// ---------------------------------------------------------------------------

export interface ForecastPoint {
  source: string;
  issued_at: string;
  valid_at: string;
  lat: number;
  lon: number;
  location_name?: string | null;

  temperature_c?: number | null;
  feels_like_c?: number | null;
  humidity_pct?: number | null;
  wind_speed_kmh?: number | null;
  wind_direction_deg?: number | null;
  wind_gusts_kmh?: number | null;
  pressure_hpa?: number | null;
  surface_pressure_hpa?: number | null;
  cloud_cover_pct?: number | null;
  precipitation_mm?: number | null;
  rain_mm?: number | null;
  snowfall_cm?: number | null;
  visibility_m?: number | null;
  uv_index?: number | null;
  weather_code?: number | null;
  weather_description?: string | null;
  is_day?: boolean | null;
}

export interface DailyForecast {
  date: string; // YYYY-MM-DD
  temp_max_c?: number | null;
  temp_min_c?: number | null;
  feels_like_max_c?: number | null;
  feels_like_min_c?: number | null;
  precipitation_sum_mm?: number | null;
  rain_sum_mm?: number | null;
  precipitation_hours?: number | null;
  precipitation_probability_max_pct?: number | null;
  wind_speed_max_kmh?: number | null;
  wind_gusts_max_kmh?: number | null;
  wind_direction_dominant_deg?: number | null;
  uv_index_max?: number | null;
  weather_code?: number | null;
  weather_description?: string | null;
  sunrise?: string | null;
  sunset?: string | null;
}

export interface HourlyForecast {
  time: string; // ISO 8601
  temperature_c?: number | null;
  feels_like_c?: number | null;
  humidity_pct?: number | null;
  precipitation_mm?: number | null;
  precipitation_probability_pct?: number | null;
  weather_code?: number | null;
  pressure_hpa?: number | null;
  wind_speed_kmh?: number | null;
  wind_direction_deg?: number | null;
  cloud_cover_pct?: number | null;
  is_day?: boolean | null;
}

export interface ForecastTimeline {
  source: string;
  issued_at: string;
  lat: number;
  lon: number;
  location_name?: string | null;
  timezone?: string | null;
  daily: DailyForecast[];
  hourly?: HourlyForecast[] | null;
}

// ---------------------------------------------------------------------------
// Disaster Alert & WebSocket Models
// ---------------------------------------------------------------------------

export type AlertSeverity = "Extreme" | "Severe" | "Moderate" | "Minor" | "Unknown";

export interface AlertRecord {
  alert_id: string;
  source: string;
  sender: string;
  sent_at: string;
  status: string;
  msg_type: string;
  event: string;
  urgency: string;
  severity: AlertSeverity;
  certainty: string;
  headline?: string | null;
  description?: string | null;
  instruction?: string | null;
  effective_at?: string | null;
  expires_at?: string | null;
  area_desc?: string | null;
  polygon?: [number, number][] | null;
  circle?: string | null;
  language: string;
}

export interface AlertListResponse {
  location_name: string;
  lat?: number | null;
  lon?: number | null;
  count: number;
  alerts: AlertRecord[];
}

export interface WebSocketAlertMessage {
  type: "weather_alert";
  timestamp: string;
  alert: AlertRecord;
}

// ---------------------------------------------------------------------------
// Geocoding & Location Models
// ---------------------------------------------------------------------------

export interface LocationMatch {
  name: string;
  lat: number;
  lon: number;
  country?: string | null;
  country_code?: string | null;
  admin1?: string | null; // State / Province
  admin2?: string | null; // District
  elevation?: number | null;
  timezone?: string | null;
  population?: number | null;
  confidence: number;
}

// ---------------------------------------------------------------------------
// Health & Diagnostics
// ---------------------------------------------------------------------------

export interface HealthCheckResponse {
  status: "ok" | "error";
  database: "connected" | "disconnected";
  redis: "connected" | "disconnected";
  scheduler_running: boolean;
}
