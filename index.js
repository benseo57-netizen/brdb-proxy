const express = require('express');
const { chromium } = require('playwright');

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/decode', async (req, res) => {
  const cbmUrl = req.query.url;

  if (!cbmUrl) {
    return res.status(400).json({ error: 'url 파라미터 필요' });
  }

  let browser;
  try {
    browser = await chromium.launch({ args: ['--no-sandbox'] });
    const page = await browser.newPage();

    await page.goto(cbmUrl, { waitUntil: 'networkidle', timeout: 15000 });

    const finalUrl = page.url();

    if (finalUrl.indexOf('news.google.com') > -1) {
      return res.status(422).json({ error: '리다이렉트 실패' });
    }

    res.json({ url: finalUrl });

  } catch(e) {
    res.status(500).json({ error: e.message });
  } finally {
    if (browser) await browser.close();
  }
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.listen(PORT, () => {
  console.log('BRDB Proxy 서버 실행 중: ' + PORT);
});
