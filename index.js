const express = require('express');
const puppeteer = require('puppeteer-core');

const app = express();
const PORT = process.env.PORT || 3000;

// Render 서버에 기본 설치된 Chrome 경로들
const CHROME_PATHS = [
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/snap/bin/chromium'
];

async function findChrome() {
  const fs = require('fs');
  for (const p of CHROME_PATHS) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

app.get('/decode', async (req, res) => {
  const cbmUrl = req.query.url;
  if (!cbmUrl) return res.status(400).json({ error: 'url 파라미터 필요' });

  const chromePath = await findChrome();
  if (!chromePath) {
    return res.status(500).json({ error: 'Chrome 없음', paths: CHROME_PATHS });
  }

  let browser;
  try {
    browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--single-process',
        '--no-zygote'
      ]
    });

    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
    await page.goto(cbmUrl, { waitUntil: 'networkidle2', timeout: 20000 });

    const finalUrl = page.url();

    if (finalUrl.indexOf('news.google.com') > -1) {
      return res.status(422).json({ error: '리다이렉트 실패', finalUrl: finalUrl });
    }

    res.json({ url: finalUrl });

  } catch(e) {
    res.status(500).json({ error: e.message });
  } finally {
    if (browser) await browser.close();
  }
});

app.get('/health', async (req, res) => {
  const chromePath = await findChrome();
  res.json({ status: 'ok', chrome: chromePath || 'not found' });
});

app.listen(PORT, function() {
  console.log('BRDB Proxy 실행 중: ' + PORT);
});
