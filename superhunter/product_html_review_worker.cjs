// Read only the three documents prepared in the private staging directory.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.join(process.cwd(), 'package'));

async function observe(context, name) {
  const page = await context.newPage();
  const requests = [];
  page.on('request', request => requests.push(request.resourceType()));
  try {
    await page.setContent(fs.readFileSync(name + '.html', 'utf8'), { waitUntil: 'load', timeout: 5000 });
    const heading = page.getByRole('heading', { level: 1 });
    const pre = page.locator('body > pre');
    return {
      title: await page.title(), language: await page.locator('html').getAttribute('lang'),
      heading: await heading.allTextContents(), headingVisible: await heading.count() === 1 && await heading.isVisible(),
      preCount: await pre.count(), preVisible: await pre.isVisible(), text: await pre.innerText(),
      bodyChildren: await page.locator('body > *').evaluateAll(items => items.map(node => node.localName)),
      activeElements: await page.locator('script, a[href], iframe, img, form, link[href]').count(), requests,
      csp: await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content'),
      documentURL: page.url(),
    };
  } finally {
    await page.close();
  }
}

async function main() {
  if (process.getuid() === 0) throw new Error('unprivileged process required');
  const context = await chromium.launchPersistentContext(path.join(process.cwd(), 'profile'), {
    executablePath: path.join(process.cwd(), 'chrome-headless-shell-linux64/chrome-headless-shell'),
    chromiumSandbox: true, headless: true, javaScriptEnabled: false, serviceWorkers: 'block',
    offline: true, bypassCSP: false, timeout: 20000,
  });
  try {
    const results = {};
    for (const name of ['canonical', 'missing_row', 'missing_heading']) results[name] = await observe(context, name);
    process.stdout.write(JSON.stringify(results));
  } finally {
    await context.close();
  }
}
main().catch(error => { console.error(error.name); process.exitCode = 1; });
