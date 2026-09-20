import { useCopy } from '../i18n';
import { interpolate, useCurrentFrame } from 'remotion';
import { appear, colors, data, Tag } from '../theme';

// 두 레인 모두 동일한 환산을 사용한다. p50 1.157ms를 화면의 5초로 확대한다.
export const raceTiming = { start: 60, baselineFrames: 150 };
export const Race = () => {
  const frame = useCurrentFrame();
  const copy = useCopy();
  const elapsedMs = Math.max(0, frame - raceTiming.start) / raceTiming.baselineFrames * data.baseline.p50Ms;
  const start = frame < 60 ? (frame < 20 ? '3' : frame < 40 ? '2' : '1') : copy.go;
  return <div style={{ paddingTop: 36 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div><div style={{ fontSize: 58, letterSpacing: -2, fontWeight: 700 }}>{copy.raceTitle}</div><div style={{ color: colors.muted, fontSize: 26, marginTop: 15 }}>{copy.raceSubtitle}</div></div>
      <Tag style={{ color: colors.lime, fontSize: 25 }}>{copy.timeExpanded}</Tag>
    </div>
    <div style={{ display: 'flex', gap: 32, marginTop: 36 }}>
      {[{ label: copy.baseline, sub: copy.before, metric: data.baseline, accent: colors.amber }, { label: copy.pooled, sub: copy.after, metric: data.pooled, accent: colors.lime }].map(({ label, sub, metric, accent }) => {
        const progress = Math.min(1, elapsedMs / metric.p50Ms);
        const done = elapsedMs >= metric.p50Ms;
        return <div key={sub} style={{ flex: 1, height: 454, border: `1px solid ${done ? accent : colors.line}`, borderRadius: 26, backgroundColor: colors.card, padding: 34 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><span style={{ color: accent, fontSize: 20, letterSpacing: 3 }}>{sub}</span><span style={{ color: done ? accent : colors.muted, fontSize: 23 }}>{done ? copy.finish : frame < 60 ? copy.ready : copy.running}</span></div>
          <div style={{ fontSize: 42, fontWeight: 700, marginTop: 18 }}>{label}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginTop: 12 }}><span style={{ fontSize: 100, fontWeight: 700, letterSpacing: -4, fontVariantNumeric: 'tabular-nums', color: done ? accent : colors.ink }}>{Math.min(metric.p50Ms, elapsedMs).toFixed(3)}</span><span style={{ fontSize: 32, color: colors.muted }}>ms</span></div>
          <div style={{ position: 'relative', height: 78, marginTop: 22 }}>
            <div style={{ position: 'absolute', top: 35, left: 0, right: 0, height: 3, backgroundColor: colors.line }} />
            <div style={{ position: 'absolute', top: 34, left: 0, width: `${progress * 93}%`, height: 5, backgroundColor: accent }} />
            <div style={{ position: 'absolute', left: `${progress * 93}%`, top: 12, width: 52, height: 48, borderRadius: 13, backgroundColor: accent, color: colors.bg, fontSize: 24, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 0 36px ${accent}25` }}>J</div>
            <div style={{ position: 'absolute', right: 0, top: 8, height: 62, width: 3, backgroundColor: colors.muted }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: colors.muted, fontSize: 23 }}><span>{copy.start}</span><span>p50 {metric.p50Ms.toFixed(3)}ms</span></div>
        </div>;
      })}
    </div>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 26 }}>
      <div style={{ color: colors.muted, fontSize: 26 }}>{copy.raceNote}</div>
      <div style={{ color: colors.lime, fontWeight: 700, fontSize: 48, opacity: frame < 83 ? 1 : interpolate(frame, [83, 96], [1, 0], { extrapolateRight: 'clamp' }), scale: 0.9 + appear(frame % 20) * 0.1 }}>{start}</div>
    </div>
  </div>;
};
