import assert from "node:assert/strict";
import test from "node:test";
import { lockPageScroll } from "./page-scroll-lock.js";

class FakeStyle {
  constructor(initial = {}) {
    this.properties = new Map(
      Object.entries(initial).map(([property, value]) => [property, { priority: "", value }]),
    );
  }

  getPropertyPriority(property) {
    return this.properties.get(property)?.priority || "";
  }

  getPropertyValue(property) {
    return this.properties.get(property)?.value || "";
  }

  removeProperty(property) {
    this.properties.delete(property);
  }

  setProperty(property, value, priority = "") {
    this.properties.set(property, { priority, value });
  }
}

test("page scroll locks nest and restore the exact document position and inline styles", () => {
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;
  const rootStyle = new FakeStyle({ "overflow-y": "clip", "scroll-behavior": "smooth" });
  const bodyStyle = new FakeStyle({ position: "relative", top: "3px" });
  const scrollCalls = [];

  globalThis.document = {
    body: { style: bodyStyle },
    documentElement: { style: rootStyle },
  };
  globalThis.window = {
    pageXOffset: 0,
    pageYOffset: 0,
    scrollTo(...coordinates) {
      scrollCalls.push(coordinates);
    },
    scrollX: 12,
    scrollY: 640,
  };

  try {
    const releaseFirstLock = lockPageScroll();
    const releaseSecondLock = lockPageScroll();

    assert.equal(rootStyle.getPropertyValue("overflow-x"), "hidden");
    assert.equal(rootStyle.getPropertyValue("overflow-y"), "hidden");
    assert.equal(rootStyle.getPropertyValue("overscroll-behavior"), "none");
    assert.equal(bodyStyle.getPropertyValue("position"), "fixed");
    assert.equal(bodyStyle.getPropertyValue("left"), "-12px");
    assert.equal(bodyStyle.getPropertyValue("top"), "-640px");

    releaseFirstLock();
    assert.equal(bodyStyle.getPropertyValue("position"), "fixed");
    assert.deepEqual(scrollCalls, []);

    releaseSecondLock();
    assert.equal(rootStyle.getPropertyValue("overflow-x"), "");
    assert.equal(rootStyle.getPropertyValue("overflow-y"), "clip");
    assert.equal(rootStyle.getPropertyValue("overscroll-behavior"), "");
    assert.equal(rootStyle.getPropertyValue("scroll-behavior"), "smooth");
    assert.equal(bodyStyle.getPropertyValue("position"), "relative");
    assert.equal(bodyStyle.getPropertyValue("left"), "");
    assert.equal(bodyStyle.getPropertyValue("top"), "3px");
    assert.deepEqual(scrollCalls, [[12, 640]]);

    // Each returned cleanup is idempotent, as React effect cleanups need it to be.
    releaseSecondLock();
    assert.deepEqual(scrollCalls, [[12, 640]]);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
  }
});
