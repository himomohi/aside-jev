import { createContext, useContext } from 'react';
import en from './locales/en.json';
import ko from './locales/ko.json';

export type Locale = 'en' | 'ko';
export const dictionaries: Record<Locale, typeof en> = { en, ko };
export const resolveLocale = (locale: unknown): Locale => locale === 'ko' ? 'ko' : 'en';
export const LocaleContext = createContext<Locale>('en');
export const useCopy = () => dictionaries[useContext(LocaleContext)];
