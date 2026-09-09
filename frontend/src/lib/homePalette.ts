import type { CSSProperties } from "react";
import { TEAM_COLOR_PALETTES } from "./color-utils";

/**
 * Home / landing topic colors — slots 1–7 on `rainbowPastel` (0-based indices below).
 *
 * | Slot | Topic      | Index | Hex (rainbowPastel) |
 * |------|------------|-------|---------------------|
 * | 1    | Spieler    | 0     | #1B8CA6             |
 * | 2    | Club       | 1     | #2CA89A             |
 * | 3    | Liga       | 2     | #8CBF8A             |
 * | 4    | Turnier    | 3     | #E6C86E             |
 * | 5    | Clubpokal  | 4     | #F7A86E             |
 * | 6    | Club 300 / Mein Club | 5 | #E86E56     |
 * | 7    | Glossar    | 6     | #D95A6A             |
 *
 * Keep element order in hero cards, entity-map rows, and nav groups aligned with
 * this sequence so color bands read consistently left-to-right.
 */
export const HOME_TOPIC_PALETTE = {
  player: 0,
  club: 1,
  league: 2,
  tournament: 3,
  clubpokal: 4,
  club300: 5,
  myClub: 5,
  glossary: 6,
} as const;

export type HomeTopicPaletteKey = keyof typeof HOME_TOPIC_PALETTE;

export function homePaletteColor(index: number): string {
  return TEAM_COLOR_PALETTES.rainbowPastel[index] ?? TEAM_COLOR_PALETTES.rainbowPastel[0];
}

export function homePaletteColorForTopic(topic: HomeTopicPaletteKey): string {
  return homePaletteColor(HOME_TOPIC_PALETTE[topic]);
}

export function homePaletteStyles(index: number): CSSProperties {
  const color = homePaletteColor(index);
  return {
    borderTopColor: color,
    backgroundColor: `${color}18`,
  };
}

export function homePaletteStylesForTopic(topic: HomeTopicPaletteKey): CSSProperties {
  return homePaletteStyles(HOME_TOPIC_PALETTE[topic]);
}

export function homePaletteTitleStyle(index: number): CSSProperties {
  return { color: homePaletteColor(index) };
}

/** Solid fill for in-card CTAs (e.g. Glossar button). */
export function homePaletteButtonStyle(index: number): CSSProperties {
  const color = homePaletteColor(index);
  const lightBackground = index === 2 || index === 3;
  return {
    backgroundColor: color,
    color: lightBackground ? "#18181B" : "#FFFFFF",
  };
}

export function homePaletteButtonStyleForTopic(topic: HomeTopicPaletteKey): CSSProperties {
  return homePaletteButtonStyle(HOME_TOPIC_PALETTE[topic]);
}

/** Full-bleed tour / banner chrome — pastels are mixed darker so white type stays readable. */
export function homePaletteBannerStyle(index: number): CSSProperties {
  const color = homePaletteColor(index);
  return {
    backgroundColor: `color-mix(in srgb, ${color} 62%, #18181B 38%)`,
    color: "#FFFFFF",
  };
}

export function homePaletteBannerStyleForTopic(topic: HomeTopicPaletteKey): CSSProperties {
  return homePaletteBannerStyle(HOME_TOPIC_PALETTE[topic]);
}

/** Tint band for results-page headers and topic-active nav rows. */
export function topicTintStyle(topic: HomeTopicPaletteKey): CSSProperties {
  const color = homePaletteColorForTopic(topic);
  return {
    borderTopColor: color,
    backgroundColor: `${color}18`,
  };
}

export function topicAccentColor(topic: HomeTopicPaletteKey): string {
  return homePaletteColorForTopic(topic);
}

/** @deprecated Use HOME_TOPIC_PALETTE */
export const HOME_HERO_PALETTE = HOME_TOPIC_PALETTE;
