import { createI18n } from './i18n.mjs';

// 국가 조회 응답의 IP 원문은 사용하거나 저장하지 않는다.
export function createExtensionI18n(storage) {
  if (storage === undefined) { try { storage = globalThis.localStorage; } catch { storage = null; } }
  const key = 'aside-jev.extension.language';
  const base = createI18n(key, storage);
  let selection = 'auto';
  let revision = 0;
  try { const saved = storage?.getItem(key); if (saved === 'ko' || saved === 'en') selection = saved; } catch {}
  const api = {
    ...base,
    get language() { return base.language; },
    get locale() { return base.locale; },
    get selection() { return selection; },
    setLanguage(next) {
      revision++;
      selection = ['en', 'ko'].includes(next) ? next : 'auto';
      try { storage?.setItem(key, selection); } catch {}
      if (selection !== 'auto') base.setLanguage(selection, { persist: false });
    },
    async resolve({ fetcher, browserLanguage = globalThis.navigator?.language ?? 'en' } = {}) {
      if (selection !== 'auto') return;
      const current = ++revision;
      const fallback = browserLanguage.toLowerCase().startsWith('ko') ? 'ko' : 'en';
      let language = fallback;
      // Node 기반 DOM 검사에서는 실제 네트워크 요청을 만들지 않는다.
      fetcher ??= globalThis.location?.protocol === 'chrome-extension:' ? globalThis.fetch : null;
      try {
        if (fetcher) {
          const response = await fetcher('https://api.country.is/', {
            credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store',
            signal: AbortSignal.timeout(2500),
          });
          if (!response.ok) throw new Error('country_lookup_failed');
          const data = await response.json();
          if (typeof data.country !== 'string' || !/^[A-Z]{2}$/.test(data.country)) throw new Error('invalid_country');
          language = data.country === 'KR' ? 'ko' : 'en';
        }
      } catch { /* 실패하면 브라우저 언어로 표시한다. */ }
      if (current === revision && selection === 'auto') base.setLanguage(language, { persist: false });
    },
  };
  return api;
}
