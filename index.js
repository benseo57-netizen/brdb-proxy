const express = require('express');
const axios = require('axios');

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/decode', async (req, res) => {
  const cbmUrl = req.query.url;
  if (!cbmUrl) return res.status(400).json({ error: 'url 파라미터 필요' });

  try {
    const response = await axios.get(cbmUrl, {
      maxRedirects: 10,
      timeout: 15000,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
      },
      validateStatus: () => true
    });

    const finalUrl = response.request && response.request.res && response.request.res.responseUrl
      ? response.request.res.responseUrl
      : cbmUrl;

    const html = typeof response.data === 'string' ? response.data : '';

    const urlMatch = html.match(/window\.location\.replace\(['"]([^'"]+)['"]\)/)
      || html.match(/url=([^&"'\s]+)/)
      || html.match(/href="(https?:\/\/(?!.*google)[^"]+)"/);

    const extractedUrl = urlMatch ? urlMatch[1] : null;

    const resultUrl = (finalUrl && finalUrl.indexOf('news.google.com') === -1)
      ? finalUrl
      : extractedUrl;

    if (!resultUrl || resultUrl.indexOf('news.google.com') > -1) {
      return res.status(422).json({
        error: '실제 URL 추출 실패',
        finalUrl: finalUrl,
        htmlSnippet: html.substring(0, 300)
      });
    }

    res.json({ url: resultUrl });

  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});

app.listen(PORT, function() {
  console.log('BRDB Proxy 실행 중: ' + PORT);
});
