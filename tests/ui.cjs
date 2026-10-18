const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");
const { once } = require("node:events");

async function fixture(large = false) {
  const server = spawn(process.env.PYTHON || "python", ["scripts/fixture_server.py"], {
    env: {...process.env, PYTHONPATH: ".", UI_LARGE_FIXTURE: large ? "1" : "0"},
    stdio: ["ignore", "pipe", "inherit"]
  });
  const port = await new Promise((resolve, reject) => {
    server.stdout.once("data", chunk => resolve(Number(chunk.toString().trim())));
    server.once("error", reject);
    server.once("exit", code => reject(new Error("fixture server exited " + code)));
  });
  return {server, base: "http://127.0.0.1:" + port};
}

(async () => {
  const small = await fixture();
  let browser, large;
  try {
    const bundled = require("@sparticuz/chromium").default;
    browser = await chromium.launch({
      args: bundled.args,
      executablePath: process.env.CHROMIUM_PATH || await bundled.executablePath(),
      headless: true
    });
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const loaded = text => page.getByRole("status").filter({hasText: text}).waitFor();
    await page.goto(small.base);
    await loaded("18 observations loaded");
    assert.equal(await page.getByRole("heading", {name: /waterfall/}).count(), 3);
    assert.equal(await page.locator("#tokens button").count(), 4);
    assert.equal(await page.locator("#tokens button.engine").count(), 2);
    assert.equal(await page.locator("#user button[aria-label^='session ']").count(), 1);
    assert.equal(await page.locator("#user button[aria-label^='turn ']").count(), 2);
    assert.match(await page.locator("#tokens button").first().getAttribute("aria-label"), /start 4.000 ms/);
    await page.locator("#tokens button").first().focus();
    await page.keyboard.press("Enter");
    assert.match(await page.locator("#detail").textContent(), /client.chunk/);
    await page.getByLabel("Source").selectOption("engine");
    await loaded("6 observations loaded");
    assert.equal(await page.locator("#tokens button").count(), 2);
    await page.getByLabel("Source").selectOption("");
    await loaded("18 observations loaded");
    await page.locator("#user button[aria-label^='request ']").first().click();
    await loaded("6 observations loaded");
    assert.equal(await page.getByLabel("Request", {exact: true}).inputValue(), "request-0");
    assert.equal(await page.locator("#tokens button").count(), 2);
    await page.getByLabel("Request", {exact: true}).fill("");
    await loaded("18 observations loaded");
    await page.getByLabel("Timeline zoom").fill("4");
    assert.equal(await page.locator("#tokens .track").first().evaluate(e => e.style.width), "400%");
    await page.getByLabel("Session", {exact: true}).fill("<img src=x onerror=alert(1)>");
    await loaded("0 observations loaded");
    assert.match(await page.locator("#tokens").textContent(), /No observations/);
    assert.equal(await page.locator("img").count(), 0);
    await page.getByLabel("Session", {exact: true}).fill("");
    await loaded("18 observations loaded");
    if (process.env.UI_SCREENSHOT) await page.screenshot({path: process.env.UI_SCREENSHOT, fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    // Older history must not hide the newest session; filters query all stored data.
    large = await fixture(true);
    await page.goto(large.base);
    await loaded("1000 observations loaded");
    assert.equal(await page.locator("#user button[aria-label^='session ']").count(), 1);
    assert.match(await page.getByRole("status").textContent(), /10023 matching/);
    const before = await page.locator("#tokens button").first().getAttribute("aria-label");
    await page.getByRole("button", {name: "Older page", exact: true}).click();
    await loaded("page 2");
    assert.notEqual(await page.locator("#tokens button").first().getAttribute("aria-label"), before);
    await page.getByRole("button", {name: "Newer page", exact: true}).click();
    await loaded("page 1");
    await page.getByLabel("Session", {exact: true}).fill("historical-session");
    await loaded("10005 matching");
    assert.equal(await page.locator("#user button").count(), 0);
    await page.getByLabel("Session", {exact: true}).fill("session-demo");
    await loaded("18 observations loaded");
    assert.equal(await page.locator("#tokens button").count(), 4);
    await page.getByRole("button", {name: "Latest observations", exact: true}).click();
    await loaded("18 observations loaded");
    assert.deepEqual(errors, []);
    console.log("UI: lifecycle, three waterfalls, server filters, >10000 events, pagination, drilldown, keyboard, zoom, mobile passed");
  } finally {
    if (browser) await browser.close();
    for (const item of [small, large].filter(Boolean)) {
      item.server.kill();
      if (item.server.exitCode === null) await once(item.server, "exit");
    }
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
