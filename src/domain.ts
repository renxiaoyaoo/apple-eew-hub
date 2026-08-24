import type { Device, DrillPreset, LatestAlert, Status, SystemConfig } from "./types";

export const chengdu = { lat: 30.5728, lng: 104.0668 };
export const fallbackEpicenter = { lat: 28.43, lng: 104.71 };
export const cityCoords: Record<string, { lat: number; lng: number }> = {
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

export const sourceOptions = [
  ["sc_eew", "四川地震预警"],
  ["cq_eew", "重庆地震预警"],
  ["cenc_eew", "中国地震台网"],
  ["fj_eew", "福建地震预警"],
  ["jma_eew", "日本气象厅"],
  ["all_eew", "全部 Wolfx 源"],
] as const;

export const barkLevelOptions = [
  ["critical", "最高级强提醒"],
  ["timeSensitive", "及时提醒"],
  ["active", "普通提醒"],
  ["passive", "静默/低打扰"],
] as const;

export const defaultGlobalCatalogMagnitude = 4.5;
export const repoUrl = "https://github.com/renxiaoyaoo/apple-eew-hub";

export const defaultSystemConfig: SystemConfig = {
  wolfx_enabled: true,
  wolfx_ws_url: "",
  wolfx_ws_base: "wss://ws-api.wolfx.jp",
  wolfx_sources: ["sc_eew", "cq_eew", "cenc_eew", "jma_eew"],
  global_enabled: true,
  global_source_url: "wss://www.seismicportal.eu/standing_order/websocket",
  global_min_magnitude: 7.0,
  global_far_alert_enabled: true,
  alert_red_intensity: 4,
  alert_yellow_intensity: 2,
  bark_red_level: "critical",
  bark_red_volume: "8",
  bark_red_sound: "alarm",
  bark_red_repeat: 1,
  bark_red_repeat_gap_seconds: 0,
  bark_yellow_level: "timeSensitive",
  bark_yellow_volume: "4",
  bark_yellow_sound: "alarm",
  bark_yellow_repeat: 1,
  bark_yellow_repeat_gap_seconds: 0,
  bark_blue_level: "active",
  bark_blue_volume: "",
  bark_blue_sound: "",
  bark_blue_repeat: 1,
  bark_blue_repeat_gap_seconds: 0,
};

export const drillPresets: DrillPreset[] = [
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

export function severity(intensity = 0, levels?: Status["alert_levels"]) {
  if (intensity >= (levels?.red_intensity ?? 4)) return "red";
  if (intensity >= (levels?.yellow_intensity ?? 2)) return "yellow";
  return "blue";
}

export function cardTitle(seconds: number, city: string) {
  if (seconds > 0) return "地震横波即将到达";
  return `地震横波已到达${city || "你的位置"}`;
}

export function formatEventTime(value?: string) {
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

export function timeMs(value?: string) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
}

export function sourceName(name: string) {
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

export function sourceLabel(name: string) {
  const translated = sourceName(name);
  return translated === name ? name : `${name} · ${translated}`;
}

export function epicenterLabel(source = "", epicenter = "") {
  if (source === "jma_eew") return `日本气象厅：${epicenter}`;
  return epicenter;
}

export function pushPhaseText(phase?: string) {
  if (phase === "arrival") return "到达";
  if (phase === "test") return "测试";
  return "发现";
}

export function barkLevelText(value: string) {
  return barkLevelOptions.find(([level]) => level === value)?.[1] ?? value;
}

export function repeatText(value: number) {
  return `${Math.max(1, Number(value) || 1)} 次`;
}

export function decisionReasonLabel(reason?: string) {
  const labels: Record<string, string> = {
    "test drill": "演练模式",
    "global major earthquake": "全球特大地震",
    "global local threshold matched": "全球源地震达到本地条件",
    "threshold matched": "达到设备阈值",
    "felt intensity": "预计可能有感",
    "below threshold": "未达到阈值",
    "jma forecast only": "日本气象厅预告",
    "cancel report": "取消报",
    "device disabled": "设备已停用",
    "device disabled test alerts": "设备不接收测试",
  };
  return labels[reason || ""] ?? reason ?? "达到提醒条件";
}

export function alertReasonText(event: LatestAlert["event"], decision: NonNullable<LatestAlert["decisions"]>[number], device?: Device, globalMin = 7.0) {
  const deviceName = device?.name || decision.device_name || "这台 Apple 设备";
  const city = device?.default_city ? `，位置为${device.default_city}` : "";
  const metrics = `距震中约 ${Math.round(decision.distance_km)}km，预计烈度 ${decision.intensity.toFixed(1)}，震级 M${event?.magnitude.toFixed(1) ?? "未知"}`;
  if (event?.test) return `因为这是演练，系统会按演练场景给 ${deviceName} 发送提醒。`;
  if (decision.reason === "global major earthquake") {
    return `因为这场地震达到全球特大地震阈值 M${globalMin}+。它会作为温和提醒发送，不按本地横波倒计时理解。`;
  }
  if (decision.reason === "felt intensity") {
    return `因为 ${metrics}，系统判断可能有感，所以提醒 ${deviceName}${city}。`;
  }
  const threshold = device
    ? `；这台设备的条件是 M${device.min_magnitude}+、${device.max_distance_km}km 内、烈度 ${device.min_intensity}+`
    : "";
  return `因为 ${metrics}${threshold}，所以触发 ${deviceName}${city} 的预警。`;
}

export function canonicalLogEventId(eventId: string) {
  return eventId.replace(/^(\d{12}\.\d+)_\d+$/, "$1");
}

export function parseBarkKey(value: string) {
  const trimmed = value.trim();
  try {
    const url = new URL(trimmed);
    const key = url.pathname.split("/").filter(Boolean)[0];
    return key || trimmed;
  } catch {
    return trimmed.replace(/^\/+/, "").split("/")[0] || trimmed;
  }
}

export function coordsFor(city: string, latitude: string, longitude: string) {
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (Number.isFinite(lat) && Number.isFinite(lng)) return { lat, lng };
  const normalized = city.replace(/市$/, "").trim();
  return cityCoords[normalized] ?? chengdu;
}
