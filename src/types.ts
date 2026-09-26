export type Status = {
  listener: { connected: boolean; degraded?: boolean; connected_count?: number; source_count?: number; message: string; sources?: Record<string, { connected: boolean; url: string; message: string }> };
  sources: string[];
  device_count: number;
  global_quake_min_magnitude?: number;
  global_far_alert_enabled?: boolean;
  retention?: {
    max_events: number;
    max_decisions: number;
    max_pushes: number;
  };
  alert_levels?: {
    red_intensity: number;
    yellow_intensity: number;
    bark: Record<"red" | "yellow" | "blue", { level: string; volume?: string; sound: string; repeat?: number }>;
  };
};

export type Device = {
  id: number;
  name: string;
  push_type: "bark" | "ntfy" | "webhook";
  default_city: string;
  latitude: number;
  longitude: number;
  min_magnitude: number;
  max_distance_km: number;
  min_intensity: number;
};

export type LatestAlert = {
  event?: {
    event_id?: string;
    source?: string;
    epicenter: string;
    latitude: number;
    longitude: number;
    magnitude: number;
    depth_km: number;
    origin_time?: string;
    test: boolean;
  };
  decisions?: Array<{
    device_id?: number;
    device_name: string;
    distance_km: number;
    arrival_seconds: number;
    intensity: number;
    intensity_text: string;
    should_push: boolean;
    reason?: string;
    created_at?: string;
  }>;
};

export type Logs = {
  counts?: {
    events: number;
    decisions: number;
    pushes: number;
    triggered_events: number;
    notified_events: number;
    observed_events: number;
    observed_recorded: number;
  };
  events: Array<{
    event_id: string;
    source: string;
    epicenter: string;
    magnitude: number;
    depth_km: number;
    origin_time: string;
    test?: number | boolean;
    updated_at: string;
  }>;
  decisions: Array<{
    event_id: string;
    distance_km: number;
    arrival_seconds: number;
    intensity: number;
    intensity_text: string;
    should_push: number | boolean;
    reason: string;
    pushed: number | boolean;
    created_at: string;
  }>;
  pushes: Array<{
    id: number;
    event_id: string;
    device_name?: string;
    epicenter?: string;
    magnitude?: number;
    test?: number | boolean;
    push_phase?: string;
    channel: string;
    ok: number | boolean;
    status_code?: number;
    latency_ms?: number;
    message: string;
    created_at: string;
  }>;
  observed_events: Array<{
    event_id: string;
    source: string;
    epicenter: string;
    latitude: number;
    longitude: number;
    magnitude: number;
    depth_km: number;
    origin_time: string;
    recorded: number | boolean;
    reason: string;
    updated_at: string;
  }>;
};

export type PushEventGroup = {
  key: string;
  event_id: string;
  epicenter: string;
  magnitude?: number;
  test?: number | boolean;
  phases: Set<string>;
  devices: Set<string>;
  attempts: number;
  okCount: number;
  latencyMs: number;
  latestAt: string;
};

export type SystemConfig = {
  wolfx_enabled: boolean;
  wolfx_ws_url: string;
  wolfx_ws_base: string;
  wolfx_sources: string[];
  global_enabled: boolean;
  global_source_url: string;
  global_min_magnitude: number;
  global_far_alert_enabled: boolean;
  source_health_alert_enabled: boolean;
  source_health_alert_after_seconds: number;
  alert_red_intensity: number;
  alert_yellow_intensity: number;
  bark_red_level: string;
  bark_red_volume: string;
  bark_red_sound: string;
  bark_red_repeat: number;
  bark_red_repeat_gap_seconds: number;
  bark_yellow_level: string;
  bark_yellow_volume: string;
  bark_yellow_sound: string;
  bark_yellow_repeat: number;
  bark_yellow_repeat_gap_seconds: number;
  bark_blue_level: string;
  bark_blue_volume: string;
  bark_blue_sound: string;
  bark_blue_repeat: number;
  bark_blue_repeat_gap_seconds: number;
};

export type DrillPreset = {
  id: string;
  source?: string;
  name: string;
  tag: string;
  epicenter: string;
  latitude: number;
  longitude: number;
  magnitude: number;
  depth_km: number;
  distance_km: number;
  countdown_seconds: number;
  intensity: number;
  target_city: string;
  target_latitude: number;
  target_longitude: number;
};
