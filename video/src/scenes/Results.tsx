import { useCopy } from '../i18n';
import { useCurrentFrame } from 'remotion';
import { appear, colors, data, reduction, Tag } from '../theme';

export const Results = () => {
  const frame = useCurrentFrame();
  const copy = useCopy();
  return <div style={{ paddingTop: 38 }}>
    <Tag style={{ color: colors.lime }}>{copy.resultsTag}</Tag>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 30, marginTop: 26, opacity: appear(frame) }}>
      <span style={{ color: colors.lime, fontSize: 158, lineHeight: 1.1, fontWeight: 700, letterSpacing: -7 }}>{reduction.toFixed(1)}<span style={{ fontSize: 88 }}>%</span></span>
      <div style={{ fontSize: 52, fontWeight: 700, lineHeight: 1.25 }}>{copy.lower}<br /><span style={{ fontSize: 31, fontWeight: 400, color: colors.muted }}>{copy.localExperiment}</span></div>
    </div>
    <div style={{ display: 'flex', gap: 26, marginTop: 36 }}>
      {[
        [copy.median, `${data.baseline.p50Ms.toFixed(3)} → ${data.pooled.p50Ms.toFixed(3)}`, copy.perRequest],
        [copy.tail, `${data.baseline.p95Ms.toFixed(3)} → ${data.pooled.p95Ms.toFixed(3)}`, copy.msSamples],
        [copy.connections, `${data.baseline.tcpConnections} → ${data.pooled.tcpConnections}`, copy.connectionSamples],
      ].map(([title, value, unit], index) => <div key={title} style={{ flex: 1, padding: '28px 30px', border: `1px solid ${colors.line}`, borderRadius: 22, backgroundColor: colors.card, opacity: appear(frame, 5 + index * 6), translate: `0 ${(1 - appear(frame, 5 + index * 6)) * 18}px` }}>
        <div style={{ color: colors.muted, fontSize: 25 }}>{title}</div><div style={{ fontSize: index === 2 ? 57 : 49, fontWeight: 700, marginTop: 20, letterSpacing: -2 }}>{value}</div><div style={{ fontSize: 23, color: colors.muted, marginTop: 12 }}>{unit}</div>
      </div>)}
    </div>
    <div style={{ fontSize: 28, color: colors.ink, marginTop: 36 }}>{copy.notModelComparison}</div>
    <div style={{ fontSize: 23, color: colors.muted, marginTop: 14 }}>{copy.reproduce}: scripts/benchmark_latency.py <span style={{ margin: '0 14px' }}>·</span> {copy.method}: docs/VALIDATION.md</div>
  </div>;
};
