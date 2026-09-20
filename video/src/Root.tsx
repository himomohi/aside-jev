import './index.css';
import { LocaleContext, resolveLocale, useCopy } from './i18n';
import { Composition, useCurrentFrame } from 'remotion';
import { TransitionSeries, linearTiming } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { Shell } from './theme';
import { Intro } from './scenes/Intro';
import { Race } from './scenes/Race';
import { Results } from './scenes/Results';

const Duel = () => {
  const frame = useCurrentFrame();
  const copy = useCopy();
  return <Shell chapter={frame < 108 ? copy.setupChapter : frame < 396 ? copy.raceChapter : copy.resultsChapter}>
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={120}><Intro /></TransitionSeries.Sequence>
      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
      <TransitionSeries.Sequence durationInFrames={300}><Race /></TransitionSeries.Sequence>
      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 12 })} />
      <TransitionSeries.Sequence durationInFrames={204}><Results /></TransitionSeries.Sequence>
    </TransitionSeries>
  </Shell>;
};

const LocalizedDuel = ({ locale }: { locale: string }) => <LocaleContext.Provider value={resolveLocale(locale)}><Duel /></LocaleContext.Provider>;

export const RemotionRoot = () => <Composition id="SpeedDuel" component={LocalizedDuel} defaultProps={{ locale: 'en' }} width={1920} height={1080} fps={30} durationInFrames={600} />;
