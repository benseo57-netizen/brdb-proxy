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

    // axios 리다이렉트 최종 URL 확인
    const finalUrl = response.request && response.request.res && response.request.res.responseUrl
      ? response.request.res.responseUrl
      : null;

    // 유효한 URL인지 확인 (https://로 시작하고 google 도메인 아닌 것)
    function isValidArticleUrl(url) {
      if (!url) return false;
      if (!url.startsWith('http')) return false;
      if (url.indexOf('news.google.com') > -1) return false;
      if (url.indexOf('google.com') > -1) return false;
      return true;
    }

    if (isValidArticleUrl(finalUrl)) {
      return res.json({ url: finalUrl });
    }

    // HTML에서 meta refresh 또는 canonical URL 추출
    const html = typeof response.data === 'string' ? response.data : '';

    // 방법1: meta refresh
    const metaMatch = html.match(/<meta[^>]+http-equiv="refresh"[^>]+content="[^"]*url=([^"&]+)/i);
    if (metaMatch && isValidArticleUrl(metaMatch[1])) {
      return res.json({ url: metaMatch[1] });
    }

    // 방법2: canonical link
    const canonicalMatch = html.match(/<link[^>]+rel="canonical"[^>]+href="([^"]+)"/i);
    if (canonicalMatch && isValidArticleUrl(canonicalMatch[1])) {
      return res.json({ url: canonicalMatch[1] });
    }

    // 방법3: og:url
    const ogMatch = html.match(/<meta[^>]+property="og:url"[^>]+content="([^"]+)"/i);
    if (ogMatch && isValidArticleUrl(ogMatch[1])) {
      return res.json({ url: ogMatch[1] });
    }

    return res.status(422).json({
      error: '실제 URL 추출 실패',
      finalUrl: finalUrl,
      htmlSnippet: html.substring(0, 300)
    });

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
