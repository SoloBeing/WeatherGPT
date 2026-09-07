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
  data?:
    | ForecastPoint
    | ForecastTimeline
    | AlertListResponse
    | MarinePoint
    | AviationWeather
    | CropAdvisoryReport
    | ClimatologyReport
    | Record<string, any>
    | null;
  /** Session ID preserved for subsequent turns */
  session_id?: string | null;
  /** Data sources cited (e.g. ['open-meteo', 'gfs', 'sachet-ndma', 'imd', 'INCOIS', 'NOAA Aviation Weather Center']) */
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
  data_quality?: "verified" | "synthetic";
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
  time: string; // ISO timestamp
  temp_c?: number | null;
  humidity_pct?: number | null;
  precipitation_mm?: number | null;
  precipitation_probability_pct?: number | null;
  weather_code?: number | null;
  weather_description?: string | null;
  wind_speed_kmh?: number | null;
  wind_direction_deg?: number | null;
}

export interface ForecastTimeline {
  source: string;
  data_quality?: "verified" | "synthetic";
  issued_at: string;
  lat: number;
  lon: number;
  location_name?: string | null;
  timezone?: string | null;
  elevation_m?: number | null;
  daily: DailyForecast[];
  hourly?: HourlyForecast[] | null;
}

// ---------------------------------------------------------------------------
// SIH Domain-Specific Models
// ---------------------------------------------------------------------------

/** Ocean state and Potential Fishing Zone (PFZ) advisory */
export interface MarinePoint {
  source: string;
  data_quality?: "verified" | "synthetic";
  location_name: string;
  lat: number;
  lon: number;
  issued_at: string;
  wave_height_m: number;
  wave_direction_deg: number;
  wave_period_s: number;
  wind_wave_height_m?: number | null;
  swell_wave_height_m?: number | null;
  ocean_current_speed_kmh?: number | null;
  ocean_current_direction_deg?: number | null;
  sea_surface_temp_c?: number | null;
  sea_state: string;
  pfz_advisory: string;
}

/** Official METAR flight weather observation */
export interface AviationWeather {
  source: string;
  data_quality?: "verified" | "synthetic";
  icao_code: string;
  station_name: string;
  lat: number;
  lon: number;
  observed_at: string;
  flight_category: "VFR" | "MVFR" | "IFR" | "LIFR";
  raw_metar: string;
  temperature_c?: number | null;
  dewpoint_c?: number | null;
  wind_speed_kt?: number | null;
  wind_direction_deg?: number | null;
  wind_gust_kt?: number | null;
  visibility_sm?: number | null;
  visibility_m?: number | null;
  altimeter_hpa?: number | null;
  cloud_cover?: string | null;
  weather_phenomena?: string | null;
}

/** ICAR / IMD Agromet crop phenological advisory */
export interface CropAdvisoryReport {
  source: string;
  data_quality?: "verified" | "synthetic";
  crop: string;
  stage: string;
  location_name: string;
  issued_at: string;
  forecast_rain_sum_mm: number;
  forecast_temp_max_c: number;
  forecast_temp_min_c: number;
  irrigation_advisory: string;
  spray_advisory: string;
  field_operation_advisory: string;
  pest_disease_alerts: string[];
}

/** Monthly climate normal */
export interface MonthlyClimateNormal {
  month: number;
  month_name: string;
  mean_temp_c?: number | null;
  mean_precipitation_mm?: number | null;
}

/** ECMWF ERA5 multi-decadal climate analysis and trend report */
export interface ClimatologyReport {
  source: string;
  data_quality?: "verified" | "synthetic";
  location_name: string;
  lat: number;
  lon: number;
  baseline_period: string;
  variable: string;
  annual_mean: number;
  annual_min: number;
  annual_max: number;
  std_dev: number;
  warming_trend_c_per_decade?: number | null;
  recent_anomaly?: number | null;
  monthly_normals: MonthlyClimateNormal[];
  narrative_summary: string;
}

// ---------------------------------------------------------------------------
// Disaster & Common Alerting Protocol (CAP) Models
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

/** Initial snapshot sent over WebSocket upon connection */
export interface WebSocketInitMessage {
  type: "init";
  timestamp: string;
  active_alerts_count: number;
  alerts: AlertRecord[];
}

/** Live real-time disaster broadcast pushed over WebSocket */
export interface WebSocketAlertMessage {
  type: "weather_alert";
  timestamp: string;
  alert: AlertRecord;
}

export type WebSocketMessage = WebSocketInitMessage | WebSocketAlertMessage;

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
  status: "ok" | "degraded" | "error";
  database: "connected" | "disconnected";
  redis: "connected" | "disconnected";
  scheduler_running: boolean;
}
