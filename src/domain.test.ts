import { describe, expect, it } from "vitest";

import { coordsFor, uniqueEvents } from "./domain";

describe("coordsFor", () => {
  it("uses a known city when both coordinate fields are blank", () => {
    expect(coordsFor("成都", "", "")).toEqual({ lat: 30.5728, lng: 104.0668 });
  });

  it("never treats blank coordinate fields as zero", () => {
    expect(() => coordsFor("未知城市", "", "")).toThrow("无法识别");
  });

  it("requires a complete valid coordinate pair", () => {
    expect(() => coordsFor("成都", "30.5", "")).toThrow("同时填写");
    expect(() => coordsFor("成都", "91", "104")).toThrow("格式不正确");
  });

  it("keeps valid coordinates on the equator and prime meridian", () => {
    expect(coordsFor("", "0", "0")).toEqual({ lat: 0, lng: 0 });
  });
});

describe("uniqueEvents", () => {
  it("keeps the newest item for each canonical event id", () => {
    const items = [
      { event_id: "202609270101.1_2", value: "new" },
      { event_id: "202609270101.1_1", value: "old" },
      { event_id: "other", value: "other" },
    ];
    expect(uniqueEvents(items).map((item) => item.value)).toEqual(["new", "other"]);
  });
});
