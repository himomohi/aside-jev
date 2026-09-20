import { bundle } from '@remotion/bundler';
import { openBrowser, renderMedia, renderStill, selectComposition } from '@remotion/renderer';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { selectedLocales, mediaBase } from './locales.mjs';
const locales = selectedLocales();

// 직접 호출해도 서버 바인딩 제한을 먼저 적용한다.
await import('./loopback-only.cjs');
const root = resolve(import.meta.dirname, '..');
const output = resolve(root, '../docs/media');
await mkdir(output, { recursive: true });
const serveUrl = await bundle({ entryPoint: resolve(root, 'src/index.ts'), outDir: resolve(root, 'build'), enableCaching: true });
const browser = await openBrowser('chrome');
try {
  for (const locale of locales) {
  const inputProps = { locale };
  const base = mediaBase(locale);
  const composition = await selectComposition({ serveUrl, id: 'SpeedDuel', inputProps, puppeteerInstance: browser });
  if (process.argv.includes('--stills')) {
    await mkdir(resolve(root, 'out'), { recursive: true });
    for (const frame of [60, 153, 258, 336, 480]) {
      await renderStill({ serveUrl, composition, inputProps, puppeteerInstance: browser, frame, output: resolve(root, `out/${locale}-frame-${frame}.png`) });
    }
  } else {
    let last = -1;
    await renderMedia({ serveUrl, composition, inputProps, puppeteerInstance: browser, codec: 'h264', crf: 20, concurrency: 4, outputLocation: resolve(output, `${base}.mp4`), onProgress: ({ progress }) => {
      const step = Math.floor(progress * 10);
      if (step !== last) { console.log(`${locale} render ${step * 10}%`); last = step; }
    }});
    await renderStill({ serveUrl, composition, inputProps, puppeteerInstance: browser, frame: 336, output: resolve(output, `${base}-poster.png`) });
  }
  }
} finally {
  await browser.close({ silent: true });
}
