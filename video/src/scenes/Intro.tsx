import { useCopy } from '../i18n';
import { useCurrentFrame } from 'remotion';
import { appear, colors, Tag } from '../theme';

export const Intro = () => {
  const frame = useCurrentFrame();
  const copy = useCopy();
  return <div style={{ paddingTop: 58 }}>
    <div style={{ opacity: appear(frame) }}><Tag style={{ color: colors.lime }}>{copy.introTag}</Tag></div>
    <div style={{ fontSize: 106, lineHeight: 1.06, letterSpacing: -5, fontWeight: 750, marginTop: 34, opacity: appear(frame, 5), translate: `0 ${(1 - appear(frame, 5)) * 35}px` }}>{copy.headlineOne}<br /><span style={{ color: colors.lime }}>{copy.headlineTwo}</span></div>
    <div style={{ marginTop: 52, display: 'flex', alignItems: 'center', gap: 30, opacity: appear(frame, 13) }}>
      <div style={{ flex: 1, padding: '28px 32px', border: `1px solid ${colors.line}`, backgroundColor: colors.card, borderRadius: 22 }}>
        <div style={{ color: colors.amber, fontSize: 20, letterSpacing: 3 }}>{copy.before}</div>
        <div style={{ fontSize: 42, fontWeight: 700, marginTop: 12 }}>{copy.baseline}</div>
        <div style={{ fontSize: 27, color: colors.muted, marginTop: 8 }}>{copy.baselineSub}</div>
      </div>
      <div style={{ fontSize: 40, fontStyle: 'italic', color: colors.muted }}>{copy.versus}</div>
      <div style={{ flex: 1, padding: '28px 32px', border: `1px solid ${colors.lime}`, backgroundColor: '#22382A', borderRadius: 22 }}>
        <div style={{ color: colors.lime, fontSize: 20, letterSpacing: 3 }}>{copy.after}</div>
        <div style={{ fontSize: 42, fontWeight: 700, marginTop: 12 }}>{copy.pooled}</div>
        <div style={{ fontSize: 27, color: colors.muted, marginTop: 8 }}>{copy.pooledSub}</div>
      </div>
    </div>
  </div>;
};
