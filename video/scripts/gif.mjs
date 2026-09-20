import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { selectedLocales, mediaBase } from './locales.mjs';
const media = resolve(import.meta.dirname, '../../docs/media');
for (const locale of selectedLocales()) {
const base = mediaBase(locale);
execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', resolve(media, `${base}.mp4`), '-filter_complex', '[0:v]fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle', '-loop', '0', resolve(media, `${base}.gif`)], { stdio: 'inherit' });
}
