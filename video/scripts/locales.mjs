// 생략 시 영문 산출물을 만든다. all은 두 언어를 같은 데이터로 렌더링한다.
export function selectedLocales(args = process.argv.slice(2)) {
  const index = args.indexOf('--locale');
  const locale = index < 0 ? 'en' : args[index + 1];
  if (!['en', 'ko', 'all'].includes(locale)) throw new Error('Use --locale en, ko, or all.');
  return locale === 'all' ? ['en', 'ko'] : [locale];
}
export const mediaBase = (locale) => `jev-speed-duel${locale === 'ko' ? '.ko' : ''}`;
