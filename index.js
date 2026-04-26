const express = require('express');
const puppeteer = require('puppeteer');

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/decode', async (req, res) => {
  const cbmUrl = req.query.url;
  if (!cbmUrl) return res.status(400).json({ error: 'url 파라미터 필요' });

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--no-first-run',
        '--no-zygote',
        '--single-process'
      ]
    });

    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36');

    await page.goto(cbmUrl, { waitUntil: 'networkidle2', timeout: 20000 });

    const finalUrl = page.url();

    if (finalUrl.indexOf('news.google.com') > -1) {
      return res.status(422).json({ error: '리다이렉트 실패 — 구글뉴스에 머물러 있음' });
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
  console.log('BRDB Proxy 실행 중: ' + PORT);
});
