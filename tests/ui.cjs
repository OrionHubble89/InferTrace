const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const assert = require("node:assert/strict");

(async () => {
  const server = spawn(process.env.PYTHON || "python", ["scripts/fixture_server.py"], {
    env: {...process.env, PYTHONPATH: "."}, stdio: ["ignore", "pipe", "inherit"]
  });
  let browser;
  try {
    const port = await new Promise((resolve, reject) => {
      server.stdout.once("data", chunk => resolve(Number(chunk.toString().trim())));
      server.once("error", reject);
      server.once("exit", code => reject(new Error("fixture server exited " + code)));
    });
    const bundled = require("@sparticuz/chromium").default;
    browser = await chromium.launch({
      args: bundled.args,
      executablePath: await bundled.executablePath(),
      headless: true,
      ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})
    });
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://127.0.0.1:" + port);
    await page.getByRole("status").filter({hasText: "12 observations loaded"}).waitFor();
    assert.equal(await page.getByRole("heading", {name: /waterfall/}).count(), 3);
    assert.equal(await page.locator("#tokens button").count(), 4);
    assert.equal(await page.locator("#tokens button.engine").count(), 2);
    assert.match(await page.locator("#tokens button").first().getAttribute("aria-label"), /start 4.000 ms/);
    await page.locator("#tokens button").first().focus();
    await page.keyboard.press("Enter");
    assert.match(await page.locator("#detail").textContent(), /client.chunk/);
    await page.getByLabel("Source").selectOption("engine");
    assert.equal(await page.locator("#tokens button").count(), 2);
    await page.getByLabel("Source").selectOption("");
    await page.locator("#user button").first().click();
    assert.equal(await page.getByLabel("Request", {exact: true}).inputValue(), "request-0");
    assert.equal(await page.locator("#tokens button").count(), 2);
    await page.getByLabel("Request", {exact: true}).fill("");
    await page.getByLabel("Timeline zoom").fill("4");
    assert.equal(await page.locator("#tokens .track").first().evaluate(e => e.style.width), "400%");
    await page.getByLabel("Session", {exact: true}).fill("<img src=x onerror=alert(1)>");
    assert.match(await page.locator("#tokens").textContent(), /No observations/);
    assert.equal(await page.locator("img").count(), 0);
    await page.getByLabel("Session", {exact: true}).fill("");
    if (process.env.UI_SCREENSHOT) await page.screenshot({path: process.env.UI_SCREENSHOT, fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    console.log("UI: three waterfalls, drilldown, filters, keyboard, zoom, empty state, injection and mobile passed");
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
