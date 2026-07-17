import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Circle, MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./styles.css";

type Status = {
  listener: { connected: boolean; message: string; sources?: Record<string, { connected: boolean; url: string; message: string }> };
  sources: string[];
  device_count: number;
  global_quake_min_magnitude?: number;
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

type Device = {
  id: number;
  name: string;
  default_city: string;
  latitude: number;
  longitude: number;
  min_magnitude: number;
  max_distance_km: number;
  min_intensity: number;
};

type LatestAlert = {
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
    created_at?: string;
  }>;
};

type Logs = {
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

type PushEventGroup = {
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

type SystemConfig = {
  wolfx_enabled: boolean;
  wolfx_ws_url: string;
  wolfx_ws_base: string;
  wolfx_sources: string[];
  global_enabled: boolean;
  global_source_url: string;
  global_min_magnitude: number;
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

type DrillPreset = {
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

const chengdu = { lat: 30.5728, lng: 104.0668 };
const fallbackEpicenter = { lat: 28.43, lng: 104.71 };
const cityCoords: Record<string, { lat: number; lng: number }> = {
  成都: chengdu,
  重庆: { lat: 29.563, lng: 106.5516 },
  绵阳: { lat: 31.4675, lng: 104.6796 },
  德阳: { lat: 31.1268, lng: 104.3979 },
  乐山: { lat: 29.5521, lng: 103.7654 },
  宜宾: { lat: 28.7513, lng: 104.6417 },
  泸州: { lat: 28.8718, lng: 105.4423 },
  雅安: { lat: 30.0154, lng: 103.0398 },
  南充: { lat: 30.8373, lng: 106.1107 },
  自贡: { lat: 29.3392, lng: 104.7784 },
};

const sourceOptions = [
  ["sc_eew", "四川地震预警"],
  ["cq_eew", "重庆地震预警"],
  ["cenc_eew", "中国地震台网"],
  ["fj_eew", "福建地震预警"],
  ["jma_eew", "日本气象厅"],
  ["all_eew", "全部 Wolfx 源"],
] as const;

const barkLevelOptions = [
  ["critical", "最高级强提醒"],
  ["timeSensitive", "及时提醒"],
  ["active", "普通提醒"],
  ["passive", "静默/低打扰"],
] as const;

const defaultSystemConfig: SystemConfig = {
  wolfx_enabled: true,
  wolfx_ws_url: "",
  wolfx_ws_base: "wss://ws-api.wolfx.jp",
  wolfx_sources: ["sc_eew", "cq_eew", "cenc_eew"],
  global_enabled: true,
  global_source_url: "wss://www.seismicportal.eu/standing_order/websocket",
  global_min_magnitude: 7.5,
  alert_red_intensity: 4,
  alert_yellow_intensity: 2,
  bark_red_level: "critical",
  bark_red_volume: "8",
  bark_red_sound: "alarm",
  bark_red_repeat: 1,
  bark_red_repeat_gap_seconds: 0,
  bark_yellow_level: "critical",
  bark_yellow_volume: "4",
  bark_yellow_sound: "alarm",
  bark_yellow_repeat: 1,
  bark_yellow_repeat_gap_seconds: 0,
  bark_blue_level: "timeSensitive",
  bark_blue_volume: "",
  bark_blue_sound: "alarm",
  bark_blue_repeat: 1,
  bark_blue_repeat_gap_seconds: 0,
};

const drillPresets: DrillPreset[] = [
  {
    id: "wenchuan-2008",
    name: "2008 汶川 M8.0",
    tag: "强烈避险",
    epicenter: "四川阿坝州汶川县",
    latitude: 31.0,
    longitude: 103.4,
    magnitude: 8.0,
    depth_km: 14,
    distance_km: 86,
    countdown_seconds: 18,
    intensity: 5,
    target_city: "成都",
    target_latitude: chengdu.lat,
    target_longitude: chengdu.lng,
  },
  {
    id: "luding-2022",
    name: "2022 泸定 M6.8",
    tag: "明显有感",
    epicenter: "四川甘孜州泸定县",
    latitude: 29.59,
    longitude: 102.08,
    magnitude: 6.8,
    depth_km: 16,
    distance_km: 225,
    countdown_seconds: 43,
    intensity: 3,
    target_city: "成都",
    target_latitude: chengdu.lat,
    target_longitude: chengdu.lng,
  },
  {
    id: "jiuzhaigou-2017",
    name: "2017 九寨沟 M7.0",
    tag: "远场提醒",
    epicenter: "四川阿坝州九寨沟县",
    latitude: 33.2,
    longitude: 103.82,
    magnitude: 7.0,
    depth_km: 20,
    distance_km: 293,
    countdown_seconds: 63,
    intensity: 1,
    target_city: "成都",
    target_latitude: chengdu.lat,
    target_longitude: chengdu.lng,
  },
  {
    id: "chile-2010-global",
    source: "emsc_global",
    name: "2010 智利 M8.8",
    tag: "全球远场",
    epicenter: "智利马乌莱近海",
    latitude: -35.91,
    longitude: -72.73,
    magnitude: 8.8,
    depth_km: 35,
    distance_km: 18600,
    countdown_seconds: 0,
    intensity: 1,
    target_city: "成都",
    target_latitude: chengdu.lat,
    target_longitude: chengdu.lng,
  },
];

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("eewAuthToken") || "";
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function severity(intensity = 0, levels?: Status["alert_levels"]) {
  if (intensity >= (levels?.red_intensity ?? 4)) return "red";
  if (intensity >= (levels?.yellow_intensity ?? 2)) return "yellow";
  return "blue";
}

function cardTitle(seconds: number, city: string) {
  if (seconds > 0) return "地震横波即将到达";
  return `地震横波已到达${city || "你的位置"}`;
}

function formatEventTime(value?: string) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知";
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function timeMs(value?: string) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
}

function sourceName(name: string) {
  const names: Record<string, string> = {
    sc_eew: "四川地震预警",
    cq_eew: "重庆地震预警",
    cenc_eew: "中国地震台网",
    fj_eew: "福建地震预警",
    jma_eew: "日本气象厅",
    drill: "演练",
    test: "测试通知",
    wolfx: "Wolfx",
    emsc_global: "EMSC 全球地震",
  };
  return names[name] ?? name;
}

function sourceLabel(name: string) {
  const translated = sourceName(name);
  return translated === name ? name : `${name} · ${translated}`;
}

function pushPhaseText(phase?: string) {
  if (phase === "arrival") return "到达";
  if (phase === "test") return "测试";
  return "发现";
}

function barkLevelText(value: string) {
  return barkLevelOptions.find(([level]) => level === value)?.[1] ?? value;
}

function repeatText(value: number) {
  return `${Math.max(1, Number(value) || 1)} 次`;
}

function canonicalLogEventId(eventId: string) {
  return eventId.replace(/^(\d{12}\.\d+)_\d+$/, "$1");
}

function parseBarkKey(value: string) {
  const trimmed = value.trim();
  try {
    const url = new URL(trimmed);
    const key = url.pathname.split("/").filter(Boolean)[0];
    return key || trimmed;
  } catch {
    return trimmed.replace(/^\/+/, "").split("/")[0] || trimmed;
  }
}

function coordsFor(city: string, latitude: string, longitude: string) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (Number.isFinite(lat) && Number.isFinite(lng)) return { lat, lng };
  const normalized = city.replace(/市$/, "").trim();
  return cityCoords[normalized] ?? chengdu;
}

function FitMap({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length >= 2) map.fitBounds(points, { padding: [44, 44] });
  }, [map, points]);
  return null;
}

function App() {
  const [routePath] = useState(() => window.location.pathname);
  const [detailEventId] = useState(() => {
    const eventPath = window.location.pathname.match(/^\/event\/([^/]+)$/);
    return eventPath?.[1] ? decodeURIComponent(eventPath[1]) : new URLSearchParams(window.location.search).get("event_id") || "";
  });
  const [detailDeviceId] = useState(() => {
    const id = new URLSearchParams(window.location.search).get("device_id");
    const value = Number(id);
    return Number.isFinite(value) && value > 0 ? value : null;
  });
  const [status, setStatus] = useState<Status | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [latest, setLatest] = useState<LatestAlert>({});
  const [logs, setLogs] = useState<Logs>({ events: [], decisions: [], pushes: [], observed_events: [] });
  const [message, setMessage] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedDrill, setSelectedDrill] = useState(drillPresets[0].id);
  const [alertStartedAt, setAlertStartedAt] = useState(Date.now());
  const [nowMs, setNowMs] = useState(Date.now());
  const [hideTestHistory, setHideTestHistory] = useState(false);
  const [detailNotFound, setDetailNotFound] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const configDirtyRef = useRef(false);
  const [systemConfig, setSystemConfig] = useState<SystemConfig>(defaultSystemConfig);
  const [form, setForm] = useState({
    name: "",
    bark_key: "",
    default_city: "成都",
    latitude: "",
    longitude: "",
    min_magnitude: "4.5",
    max_distance_km: "500",
    min_intensity: "2",
  });

  async function refresh() {
    const nextAlert = detailEventId
      ? api<LatestAlert>(`/api/alerts/${encodeURIComponent(detailEventId)}`)
          .then((value) => {
            setDetailNotFound(false);
            return value;
          })
          .catch(() => {
            setDetailNotFound(true);
            return {};
          })
      : api<LatestAlert>("/api/latest-alert");
    const [nextStatus, nextDevices, nextLatest, nextLogs, nextConfig] = await Promise.all([
      api<Status>("/api/status"),
      api<Device[]>("/api/devices"),
      nextAlert,
      api<Logs>("/api/logs"),
      api<SystemConfig>("/api/system-config"),
    ]);
    setStatus(nextStatus);
    setDevices(nextDevices);
    setLatest(nextLatest);
    setLogs(nextLogs);
    if (!configDirtyRef.current) setSystemConfig({ ...defaultSystemConfig, ...nextConfig });
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
    const id = window.setInterval(() => refresh().catch(() => undefined), 5000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  function editDevice(device: Device) {
    setEditingId(device.id);
    setForm({
      name: device.name,
      bark_key: "",
      default_city: device.default_city || "成都",
      latitude: String(device.latitude || ""),
      longitude: String(device.longitude || ""),
      min_magnitude: String(device.min_magnitude),
      max_distance_km: String(device.max_distance_km),
      min_intensity: String(device.min_intensity),
    });
    setMessage("正在编辑已有 Apple 设备。Bark Key 留空则不改。");
  }

  const selectedPreset = drillPresets.find((item) => item.id === selectedDrill) ?? drillPresets[0];
  const event = latest.event ?? {
    event_id: selectedPreset.id,
    epicenter: selectedPreset.epicenter,
    latitude: selectedPreset.latitude,
    longitude: selectedPreset.longitude,
    magnitude: selectedPreset.magnitude,
    depth_km: selectedPreset.depth_km,
    test: true,
  };
  const selectedDecision = detailDeviceId
    ? latest.decisions?.find((item) => item.device_id === detailDeviceId)
    : latest.decisions?.[0];
  const decision = selectedDecision ?? {
    device_id: devices[0]?.id,
    device_name: devices[0]?.name ?? "成都 Apple 设备",
    distance_km: selectedPreset.distance_km,
    arrival_seconds: selectedPreset.countdown_seconds,
    intensity: selectedPreset.intensity,
    intensity_text: selectedPreset.tag,
    should_push: true,
  };
  useEffect(() => {
    setAlertStartedAt(Date.now());
  }, [event.event_id, event.epicenter, event.magnitude]);
  const countdownBaseMs = timeMs(decision.created_at) ?? alertStartedAt;
  const elapsedSeconds = Math.max(0, Math.floor((nowMs - countdownBaseMs) / 1000));
  const liveArrivalSeconds = Math.max(-90, decision.arrival_seconds - elapsedSeconds);
  const activeDevice = detailDeviceId
    ? devices.find((item) => item.id === detailDeviceId)
    : devices.find((item) => item.name === decision.device_name) ?? devices[0];
  const user = activeDevice ? { lat: activeDevice.latitude, lng: activeDevice.longitude } : chengdu;
  const epicenter: [number, number] = [event.latitude || fallbackEpicenter.lat, event.longitude || fallbackEpicenter.lng];
  const userPoint: [number, number] = [user.lat || chengdu.lat, user.lng || chengdu.lng];
  const waveKm = Math.max(35, Math.min(760, Math.abs(liveArrivalSeconds) * 3.5 + 90));
  const level = severity(decision.intensity, status?.alert_levels);
  const sourceStates = Object.entries(status?.listener.sources ?? {});
  const connectedSources = sourceStates.filter(([, state]) => state.connected).length;
  const visiblePushes = logs.pushes.filter((item) => !hideTestHistory || !item.test);
  const visibleEvents = logs.events.filter((item) => !hideTestHistory || !item.test);
  const visibleObservedEvents = logs.observed_events.filter((item, index, items) => {
    const key = canonicalLogEventId(item.event_id);
    return items.findIndex((candidate) => canonicalLogEventId(candidate.event_id) === key) === index;
  });
  const dedupedVisibleEvents = visibleEvents.filter((item, index, items) => {
    const key = canonicalLogEventId(item.event_id);
    return items.findIndex((candidate) => canonicalLogEventId(candidate.event_id) === key) === index;
  });
  const groupedPushEvents = Array.from(visiblePushes.reduce((groups, item) => {
    const key = canonicalLogEventId(item.event_id);
    const current = groups.get(key);
    const itemTime = timeMs(item.created_at) ?? 0;
    if (!current) {
      groups.set(key, {
        key,
        event_id: item.event_id,
        epicenter: item.epicenter || "地震事件",
        magnitude: item.magnitude,
        test: item.test,
        phases: new Set([item.push_phase || "initial"]),
        devices: new Set([item.device_name || "Apple 设备"]),
        attempts: 1,
        okCount: item.ok ? 1 : 0,
        latencyMs: item.latency_ms ?? 0,
        latestAt: item.created_at,
      });
      return groups;
    }
    current.phases.add(item.push_phase || "initial");
    current.devices.add(item.device_name || "Apple 设备");
    current.attempts += 1;
    current.okCount += item.ok ? 1 : 0;
    current.latencyMs += item.latency_ms ?? 0;
    if (item.epicenter) current.epicenter = item.epicenter;
    if (typeof item.magnitude === "number") current.magnitude = item.magnitude;
    if (item.test !== undefined) current.test = item.test;
    if (itemTime > (timeMs(current.latestAt) ?? 0)) {
      current.event_id = item.event_id;
      current.latestAt = item.created_at;
    }
    return groups;
  }, new Map<string, PushEventGroup>()).values()).sort((a, b) => (timeMs(b.latestAt) ?? 0) - (timeMs(a.latestAt) ?? 0));
  const decisionByEvent = new Map(logs.decisions.map((item) => [item.event_id, item]));
  const displayCity = activeDevice?.default_city || "成都";
  const isFarGlobalBrief = event.source === "emsc_global" && decision.distance_km > (activeDevice?.max_distance_km ?? 500);
  const isEventHistoryPage = routePath === "/history";
  const isCatalogPage = routePath === "/catalog";
  const isPushHistoryPage = routePath === "/pushes";
  const isRulesPage = routePath === "/rules";
  const isSettingsPage = routePath === "/settings";

  async function locate() {
    if (!navigator.geolocation) {
      setMessage("当前浏览器不支持定位，可以手动填写经纬度。");
      return;
    }
    setMessage("正在请求定位权限...");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setForm((current) => ({
          ...current,
          latitude: position.coords.latitude.toFixed(6),
          longitude: position.coords.longitude.toFixed(6),
        }));
        setMessage(`已填入当前位置，精度约 ${Math.round(position.coords.accuracy)} 米。`);
      },
      () => setMessage("定位失败。可以只填城市，系统会用常见城市坐标；也可以手动填写经纬度。"),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
    );
  }

  async function saveDevice(event: React.FormEvent) {
    event.preventDefault();
    const location = coordsFor(form.default_city, form.latitude, form.longitude);
    const key = parseBarkKey(form.bark_key);
    const payload: Record<string, unknown> = {
      name: form.name.trim() || "你的 Apple 设备",
      push_type: "bark",
      push_url: "",
      default_city: form.default_city || "成都",
      latitude: location.lat,
      longitude: location.lng,
      min_magnitude: Number(form.min_magnitude),
      max_distance_km: Number(form.max_distance_km),
      min_intensity: Number(form.min_intensity),
    };
    if (!editingId) {
      payload.enabled = true;
      payload.receive_tests = true;
    }
    if (key || !editingId) payload.bark_key = key;

    if (editingId) {
      await api(`/api/devices/${editingId}`, { method: "PATCH", body: JSON.stringify(payload) });
      setMessage("Apple 设备已更新。");
    } else {
      await api("/api/devices", { method: "POST", body: JSON.stringify(payload) });
      setMessage("Apple 设备已保存。下一步点“测试通知”。");
    }
    setEditingId(null);
    await refresh();
  }

  async function testPush() {
    if (!devices[0]) {
      setMessage("先添加一台 Apple 设备。");
      return;
    }
    const result = await api<{ ok: boolean; latency_ms: number; message: string }>("/api/test-push", {
      method: "POST",
      body: JSON.stringify({ device_id: devices[0].id }),
    });
    setMessage(result.ok ? `测试通知已发出，用时 ${result.latency_ms} ms。` : `推送失败：${result.message}`);
  }

  async function runDrill() {
    await api("/api/simulate", {
      method: "POST",
      body: JSON.stringify(selectedPreset),
    });
    setMessage(`已启动 ${selectedPreset.name} 演练。`);
    await refresh();
  }

  async function clearPushHistory() {
    if (!window.confirm("确定清除推送历史吗？地震历史会保留。")) return;
    await api<{ ok: boolean }>("/api/logs/pushes", { method: "DELETE" });
    setMessage("推送历史已清除。");
    await refresh();
  }

  async function clearEventHistory() {
    if (!window.confirm("确定清除地震历史吗？相关判断和推送记录也会一起清除。")) return;
    await api<{ ok: boolean }>("/api/logs/events", { method: "DELETE" });
    setMessage("地震历史已清除。");
    await refresh();
  }

  function updateSystemConfig(patch: Partial<SystemConfig>) {
    configDirtyRef.current = true;
    setConfigDirty(true);
    setSystemConfig((current) => ({ ...current, ...patch }));
  }

  function toggleSource(source: string) {
    const sources = systemConfig.wolfx_sources.includes(source)
      ? systemConfig.wolfx_sources.filter((item) => item !== source)
      : [...systemConfig.wolfx_sources, source];
    updateSystemConfig({ wolfx_sources: sources });
  }

  async function saveSystemConfig() {
    const saved = await api<SystemConfig>("/api/system-config", {
      method: "PATCH",
      body: JSON.stringify({
        ...systemConfig,
        global_min_magnitude: Number(systemConfig.global_min_magnitude),
        alert_red_intensity: Number(systemConfig.alert_red_intensity),
        alert_yellow_intensity: Number(systemConfig.alert_yellow_intensity),
      }),
    });
    setSystemConfig({ ...defaultSystemConfig, ...saved });
    configDirtyRef.current = false;
    setConfigDirty(false);
    setMessage("系统配置已保存，监听源已按新配置重连。");
    await refresh();
  }

  const alertCard = (
    <section className={`alertCard ${level}`}>
      <div className="alertHead">
        {detailEventId && <a className="alertBack" href="/">返回首页</a>}
        <span>{event.test ? "演练/示例" : "实时预警"}</span>
      </div>
      <h2>{isFarGlobalBrief ? "全球特大地震预警" : cardTitle(liveArrivalSeconds, displayCity)}</h2>
      <strong>{isFarGlobalBrief ? `M${event.magnitude.toFixed(1)}` : liveArrivalSeconds > 0 ? `${liveArrivalSeconds} 秒` : "已到达"}</strong>
      <div className="bigMetrics">
        <div><span>距离</span><b>{Math.round(decision.distance_km)} km</b></div>
        <div><span>震级</span><b>M{event.magnitude.toFixed(1)}</b></div>
        <div><span>烈度</span><b>{decision.intensity}</b></div>
        <div><span>震感</span><b>{decision.intensity_text}</b></div>
        <div><span>震中</span><b>{event.epicenter}</b></div>
        <div><span>深度</span><b>{event.depth_km} km</b></div>
        <div><span>地震时间</span><b>{formatEventTime(event.origin_time)}</b></div>
        <div><span>预警来源</span><b>{sourceName(event.source || "unknown")}</b></div>
      </div>
      <div className="tips">勿慌乱、先躲避、后撤离、找空间、保护头、忌电梯。</div>
    </section>
  );

  const mapSection = (
    <section className="mapPanel">
      <div className="sectionHead">
        <div>
          <h2>震中、你的位置和地震波</h2>
        </div>
        <span>{activeDevice?.default_city || "成都默认位置"}</span>
      </div>
      <MapContainer center={userPoint} zoom={7} scrollWheelZoom={false} className="map">
        <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <FitMap points={[epicenter, userPoint]} />
        <Circle center={epicenter} radius={waveKm * 1000} pathOptions={{ color: level === "red" ? "#dc2626" : level === "yellow" ? "#d97706" : "#2563eb", fillOpacity: 0.08, weight: 2 }} />
        <Polyline positions={[epicenter, userPoint]} pathOptions={{ color: "#1f2937", weight: 2, dashArray: "7 9" }} />
        <Marker position={epicenter} icon={L.divIcon({ className: `pin epicenter pulse ${level}`, html: "<span>震</span>" })}><Popup>{event.epicenter}</Popup></Marker>
        <Marker position={userPoint} icon={L.divIcon({ className: "pin user", html: "我" })}><Popup>{activeDevice?.default_city || "成都"}</Popup></Marker>
      </MapContainer>
    </section>
  );

  const renderPushHistorySection = (limit?: number) => (
    <section className="panel historyPanel">
      <div className="sectionHead">
        <div>
          <h2>推送历史</h2>
        </div>
        <div className="historyActions">
          <label className="toggle"><input type="checkbox" checked={hideTestHistory} onChange={(event) => setHideTestHistory(event.target.checked)} />隐藏测试</label>
          <span>{groupedPushEvents.length} 条</span>
          <button className="dangerButton" onClick={clearPushHistory}>清除推送历史</button>
        </div>
      </div>
      <div className="historyList">
        {groupedPushEvents.slice(0, limit ?? groupedPushEvents.length).map((item) => {
          const phases = Array.from(item.phases)
            .sort((a, b) => ["initial", "arrival", "test"].indexOf(a) - ["initial", "arrival", "test"].indexOf(b))
            .map(pushPhaseText)
            .join(" / ");
          return (
          <a key={item.key} className="historyItem" href={`/event/${encodeURIComponent(item.event_id)}`}>
            <span>{item.test ? "测试" : "预警"} · {item.epicenter}</span>
            <small>{item.devices.size} 台设备 · {phases} · {item.okCount}/{item.attempts} 成功 · 总耗时 {item.latencyMs} ms</small>
            <b>{typeof item.magnitude === "number" ? `M${item.magnitude.toFixed(1)}` : `${item.attempts} 次`}</b>
          </a>
          );
        })}
      </div>
    </section>
  );

  const renderEventLogSection = (limit?: number) => (
    <section className="panel eventLogPanel">
      <div className="sectionHead">
        <div>
          <h2>地震历史</h2>
        </div>
        <div className="historyActions">
          <label className="toggle"><input type="checkbox" checked={hideTestHistory} onChange={(event) => setHideTestHistory(event.target.checked)} />隐藏测试</label>
          <span>{dedupedVisibleEvents.length} 条</span>
          <button className="dangerButton" onClick={clearEventHistory}>清除地震历史</button>
        </div>
      </div>
      <div className="eventLogList">
        {dedupedVisibleEvents.slice(0, limit ?? dedupedVisibleEvents.length).map((item) => {
          const canonicalId = canonicalLogEventId(item.event_id);
          const itemDecision = decisionByEvent.get(item.event_id) ?? decisionByEvent.get(canonicalId);
          const shouldPush = Boolean(itemDecision?.should_push);
          const decisionText = itemDecision
            ? `${Math.round(itemDecision.distance_km)}km · 烈度 ${itemDecision.intensity} · ${itemDecision.intensity_text}`
            : "未计算";
          return (
            <a key={item.event_id} className="eventLogItem" href={`/event/${encodeURIComponent(item.event_id)}`}>
              <div>
                <span>{item.epicenter}</span>
                <small>{sourceName(item.source)} · {formatEventTime(item.origin_time)}</small>
              </div>
              <b>M{item.magnitude.toFixed(1)}</b>
              <small>{decisionText}</small>
              <em className={shouldPush ? "pushed" : "notPushed"}>{shouldPush ? "已推送" : itemDecision?.reason || "未推送"}</em>
            </a>
          );
        })}
      </div>
    </section>
  );

  const renderCatalogSection = (limit?: number) => (
    <section className="panel eventLogPanel">
      <div className="sectionHead">
        <div>
          <h2>监听目录</h2>
        </div>
        <div className="historyActions">
          <span>{visibleObservedEvents.length} 条</span>
        </div>
      </div>
      <div className="eventLogList">
        {visibleObservedEvents.slice(0, limit ?? visibleObservedEvents.length).map((item) => {
          const inWarningHistory = Boolean(item.recorded);
          return (
            <a
              key={item.event_id}
              className="eventLogItem"
              href={inWarningHistory ? `/event/${encodeURIComponent(item.event_id)}` : "/catalog"}
            >
              <div>
                <span>{item.epicenter}</span>
                <small>{sourceName(item.source)} · {formatEventTime(item.origin_time)}</small>
              </div>
              <b>M{item.magnitude.toFixed(1)}</b>
              <small>深度 {item.depth_km} km</small>
              <em className={inWarningHistory ? "pushed" : "notPushed"}>{item.reason || (inWarningHistory ? "已入预警历史" : "仅监听到")}</em>
            </a>
          );
        })}
      </div>
    </section>
  );

  const historyLinks = (
    <section className="panel historyNavPanel">
      <div className="sectionHead">
        <div>
          <h2>功能菜单</h2>
        </div>
      </div>
      <div className="historyNav">
        <a href="/history">
          <span>地震历史</span>
          <b>{dedupedVisibleEvents.length} 条</b>
        </a>
        <a href="/catalog">
          <span>监听目录</span>
          <b>{visibleObservedEvents.length} 条</b>
        </a>
        <a href="/pushes">
          <span>推送历史</span>
          <b>{groupedPushEvents.length} 条</b>
        </a>
        <a href="/rules">
          <span>规则说明</span>
          <b>入库 / 推送</b>
        </a>
        <a href="/settings">
          <span>推送设置</span>
          <b>红 / 黄 / 蓝</b>
        </a>
      </div>
    </section>
  );

  const historyPageHeader = (title: string, description: string) => (
    <section className="pageHeader panel">
      <a className="textButton" href="/">返回首页</a>
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
    </section>
  );

  const rulesPage = (
    <main className="appShell">
      {historyPageHeader("规则说明", "")}
      <section className="panel rulesPanel">
        <div className="rulesGrid">
          <div>
            <h2>哪些地震会进入历史</h2>
            <ul>
              <li>国内预警源收到的地震会记录，用于追踪报数、修正报和取消报。</li>
              <li>全球 EMSC 事件只有两类会记录：全球特大地震 M{status?.global_quake_min_magnitude ?? 7.5}+，或对某台设备同时满足距离、震级和本地烈度。</li>
              <li>EMSC 本地烈度要求至少为 2，并且不低于这台设备设置的最低烈度。</li>
              <li>未进入预警历史的 EMSC 事件会进入监听目录，用来确认系统确实听到了哪些事件。</li>
              <li>测试通知和演练会记录，方便检查推送是否正常。</li>
            </ul>
          </div>
          <div>
            <h2>什么时候会推送</h2>
            <ul>
              <li>演练会推送给允许接收测试的设备。</li>
              <li>全球特大地震 M{status?.global_quake_min_magnitude ?? 7.5}+ 会温和提醒，即使离你很远；远距离全球提醒不显示本地倒计时。</li>
              <li>EMSC 全球源的非特大地震，必须对某台设备同时满足距离、震级和本地烈度才会推送。</li>
              <li>国内预警源优先按设备阈值推送；如果预计烈度达到 2 以上，也会按“可能有感”兜底提醒。</li>
            </ul>
          </div>
          <div>
            <h2>不会记录的情况</h2>
            <ul>
              <li>远距离全球小震不会只因为被数据源收到就进入历史。</li>
              <li>未达到全球特大震级，也没有本地相关烈度的事件不会记录。</li>
              <li>设备已停用时，不会为这台设备产生推送判断。</li>
              <li>取消报不会触发新的推送。</li>
            </ul>
          </div>
        </div>
      </section>
      <section className="panel rulesPanel compactRules">
        <h2>当前设备阈值</h2>
        <div className="ruleDeviceList">
          {devices.length ? devices.map((device) => (
            <div key={device.id}>
              <span>{device.name}</span>
              <small>{device.default_city || "未设置城市"} · M{device.min_magnitude}+ · {device.max_distance_km}km 内 · 烈度 {device.min_intensity}+</small>
            </div>
          )) : <p>还没有 Apple 设备。</p>}
        </div>
      </section>
    </main>
  );

  const settingsPage = (
    <main className="appShell">
      {historyPageHeader("推送设置", "")}
      <section className="panel pushSummary">
        <div>
          <h2>当前提醒方式</h2>
          <p>红色：烈度 ≥ {systemConfig.alert_red_intensity}。发现时发送 {repeatText(systemConfig.bark_red_repeat)} {barkLevelText(systemConfig.bark_red_level)}，音量 {systemConfig.bark_red_volume || "默认"}，铃声 {systemConfig.bark_red_sound}，并使用持续响；如果横波尚未到达，到达时再发一次“已到达”。</p>
          <p>黄色：烈度 ≥ {systemConfig.alert_yellow_intensity}。发现时发送 {repeatText(systemConfig.bark_yellow_repeat)} {barkLevelText(systemConfig.bark_yellow_level)}，音量 {systemConfig.bark_yellow_volume || "默认"}，铃声 {systemConfig.bark_yellow_sound}；如果横波尚未到达，到达时再发一次。</p>
          <p>蓝色：低于黄色但仍需要提醒时使用。发现时发送 {repeatText(systemConfig.bark_blue_repeat)} {barkLevelText(systemConfig.bark_blue_level)}，音量 {systemConfig.bark_blue_volume || "默认"}，铃声 {systemConfig.bark_blue_sound}；如果横波尚未到达，到达时再发一次。</p>
        </div>
      </section>
      <section className="panel pushSettingsPanel">
        <div className="sectionHead">
          <div>
            <h2>红黄蓝参数</h2>
          </div>
          <button className="compact" onClick={saveSystemConfig}>保存配置</button>
        </div>
        <div className="pushSettingGrid">
          <div>
            <h3>红色</h3>
            <label>烈度 ≥<input value={systemConfig.alert_red_intensity} onChange={(event) => updateSystemConfig({ alert_red_intensity: Number(event.target.value) })} /></label>
            <label>提醒方式<select value={systemConfig.bark_red_level} onChange={(event) => updateSystemConfig({ bark_red_level: event.target.value })}>{barkLevelOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>音量<input value={systemConfig.bark_red_volume} onChange={(event) => updateSystemConfig({ bark_red_volume: event.target.value })} /></label>
            <label>铃声<input value={systemConfig.bark_red_sound} onChange={(event) => updateSystemConfig({ bark_red_sound: event.target.value })} /></label>
          </div>
          <div>
            <h3>黄色</h3>
            <label>烈度 ≥<input value={systemConfig.alert_yellow_intensity} onChange={(event) => updateSystemConfig({ alert_yellow_intensity: Number(event.target.value) })} /></label>
            <label>提醒方式<select value={systemConfig.bark_yellow_level} onChange={(event) => updateSystemConfig({ bark_yellow_level: event.target.value })}>{barkLevelOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>音量<input value={systemConfig.bark_yellow_volume} onChange={(event) => updateSystemConfig({ bark_yellow_volume: event.target.value })} /></label>
            <label>铃声<input value={systemConfig.bark_yellow_sound} onChange={(event) => updateSystemConfig({ bark_yellow_sound: event.target.value })} /></label>
          </div>
          <div>
            <h3>蓝色</h3>
            <label>提醒方式<select value={systemConfig.bark_blue_level} onChange={(event) => updateSystemConfig({ bark_blue_level: event.target.value })}>{barkLevelOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>音量<input value={systemConfig.bark_blue_volume} onChange={(event) => updateSystemConfig({ bark_blue_volume: event.target.value })} placeholder="可留空" /></label>
            <label>铃声<input value={systemConfig.bark_blue_sound} onChange={(event) => updateSystemConfig({ bark_blue_sound: event.target.value })} /></label>
          </div>
        </div>
        {message && <p className="message">{message}</p>}
      </section>
      <section className="panel configPanel">
        <div className="sectionHead">
          <div>
            <h2>系统配置</h2>
          </div>
          <button className="compact" onClick={saveSystemConfig}>保存配置</button>
        </div>
        <div className="settingsList">
          <div className="settingFull">
            <h3>监听源</h3>
            <div className="checkGrid">
              <label className="checkLine">
                <input type="checkbox" checked={systemConfig.wolfx_enabled} onChange={(event) => updateSystemConfig({ wolfx_enabled: event.target.checked })} />
                国内 Wolfx 地震预警
              </label>
              {sourceOptions.map(([value, label]) => (
                <label key={value} className="checkLine">
                  <input type="checkbox" checked={systemConfig.wolfx_sources.includes(value)} onChange={() => toggleSource(value)} />
                  {value} · {label}
                </label>
              ))}
            </div>
          </div>
          <div className="settingFull">
            <h3>全球特大地震</h3>
            <div className="settingPair">
              <label className="checkLine">
                <input type="checkbox" checked={systemConfig.global_enabled} onChange={(event) => updateSystemConfig({ global_enabled: event.target.checked })} />
                EMSC 全球 WebSocket
              </label>
              <label>
                全球推送最低震级
                <input value={systemConfig.global_min_magnitude} onChange={(event) => updateSystemConfig({ global_min_magnitude: Number(event.target.value) })} />
              </label>
            </div>
          </div>
          <div className="settingFull">
            <h3>源地址</h3>
            <label>
              Wolfx 基础地址
              <input value={systemConfig.wolfx_ws_base} onChange={(event) => updateSystemConfig({ wolfx_ws_base: event.target.value })} />
            </label>
            <label>
              自定义 Wolfx 地址，可留空
              <input value={systemConfig.wolfx_ws_url} onChange={(event) => updateSystemConfig({ wolfx_ws_url: event.target.value })} placeholder="多个地址用英文逗号分隔" />
            </label>
            <label>
              EMSC WebSocket 地址
              <input value={systemConfig.global_source_url} onChange={(event) => updateSystemConfig({ global_source_url: event.target.value })} />
            </label>
          </div>
        </div>
      </section>
    </main>
  );

  if (detailEventId && detailNotFound) {
    return (
      <main className="appShell detailShell">
        <section className="panel loadingPanel">
          <h1>预警不存在或已清除</h1>
          <p>这条通知对应的地震记录已经找不到。可以返回首页查看最近通知。</p>
          <a className="alertBack" href="/">返回首页</a>
        </section>
      </main>
    );
  }

  if (detailEventId && !latest.event) {
    return (
      <main className="appShell detailShell">
        <section className="panel loadingPanel">
          <h1>正在加载预警详情</h1>
          <p>请稍候。</p>
        </section>
      </main>
    );
  }

  if (detailEventId) {
    return (
      <main className="appShell detailShell">
        <section className="detailLayout">
          {alertCard}
          {mapSection}
        </section>
      </main>
    );
  }

  if (isEventHistoryPage) {
    return (
      <main className="appShell">
        {historyPageHeader(
          "地震历史",
          `只记录本地相关事件和全球 M${status?.global_quake_min_magnitude ?? 7.5}+ 特大地震。普通监听记录请看监听目录。`,
        )}
        {renderEventLogSection()}
      </main>
    );
  }

  if (isCatalogPage) {
    return (
      <main className="appShell">
        {historyPageHeader(
          "监听目录",
          "只显示系统从实时监听源收到的事件，不做定时目录拉取。",
        )}
        {renderCatalogSection()}
      </main>
    );
  }

  if (isPushHistoryPage) {
    return (
      <main className="appShell">
        {historyPageHeader(
          "推送历史",
          "测试通知和真实预警都在这里查看。",
        )}
        {renderPushHistorySection()}
      </main>
    );
  }

  if (isRulesPage) return rulesPage;
  if (isSettingsPage) return settingsPage;

  return (
    <main className="appShell">
      <section className="heroBlock">
        <div>
          <h1>Apple 设备地震预警系统</h1>
          <p className="heroText">为你的 Apple 设备提供地震预警提醒。可为每台设备单独设置位置和推送条件。</p>
        </div>
        <div className="statusCard">
          <div className="statusMain">
            <span className={status?.listener.connected ? "dot on" : "dot"} />
            <strong>{status?.listener.connected ? "实时监听中" : "监听未就绪"}</strong>
            <small>{connectedSources}/{sourceStates.length || status?.sources.length || 3} 个源在线</small>
          </div>
          <div className="sources compactSources">
            {sourceStates.length ? sourceStates.map(([name, state]) => (
              <div key={name}><span>{sourceLabel(name)}</span><strong>{state.connected ? "已连接" : "离线"}</strong></div>
            )) : <div><span>Wolfx</span><strong>等待中</strong></div>}
          </div>
        </div>
      </section>

      <section className="quick panel">
        <h2>快速开始</h2>
        <ol>
          <li>Bark App 服务器填 <b>https://h-bark.111184.xyz</b>。</li>
          <li>复制 Bark 推送地址或 Key，保存 Apple 设备。</li>
          <li>点“测试通知”确认 iPhone 能响。</li>
          <li>选择历史地震场景，点“开始演练”。</li>
        </ol>
      </section>

      <section className="panel devicePanel">
        <div className="sectionHead">
          <div>
            <h2>添加接收预警的 Apple 设备</h2>
          </div>
          <span>{devices.length} 台</span>
        </div>
        <form onSubmit={saveDevice}>
          <div className="two">
            <label>设备名称<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="你的 Apple 设备" /></label>
            <label>Bark Key 或从 Bark App 复制的推送地址<input value={form.bark_key} onChange={(e) => setForm({ ...form, bark_key: e.target.value })} placeholder="https://h-bark.111184.xyz/你的Key/推送内容" /></label>
          </div>
          <div className="three locationRow">
            <label>城市<input value={form.default_city} onChange={(e) => setForm({ ...form, default_city: e.target.value })} placeholder="成都" /></label>
            <label>纬度，可选<input value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} placeholder="留空则按城市估算" /></label>
            <label>经度，可选<input value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} placeholder="留空则按城市估算" /></label>
          </div>
          <div className="buttonRow">
            <button type="button" className="ghost" onClick={locate}>获取位置</button>
            <button>{editingId ? "保存修改" : "保存设备"}</button>
            <button type="button" className="secondary" onClick={testPush}>测试通知</button>
          </div>
          <details>
            <summary>每台设备独立推送阈值</summary>
            <div className="three">
              <label>最低震级<input value={form.min_magnitude} onChange={(e) => setForm({ ...form, min_magnitude: e.target.value })} /></label>
              <label>最大距离 km<input value={form.max_distance_km} onChange={(e) => setForm({ ...form, max_distance_km: e.target.value })} /></label>
              <label>最低烈度<input value={form.min_intensity} onChange={(e) => setForm({ ...form, min_intensity: e.target.value })} /></label>
            </div>
          </details>
        </form>
        {devices.length > 0 && (
          <div className="deviceList">
            {devices.map((device) => (
              <button key={device.id} className="deviceItem" onClick={() => editDevice(device)}>
                <span>{device.name}</span>
                <small>城市：{device.default_city || "未设置"} · 推送条件：震级 ≥ {device.min_magnitude}，距离 ≤ {device.max_distance_km} km，烈度 ≥ {device.min_intensity}</small>
                <b>编辑</b>
              </button>
            ))}
          </div>
        )}
        {message && <p className="message">{message}</p>}
      </section>

      <section className="panel drillPanel">
        <div className="sectionHead">
          <div>
            <h2>选择一个历史地震场景</h2>
          </div>
          <button className="compact" onClick={runDrill}>开始演练</button>
        </div>
        <div className="drillList threeCards">
          {drillPresets.map((preset) => (
            <button
              key={preset.id}
              className={`drillItem ${selectedDrill === preset.id ? "selected" : ""} ${severity(preset.intensity, status?.alert_levels)}`}
              onClick={() => setSelectedDrill(preset.id)}
            >
              <span>{preset.name}</span>
              <b>{preset.tag}</b>
              <small>{preset.epicenter} · {preset.source === "emsc_global" ? "全球远场预览" : `距成都约 ${preset.distance_km} km`}</small>
            </button>
          ))}
        </div>
      </section>

      {historyLinks}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
