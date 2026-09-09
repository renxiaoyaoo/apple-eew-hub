import { forwardRef } from "react";
import { cardTitle, formatEventTime, repoUrl, sourceName } from "../domain";
import type { LatestAlert } from "../types";

type Event = NonNullable<LatestAlert["event"]>;
type Decision = NonNullable<LatestAlert["decisions"]>[number];

type Props = {
  event: Event;
  decision: Decision;
  level: string;
  displayCity: string;
  liveArrivalSeconds: number;
  epicenter: string;
  farGlobal: boolean;
  explanation?: string;
};

export const AlertCard = forwardRef<HTMLElement, Props>(function AlertCard(
  { event, decision, level, displayCity, liveArrivalSeconds, epicenter, farGlobal, explanation },
  ref,
) {
  return (
    <section ref={ref} className={`alertCard ${level}`}>
      <div className="alertPattern alertPatternGrid" aria-hidden="true">
        {Array.from({ length: 22 }, (_, index) => <span key={index} style={{ left: `${index * 42 - 180}px` }} />)}
      </div>
      <div className="alertPattern alertPatternTape" aria-hidden="true">
        {Array.from({ length: 14 }, (_, index) => <span key={index} />)}
      </div>
      <div className="alertHead"><span>{event.test ? "演练/示例" : "实时预警"}</span></div>
      <h2>{farGlobal ? "全球特大地震预警" : cardTitle(liveArrivalSeconds, displayCity)}</h2>
      <strong>{farGlobal ? `M${event.magnitude.toFixed(1)}` : liveArrivalSeconds > 0 ? `${liveArrivalSeconds} 秒` : "已到达"}</strong>
      <div className="bigMetrics">
        <div><span>距离</span><b>{Math.round(decision.distance_km)} km</b></div>
        <div><span>震级</span><b>M{event.magnitude.toFixed(1)}</b></div>
        <div><span>烈度</span><b>{decision.intensity}</b></div>
        <div><span>震感</span><b>{decision.intensity_text}</b></div>
        <div><span>震中</span><b>{epicenter}</b></div>
        <div><span>深度</span><b>{event.depth_km} km</b></div>
        <div><span>地震时间</span><b>{formatEventTime(event.origin_time)}</b></div>
        <div><span>预警来源</span><b>{sourceName(event.source || "unknown")}</b></div>
      </div>
      {explanation && <div className="reasonBox"><b>为什么提醒我</b><span>{explanation}</span></div>}
      <div className="alertCredit">
        <strong>Apple EEW Hub</strong>
        <a href={repoUrl} target="_blank" rel="noreferrer">{repoUrl}</a>
      </div>
    </section>
  );
});
