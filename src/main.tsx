import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { AuthError, api } from "./api";
import { AlertCard } from "./components/AlertCard";
import { EarthquakeMap } from "./components/EarthquakeMap";
import {
  alertReasonText,
  barkLevelOptions,
  barkLevelText,
  canonicalLogEventId,
  chengdu,
  coordsFor,
  decisionReasonLabel,
  defaultGlobalCatalogMagnitude,
  defaultSystemConfig,
  drillPresets,
  epicenterLabel,
  fallbackEpicenter,
  formatEventTime,
  parseBarkKey,
  pushPhaseText,
  repeatText,
  repoUrl,
  severity,
  sourceLabel,
  sourceName,
  sourceOptions,
  timeMs,
  uniqueEvents,
} from "./domain";
import type { Device, LatestAlert, Logs, PushEventGroup, Status, SystemConfig } from "./types";

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
  const [authRequired, setAuthRequired] = useState(false);
  const [authInput, setAuthInput] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [selectedDrill, setSelectedDrill] = useState(drillPresets[0].id);
  const [alertStartedAt, setAlertStartedAt] = useState(Date.now());
  const [nowMs, setNowMs] = useState(Date.now());
  const [hideTestHistory, setHideTestHistory] = useState(false);
  const [showAllReceived, setShowAllReceived] = useState(false);
  const [detailNotFound, setDetailNotFound] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const [cardImageUrl, setCardImageUrl] = useState("");
  const [cardImageName, setCardImageName] = useState("");
  const [cardImageBlob, setCardImageBlob] = useState<Blob | null>(null);
  const configDirtyRef = useRef(false);
  const alertCardRef = useRef<HTMLElement | null>(null);
  const [systemConfig, setSystemConfig] = useState<SystemConfig>(defaultSystemConfig);
  const [form, setForm] = useState({
    name: "",
    push_type: "bark",
    bark_key: "",
    push_url: "",
    default_city: "成都",
    latitude: "",
    longitude: "",
    min_magnitude: "4.5",
    max_distance_km: "500",
    min_intensity: "2",
    enabled: true,
    receive_tests: true,
  });

  async function refresh() {
    const logParams = new URLSearchParams();
    if (routePath === "/history") {
      logParams.set("events_limit", "2000");
      logParams.set("decisions_limit", "5000");
    } else if (routePath === "/catalog") {
      logParams.set("observed_limit", "2000");
    } else if (routePath === "/pushes") {
      logParams.set("pushes_limit", "2000");
    }
    const logsPath = logParams.size ? `/api/logs?${logParams}` : "/api/logs";
    const nextAlert = detailEventId
      ? api<LatestAlert>(`/api/alerts/${encodeURIComponent(detailEventId)}`)
          .then((value) => {
            setDetailNotFound(false);
            return value;
          })
          .catch((error) => {
            if (error instanceof AuthError) throw error;
            setDetailNotFound(true);
            return {};
          })
      : api<LatestAlert>("/api/latest-alert");
    const [nextStatus, nextDevices, nextLatest, nextLogs, nextConfig] = await Promise.all([
      api<Status>("/api/status"),
      api<Device[]>("/api/devices"),
      nextAlert,
      api<Logs>(logsPath),
      api<SystemConfig>("/api/system-config"),
    ]);
    setStatus(nextStatus);
    setDevices(nextDevices);
    setLatest(nextLatest);
    setLogs(nextLogs);
    setAuthRequired(false);
    if (!configDirtyRef.current) setSystemConfig({ ...defaultSystemConfig, ...nextConfig });
  }

  useEffect(() => {
    refresh().catch((error) => {
      if (error instanceof AuthError) {
        setAuthRequired(true);
        setMessage("");
      } else {
        setMessage(error.message);
      }
    });
    const bulkLogPage = ["/history", "/catalog", "/pushes"].includes(routePath);
    const id = window.setInterval(() => refresh().catch((error) => {
      if (error instanceof AuthError) setAuthRequired(true);
    }), bulkLogPage ? 30000 : 5000);
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
      push_type: device.push_type || "bark",
      bark_key: "",
      push_url: "",
      default_city: device.default_city || "成都",
      latitude: String(device.latitude || ""),
      longitude: String(device.longitude || ""),
      min_magnitude: String(device.min_magnitude),
      max_distance_km: String(device.max_distance_km),
      min_intensity: String(device.min_intensity),
      enabled: device.enabled,
      receive_tests: device.receive_tests,
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
  const detailDecisionMissing = Boolean(detailEventId && latest.event && !selectedDecision);
  useEffect(() => {
    setAlertStartedAt(Date.now());
  }, [event.event_id, event.epicenter, event.magnitude]);
  const countdownBaseMs = timeMs(decision.created_at) ?? alertStartedAt;
  const elapsedSeconds = Math.max(0, Math.floor((nowMs - countdownBaseMs) / 1000));
  const liveArrivalSeconds = Math.max(-90, decision.arrival_seconds - elapsedSeconds);
  const activeDevice = detailDeviceId
    ? devices.find((item) => item.id === detailDeviceId)
    : devices.find((item) => item.name === decision.device_name) ?? devices[0];
  const snapshotLocation = decision.device_latitude !== undefined && decision.device_longitude !== undefined
    ? { lat: decision.device_latitude, lng: decision.device_longitude }
    : null;
  const user = snapshotLocation ?? (activeDevice ? { lat: activeDevice.latitude, lng: activeDevice.longitude } : chengdu);
  const epicenter: [number, number] = [event.latitude || fallbackEpicenter.lat, event.longitude || fallbackEpicenter.lng];
  const userPoint: [number, number] = [user.lat || chengdu.lat, user.lng || chengdu.lng];
  const waveKm = Math.max(20, Math.min(20000,
    liveArrivalSeconds > 0
      ? decision.distance_km - liveArrivalSeconds * 3.5
      : decision.distance_km + Math.abs(liveArrivalSeconds) * 3.5,
  ));
  const globalMinMagnitude = status?.global_quake_min_magnitude ?? 7.0;
  const isFarGlobalBrief = decision.distance_km > 1000 && event.magnitude >= globalMinMagnitude;
  const level = isFarGlobalBrief
    ? event.magnitude >= 8 ? "red" : event.magnitude >= 7.5 ? "yellow" : "blue"
    : severity(decision.intensity, status?.alert_levels);
  const sourceStates = Object.entries(status?.listener.sources ?? {});
  const connectedSources = sourceStates.filter(([, state]) => state.connected).length;
  const visiblePushes = logs.pushes.filter((item) => !hideTestHistory || !item.test);
  const visibleEvents = logs.events.filter((item) => !hideTestHistory || !item.test);
  const visibleObservedEvents = uniqueEvents(logs.observed_events);
  const observedTotal = logs.counts?.observed_events ?? visibleObservedEvents.length;
  const observedLimit = status?.retention?.max_events;
  const observedLimitText = observedLimit
    ? `保留 ${observedTotal}/${observedLimit}`
    : `保留 ${observedTotal}`;
  const catalogVisibleEvents = showAllReceived
    ? visibleObservedEvents
    : visibleObservedEvents.filter((item) =>
      item.source !== "emsc_global" || Boolean(item.recorded) || item.magnitude >= defaultGlobalCatalogMagnitude
    );
  const dedupedVisibleEvents = uniqueEvents(visibleEvents);
  const decisionByEvent = logs.decisions.reduce((result, item) => {
    const current = result.get(item.event_id);
    if (!current || (!current.should_push && item.should_push)) result.set(item.event_id, item);
    return result;
  }, new Map<string, Logs["decisions"][number]>());
  const alertVisibleEvents = dedupedVisibleEvents.filter((item) =>
    Boolean((decisionByEvent.get(item.event_id) ?? decisionByEvent.get(canonicalLogEventId(item.event_id)))?.should_push)
  );
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
  const displayCity = decision.device_city || activeDevice?.default_city || "你的位置";
  const eventEpicenterLabel = epicenterLabel(event.source, event.epicenter);
  const alertExplanation = alertReasonText(event, decision, activeDevice, globalMinMagnitude);
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
    let location;
    try {
      location = coordsFor(form.default_city, form.latitude, form.longitude);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "位置格式不正确。");
      return;
    }
    const key = parseBarkKey(form.bark_key);
    const pushType = form.push_type as "bark" | "ntfy" | "webhook";
    const payload: Record<string, unknown> = {
      name: form.name.trim() || "你的 Apple 设备",
      push_type: pushType,
      default_city: form.default_city || "成都",
      latitude: location.lat,
      longitude: location.lng,
      min_magnitude: Number(form.min_magnitude),
      max_distance_km: Number(form.max_distance_km),
      min_intensity: Number(form.min_intensity),
      enabled: form.enabled,
      receive_tests: form.receive_tests,
    };
    if (pushType === "bark") {
      payload.push_url = "";
      if (key || !editingId) payload.bark_key = key;
    } else {
      payload.bark_key = "";
      if (form.push_url.trim() || !editingId) payload.push_url = form.push_url.trim();
    }

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

  useEffect(() => {
    return () => {
      if (cardImageUrl) URL.revokeObjectURL(cardImageUrl);
    };
  }, [cardImageUrl]);

  async function renderAlertCardBlob() {
    if (!alertCardRef.current) return;
    const hidden = Array.from(alertCardRef.current.querySelectorAll<HTMLElement>(".captureExclude"));
    try {
      hidden.forEach((node) => { node.style.visibility = "hidden"; });
      const { default: html2canvas } = await import("html2canvas");
      const canvas = await html2canvas(alertCardRef.current, {
        backgroundColor: null,
        scale: Math.min(window.devicePixelRatio || 2, 3),
        useCORS: true,
      });
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("图片生成失败");
      return blob;
    } finally {
      hidden.forEach((node) => { node.style.visibility = ""; });
    }
  }

  async function saveAlertCardImage() {
    try {
      const blob = await renderAlertCardBlob();
      if (!blob) return;
      const filename = `earthquake-alert-${event.event_id || Date.now()}.png`;
      const url = URL.createObjectURL(blob);
      setCardImageUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return url;
      });
      setCardImageName(filename);
      setCardImageBlob(blob);
      const link = document.createElement("a");
      link.download = filename;
      link.href = url;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setMessage("预警卡片已生成。若浏览器没有自动下载，可在预览里打开原图或长按保存。");
    } catch (error) {
      setMessage(`保存图片失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  async function shareAlertCardImage() {
    if (!cardImageBlob) return;
    const filename = cardImageName || `earthquake-alert-${Date.now()}.png`;
    const file = new File([cardImageBlob], filename, { type: "image/png" });
    const shareData = { files: [file], title: "地震预警卡片", text: `${event.epicenter} M${event.magnitude.toFixed(1)}` };
    if (!navigator.canShare?.(shareData)) {
      setMessage("当前浏览器不支持直接分享图片，可打开原图后保存。");
      return;
    }
    await navigator.share(shareData);
  }

  async function testPush(deviceId?: number) {
    const target = devices.find((device) => device.id === deviceId) ?? devices.find((device) => device.id === editingId) ?? devices[0];
    if (!target) {
      setMessage("先添加一台 Apple 设备。");
      return;
    }
    const result = await api<{ ok: boolean; latency_ms: number; message: string }>("/api/test-push", {
      method: "POST",
      body: JSON.stringify({ device_id: target.id }),
    });
    setMessage(result.ok ? `已向 ${target.name} 发出测试通知，用时 ${result.latency_ms} ms。` : `推送失败：${result.message}`);
  }

  async function toggleDevice(device: Device) {
    await api(`/api/devices/${device.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !device.enabled }) });
    setMessage(`${device.name} 已${device.enabled ? "停用" : "启用"}。`);
    await refresh();
  }

  async function deleteDevice(device: Device) {
    if (!window.confirm(`确定删除 ${device.name} 吗？历史记录会保留。`)) return;
    await api(`/api/devices/${device.id}`, { method: "DELETE" });
    if (editingId === device.id) setEditingId(null);
    setMessage(`${device.name} 已删除。`);
    await refresh();
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
    if (!window.confirm("确定清除发出的通知吗？触发的预警会保留。")) return;
    await api<{ ok: boolean }>("/api/logs/pushes", { method: "DELETE" });
    setMessage("发出的通知已清除。");
    await refresh();
  }

  async function clearEventHistory() {
    if (!window.confirm("确定清除触发的预警吗？相关判断和通知发送结果也会一起清除。")) return;
    await api<{ ok: boolean }>("/api/logs/events", { method: "DELETE" });
    setMessage("触发的预警已清除。");
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
        source_health_alert_after_minutes: Number(systemConfig.source_health_alert_after_minutes),
        alert_red_intensity: Number(systemConfig.alert_red_intensity),
        alert_yellow_intensity: Number(systemConfig.alert_yellow_intensity),
      }),
    });
    setSystemConfig({ ...defaultSystemConfig, ...saved });
    configDirtyRef.current = false;
    setConfigDirty(false);
    setMessage("系统配置已保存；只有监听源发生变化时才会重连。");
    await refresh();
  }

  async function submitAuth(event: React.FormEvent) {
    event.preventDefault();
    localStorage.setItem("eewAuthToken", authInput.trim());
    try {
      await refresh();
      setMessage("已通过访问口令。");
    } catch (error) {
      if (error instanceof AuthError) {
        localStorage.removeItem("eewAuthToken");
        setAuthRequired(true);
        setMessage("访问口令不正确。");
      } else {
        setMessage(error instanceof Error ? error.message : "验证失败");
      }
    }
  }

  if (authRequired) {
    return (
      <main className="authShell">
        <form className="authPanel" onSubmit={submitAuth}>
          <span className="eyebrow">Apple EEW Hub</span>
          <h1>输入访问口令</h1>
          <p>此实例启用了内置 API 口令。公网访问仍建议放在 Cloudflare Access 或反向代理认证后面。</p>
          <label>
            访问口令
            <input
              type="password"
              value={authInput}
              onChange={(event) => setAuthInput(event.target.value)}
              autoFocus
              placeholder="EEW_AUTH_TOKEN"
            />
          </label>
          <button type="submit">进入系统</button>
          {message && <p className="message">{message}</p>}
        </form>
      </main>
    );
  }

  const alertCard = <AlertCard ref={alertCardRef} event={event} decision={decision} level={level} displayCity={displayCity} liveArrivalSeconds={liveArrivalSeconds} epicenter={eventEpicenterLabel} farGlobal={isFarGlobalBrief} explanation={detailEventId ? alertExplanation : undefined} />;

  const mapSection = <EarthquakeMap epicenter={epicenter} user={userPoint} waveKm={waveKm} level={level} epicenterLabel={eventEpicenterLabel} userLabel={displayCity} />;

  const renderPushHistorySection = (limit?: number) => (
    <section className="panel historyPanel">
      <div className="sectionHead">
        <div>
          <h2>发出的通知</h2>
        </div>
        <div className="historyActions">
          <label className="toggle"><input type="checkbox" checked={hideTestHistory} onChange={(event) => setHideTestHistory(event.target.checked)} />隐藏测试</label>
          <span>{groupedPushEvents.length} 条</span>
          <button className="dangerButton" onClick={clearPushHistory}>清除通知</button>
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
          <h2>触发的预警</h2>
        </div>
        <div className="historyActions">
          <label className="toggle"><input type="checkbox" checked={hideTestHistory} onChange={(event) => setHideTestHistory(event.target.checked)} />隐藏测试</label>
          <span>{alertVisibleEvents.length} 条</span>
          <button className="dangerButton" onClick={clearEventHistory}>清除预警</button>
        </div>
      </div>
      <div className="eventLogList">
        {alertVisibleEvents.slice(0, limit ?? alertVisibleEvents.length).map((item) => {
          const canonicalId = canonicalLogEventId(item.event_id);
          const itemDecision = decisionByEvent.get(item.event_id) ?? decisionByEvent.get(canonicalId);
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
              <em className="pushed">已触发</em>
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
          <h2>收到的地震</h2>
        </div>
        <div className="historyActions">
          <button className="compact" onClick={() => setShowAllReceived((value) => !value)}>
            {showAllReceived ? "隐藏全球小震" : "显示全部"}
          </button>
          <span>{catalogVisibleEvents.length}/{visibleObservedEvents.length} 条</span>
          <span className={observedLimit && observedTotal >= observedLimit ? "limitReached" : ""}>{observedLimitText}</span>
        </div>
      </div>
      <div className="eventLogList">
        {catalogVisibleEvents.slice(0, limit ?? catalogVisibleEvents.length).map((item) => {
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
              <small>{item.source === "emsc_global" && item.magnitude < defaultGlobalCatalogMagnitude && !inWarningHistory ? "全球小震" : `深度 ${item.depth_km} km`}</small>
              <em className={inWarningHistory ? "pushed" : "notPushed"}>{item.reason || (inWarningHistory ? "已触发预警" : "未触发预警")}</em>
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
        <a href="/rules">
          <span>怎么看记录</span>
          <b>收到 / 触发 / 发出</b>
        </a>
        <a href="/settings">
          <span>推送设置</span>
          <b>红 / 黄 / 蓝</b>
        </a>
      </div>
    </section>
  );

  const homeFlow = (
    <section className="panel flowPanel homeFlowPanel">
      <a href="/catalog">
        <b>1</b>
        <span>收到的地震</span>
        <small>{catalogVisibleEvents.length}/{visibleObservedEvents.length} 条 · {observedLimitText}</small>
      </a>
      <a href="/history">
        <b>2</b>
        <span>触发的预警</span>
        <small>{logs.counts?.triggered_events ?? alertVisibleEvents.length} 场，符合设备位置和阈值</small>
      </a>
      <a href="/pushes">
        <b>3</b>
        <span>发出的通知</span>
        <small>{logs.counts?.notified_events ?? groupedPushEvents.length} 场，Bark / ntfy / Webhook 结果</small>
      </a>
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
      {historyPageHeader("怎么看记录", "一场地震会先被系统收到，只有符合你设备条件时才会触发预警；触发后如果设备配置了 Bark、ntfy 或 Webhook，才会产生通知发送结果。")}
      <section className="panel flowPanel">
        <div><b>1</b><span>收到的地震</span><small>实时源传来的事件</small></div>
        <div><b>2</b><span>触发的预警</span><small>符合设备位置和阈值</small></div>
        <div><b>3</b><span>发出的通知</span><small>Bark / ntfy / Webhook 结果</small></div>
      </section>
      <section className="panel rulesPanel">
        <div className="rulesGrid">
          <div>
            <h2>收到的地震</h2>
            <ul>
              <li>只表示系统从实时源听到了这场地震。</li>
              <li>这里可能包含很小、很远、不会提醒你的地震。</li>
              <li>它是原始入口，不等于预警。</li>
            </ul>
          </div>
          <div>
            <h2>触发的预警</h2>
            <ul>
              <li>只有需要提醒你的地震才会出现在这里。</li>
              <li>本地相关地震按每台设备的位置、震级和距离判断；烈度决定提醒强度。</li>
              <li>全球 M{status?.global_quake_min_magnitude ?? 7.0}+ 会进入这里；离你很远时只做温和提醒。</li>
            </ul>
          </div>
          <div>
            <h2>发出的通知</h2>
            <ul>
              <li>这里按一场地震合并显示通知发送结果。</li>
              <li>同一场地震可能包含发现通知和到达通知。</li>
              <li>如果没有配置推送设备，可能有预警但没有通知结果。</li>
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
          <p>黄色：烈度 ≥ {systemConfig.alert_yellow_intensity}。发现时发送 {repeatText(systemConfig.bark_yellow_repeat)} {barkLevelText(systemConfig.bark_yellow_level)}，音量 {systemConfig.bark_yellow_volume || "默认"}，铃声 {systemConfig.bark_yellow_sound}，但不持续响；如果横波尚未到达，到达时再发一次。</p>
          <p>蓝色：低于黄色但仍需要提醒时使用。发现时发送 {repeatText(systemConfig.bark_blue_repeat)} {barkLevelText(systemConfig.bark_blue_level)}，音量 {systemConfig.bark_blue_volume || "默认"}，铃声 {systemConfig.bark_blue_sound || "系统默认"}；如果横波尚未到达，到达时再发一次。</p>
          <p>说明：Bark 的最高级强提醒用于尽量突破静音/专注模式；持续响只给红色本地预警使用。远场全球大震统一静默提醒。</p>
          <p className="safetyNote">本系统使用第三方实时源和估算模型，只作为辅助提醒，不能替代当地官方地震预警与应急信息。</p>
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
              <label className="checkLine">
                <input type="checkbox" checked={systemConfig.source_health_alert_enabled} onChange={(event) => updateSystemConfig({ source_health_alert_enabled: event.target.checked })} />
                源持续离线 1 小时后通知
              </label>
            </div>
          </div>
          <div className="settingFull">
            <h3>全球特大地震</h3>
            <div className="settingPair">
              <label className="checkLine">
                <input type="checkbox" checked={systemConfig.global_enabled} onChange={(event) => updateSystemConfig({ global_enabled: event.target.checked })} />
                EMSC 全球 WebSocket
              </label>
              <label className="checkLine">
                <input type="checkbox" checked={systemConfig.global_far_alert_enabled} onChange={(event) => updateSystemConfig({ global_far_alert_enabled: event.target.checked })} />
                全球远场通知
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
          <p>这条通知对应的预警已经找不到。可以返回首页。</p>
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

  if (detailDecisionMissing) {
    return (
      <main className="appShell detailShell">
        <section className="panel loadingPanel">
          <h1>设备判断记录不可用</h1>
          <p>地震事件仍然存在，但这条通知对应的设备判断已经被清除。</p>
          <a className="alertBack" href="/">返回首页</a>
        </section>
      </main>
    );
  }

  if (detailEventId) {
    return (
      <main className="appShell detailShell">
        <div className="detailToolbar captureExclude">
          <a className="alertBack" href="/">返回首页</a>
          <button className="alertAction" onClick={saveAlertCardImage}>保存图片</button>
        </div>
        <section className="detailLayout">
          {alertCard}
          {mapSection}
        </section>
        {message && <p className="message">{message}</p>}
        {cardImageUrl && (
          <section className="imageSheet">
            <div>
              <h2>预警卡片图片已生成</h2>
              <p>如果没有自动下载，打开原图或长按下面的图片保存。</p>
            </div>
            <img src={cardImageUrl} alt="地震预警卡片图片" />
            <div className="buttonRow">
              <a className="secondaryLink" href={cardImageUrl} download={cardImageName}>下载图片</a>
              <a className="secondaryLink" href={cardImageUrl} target="_blank" rel="noreferrer">打开原图</a>
              <button className="secondary" onClick={shareAlertCardImage}>分享</button>
              <button className="ghost" onClick={() => setCardImageUrl("")}>关闭</button>
            </div>
          </section>
        )}
      </main>
    );
  }

  if (isEventHistoryPage) {
    return (
      <main className="appShell">
        {historyPageHeader(
          "触发的预警",
          `这里显示真正需要提醒你的地震，包括演练、本地相关地震和全球 M${status?.global_quake_min_magnitude ?? 7.0}+。未触发的小震、远震只在“收到的地震”里。`,
        )}
        {renderEventLogSection()}
      </main>
    );
  }

  if (isCatalogPage) {
    return (
      <main className="appShell">
        {historyPageHeader(
          "收到的地震",
          `系统从已连接实时源听到的事件会先出现在这里。默认隐藏 EMSC 全球 M${defaultGlobalCatalogMagnitude} 以下且未触发预警的小震。`,
        )}
        {renderCatalogSection()}
      </main>
    );
  }

  if (isPushHistoryPage) {
    return (
      <main className="appShell">
        {historyPageHeader(
          "发出的通知",
          "Bark、ntfy 或 Webhook 的发送结果在这里查看。同一场地震会合并成一条。",
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
          <p className="heroText">自建地震预警中枢，默认可配套自己的 Bark Server，也支持 ntfy 和 Webhook。可为每台 Apple 设备单独设置位置和推送条件。</p>
          <a className="repoLink" href={repoUrl} target="_blank" rel="noreferrer">开源项目 GitHub</a>
          <small className="heroDisclaimer">第三方辅助预警，不能替代当地官方预警与应急信息。</small>
        </div>
      </section>

      <section className="quick panel">
        <h2>快速开始</h2>
        <ol>
          <li><b>1. 保存设备</b><span>填 Bark Key、ntfy Topic 或 Webhook。</span></li>
          <li><b>2. 测试通知</b><span>确认 Apple 设备能响。</span></li>
          <li><b>3. 演练一次</b><span>检查推送、卡片和地图。</span></li>
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
            <label>推送方式<select value={form.push_type} onChange={(e) => setForm({ ...form, push_type: e.target.value })}>
              <option value="bark">Bark</option>
              <option value="ntfy">ntfy</option>
              <option value="webhook">Webhook</option>
            </select></label>
          </div>
          <div className="two">
            {form.push_type === "bark" ? (
              <label>Bark Key 或从 Bark App 复制的推送地址<input value={form.bark_key} onChange={(e) => setForm({ ...form, bark_key: e.target.value })} placeholder="https://bark.example.com/你的Key/推送内容" /></label>
            ) : (
              <label>{form.push_type === "ntfy" ? "ntfy Topic 地址" : "Webhook 地址"}<input value={form.push_url} onChange={(e) => setForm({ ...form, push_url: e.target.value })} placeholder={form.push_type === "ntfy" ? "https://ntfy.sh/你的随机topic" : "https://example.com/eew-webhook"} /></label>
            )}
            <div className="fieldHelp">
              {form.push_type === "ntfy" ? "ntfy 会用 POST 发送正文，并带 Title、Priority、Tags 头。" : form.push_type === "webhook" ? "Webhook 会收到 JSON：title、body、event、decision。" : "Bark 推荐使用自建 Bark Server，iPhone 提醒效果最好。"}
            </div>
          </div>
          <div className="three locationRow">
            <label>城市<input value={form.default_city} onChange={(e) => setForm({ ...form, default_city: e.target.value })} placeholder="成都" /></label>
            <label>纬度，可选<input value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} placeholder="留空则按城市估算" /></label>
            <label>经度，可选<input value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} placeholder="留空则按城市估算" /></label>
          </div>
          <div className="buttonRow">
            <button type="button" className="ghost" onClick={locate}>获取位置</button>
            <button>{editingId ? "保存修改" : "保存设备"}</button>
            <button type="button" className="secondary" onClick={() => testPush()}>测试通知</button>
          </div>
          <details>
            <summary>每台设备独立推送阈值</summary>
            <div className="three">
              <label>最低震级<input value={form.min_magnitude} onChange={(e) => setForm({ ...form, min_magnitude: e.target.value })} /></label>
              <label>最大距离 km<input value={form.max_distance_km} onChange={(e) => setForm({ ...form, max_distance_km: e.target.value })} /></label>
              <label>最低烈度<input value={form.min_intensity} onChange={(e) => setForm({ ...form, min_intensity: e.target.value })} /></label>
            </div>
            <div className="deviceToggles">
              <label className="checkLine"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />启用这台设备</label>
              <label className="checkLine"><input type="checkbox" checked={form.receive_tests} onChange={(e) => setForm({ ...form, receive_tests: e.target.checked })} />接收演练通知</label>
            </div>
          </details>
        </form>
        {devices.length > 0 && (
          <div className="deviceList">
            {devices.map((device) => (
              <div key={device.id} className={`deviceItem ${device.enabled ? "" : "disabled"}`}>
                <div><span>{device.name}</span><small>{device.push_type || "bark"} · 城市：{device.default_city || "未设置"} · 推送条件：震级 ≥ {device.min_magnitude}，距离 ≤ {device.max_distance_km} km，烈度 ≥ {device.min_intensity}</small></div>
                <div className="deviceActions">
                  <button type="button" className="compact" onClick={() => testPush(device.id)}>测试</button>
                  <button type="button" className="compact" onClick={() => editDevice(device)}>编辑</button>
                  <button type="button" className="ghost compact" onClick={() => toggleDevice(device)}>{device.enabled ? "停用" : "启用"}</button>
                  <button type="button" className="dangerButton" onClick={() => deleteDevice(device)}>删除</button>
                </div>
              </div>
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

      <section className="monitorBlock">
        <div className="statusCard">
          <div className="statusMain">
            <span className={status?.listener.connected ? "dot on" : status?.listener.degraded ? "dot pending" : "dot"} />
            <strong>{status?.listener.connected ? "实时监听中" : status?.listener.degraded ? `部分源离线（${status.listener.connected_count}/${status.listener.source_count}）` : "监听未就绪"}</strong>
            <small>{connectedSources}/{sourceStates.length || status?.sources.length || 3} 个源在线</small>
          </div>
          <div className="sources compactSources">
            {sourceStates.length ? sourceStates.map(([name, state]) => (
              <div key={name} className={state.connected ? "sourceOnline" : state.message === "connecting" ? "sourcePending" : "sourceOffline"}><span>{sourceLabel(name)}</span><strong>{state.connected ? "已连接" : state.message === "connecting" ? "连接中" : "离线"}</strong></div>
            )) : <div><span>Wolfx</span><strong>等待中</strong></div>}
          </div>
        </div>
        {homeFlow}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
