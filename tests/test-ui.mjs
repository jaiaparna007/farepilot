import { chromium } from 'playwright';
import path from 'node:path';

const browser = await chromium.launch({ headless: true, executablePath: '/usr/local/bin/chromium', args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on('console', msg => { if (msg.type() === 'error') errors.push(`console: ${msg.text()}`); });
page.on('pageerror', err => errors.push(`pageerror: ${err.message}`));
await page.goto('file://' + path.resolve('/data/farepilot-live/templates/index.html'));
await page.waitForTimeout(300);

const toolCount = await page.locator('#toolGrid input').count();
if (toolCount !== 8) errors.push(`expected 8 modules, found ${toolCount}`);
await page.click('#coreTools');
const coreSelected = await page.locator('#toolGrid input:checked').count();
if (coreSelected !== 3) errors.push(`core selection failed: ${coreSelected}`);
await page.locator('#toolGrid input[value="fees"]').check();
const customSelected = await page.locator('#toolGrid input:checked').count();
if (customSelected !== 4) errors.push(`custom selection failed: ${customSelected}`);
await page.click('#searchButton');
await page.waitForSelector('#results.visible', { timeout: 3000 });
const sectionCount = await page.locator('.result-section').count();
if (sectionCount !== 4) errors.push(`expected 4 result sections, found ${sectionCount}`);
const title = await page.locator('#resultTitle').innerText();
if (!title.includes('DEL') || !title.includes('DXB')) errors.push(`route title failed: ${title}`);

await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(150);
const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
if (bodyWidth > 390) errors.push(`mobile horizontal overflow: ${bodyWidth}px`);

console.log(JSON.stringify({ toolCount, coreSelected, customSelected, sectionCount, title, bodyWidth, errors }, null, 2));
await browser.close();
if (errors.length) process.exit(1);
