import { useCopy } from './i18n';
import type { CSSProperties, ReactNode } from 'react';
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import measurements from './benchmark.json';

export const data = measurements;
export const reduction = (1 - data.pooled.p50Ms / data.baseline.p50Ms) * 100;
export const colors = { bg: '#101E19', card: '#192D25', line: '#355044', ink: '#F4F2E7', muted: '#A4B8A8', lime: '#D2F78C', amber: '#D7B999' };
export const font = '"Arial", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';
export const ease = Easing.bezier(0.2, 0.8, 0.2, 1);
export const appear = (frame: number, delay = 0) => interpolate(frame, [delay, delay + 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease });

export const Shell = ({ children, chapter }: { children: ReactNode; chapter: string }) => {
  const frame = useCurrentFrame();
  const copy = useCopy();
  return <AbsoluteFill style={{ backgroundColor: colors.bg, color: colors.ink, fontFamily: font, padding: '58px 80px' }}>
    <AbsoluteFill style={{ backgroundImage: 'radial-gradient(ellipse at 90% 10%, #284334 0%, transparent 55%)', opacity: 0.55 }} />
    <div style={{ position: 'absolute', inset: 0, opacity: 0.1, backgroundImage: 'linear-gradient(#A4B8A8 1px, transparent 1px), linear-gradient(90deg, #A4B8A8 1px, transparent 1px)', backgroundSize: '80px 80px', maskImage: 'linear-gradient(transparent, black)' }} />
    <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 52 }}>
      <div style={{ fontWeight: 700, fontSize: 34, letterSpacing: -1 }}><span style={{ color: colors.lime }}>a/</span> aside <span style={{ color: colors.muted, fontWeight: 400 }}>×</span> jev</div>
      <div style={{ fontSize: 21, letterSpacing: 4, color: colors.muted }}>{copy.duel} <span style={{ marginLeft: 35, color: colors.ink }}>{chapter}</span></div>
    </div>
    <div style={{ position: 'relative', flex: 1 }}>{children}</div>
    <div style={{ position: 'relative', borderTop: `1px solid ${colors.line}`, paddingTop: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 30 }}>
      <div style={{ fontSize: 24, color: colors.muted }}>{copy.scope} · <span style={{ color: colors.ink }}>{copy.noInference}</span></div>
      <div style={{ fontSize: 20, color: colors.muted, whiteSpace: 'nowrap' }}>{data.measuredOn} · n={data.sampleCount} {copy.perMethod}</div>
    </div>
    <div style={{ position: 'absolute', bottom: 0, left: 0, height: 4, width: `${Math.min(100, frame / 600 * 100)}%`, backgroundColor: colors.lime }} />
  </AbsoluteFill>;
};

export const Tag = ({ children, style }: { children: ReactNode; style?: CSSProperties }) => <div style={{ display: 'inline-flex', alignItems: 'center', border: `1px solid ${colors.line}`, padding: '12px 20px', borderRadius: 100, fontSize: 22, color: colors.muted, ...style }}>{children}</div>;
