#!/usr/bin/env python3
"""Fix the song-detail page black bar on master: make the detail page
follow the theme (light theme = light background + dark text) instead of
hardcoded black background + white text.

Run against a checkout of master (repo root as argv[1], default '.').
Every replacement asserts its expected occurrence count so a drifted
file fails loudly instead of silently half-applying.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

# (relative path, old, new, expected occurrences)
REPLACEMENTS = [
    # ---- background.tsx: theme base instead of hardcoded #000 ----
    ("src/pages/musicDetail/components/background.tsx",
     'import { useCurrentMusic } from "@/core/trackPlayer";',
     'import { useCurrentMusic } from "@/core/trackPlayer";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/background.tsx",
     "    const musicItem = useCurrentMusic();",
     "    const musicItem = useCurrentMusic();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/background.tsx",
     "            <View style={style.background} />",
     '            <View\n                style={[\n                    style.background,\n                    { backgroundColor: colors?.pageBackground ?? "#fafafa" },\n                ]}\n            />', 1),
    ("src/pages/musicDetail/components/background.tsx",
     '        backgroundColor: "#000",\n', "", 1),

    # ---- navBar.tsx: white title/icons -> theme text ----
    ("src/pages/musicDetail/components/navBar.tsx",
     'import { useCurrentMusic } from "@/core/trackPlayer";',
     'import { useCurrentMusic } from "@/core/trackPlayer";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/navBar.tsx",
     "    const musicItem = useCurrentMusic();",
     "    const musicItem = useCurrentMusic();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/navBar.tsx",
     '                color="white"', "                color={colors.text}", 2),
    ("src/pages/musicDetail/components/navBar.tsx",
     '                <Text numberOfLines={1} style={styles.headerTitleText}>',
     '                <Text numberOfLines={1} style={[styles.headerTitleText, { color: colors.text }]}>', 1),
    ("src/pages/musicDetail/components/navBar.tsx",
     '                    <Text style={styles.headerArtistText} numberOfLines={1}>',
     '                    <Text style={[styles.headerArtistText, { color: colors.text }]} numberOfLines={1}>', 1),
    ("src/pages/musicDetail/components/navBar.tsx",
     "                            containerStyle={styles.tagBg}",
     "                            containerStyle={[styles.tagBg, { backgroundColor: colors.divider }]}", 1),
    ("src/pages/musicDetail/components/navBar.tsx",
     "                            style={styles.tagText}",
     "                            style={[styles.tagText, { color: colors.text }]}", 1),

    # ---- lyric/index.tsx: white lyric text -> theme text ----
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     'import { useI18N } from "@/core/i18n";',
     'import { useI18N } from "@/core/i18n";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "    const { t } = useI18N();",
     "    const { t } = useI18N();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     '                        <Loading color="white" />',
     "                        <Loading color={colors.text} />", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "                                                        styles.lyricMetaText,\n                                                        fontSizeStyle,",
     "                                                        styles.lyricMetaText,\n                                                        { color: colors.text },\n                                                        fontSizeStyle,", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "                                                            styles.linkText,\n                                                            fontSizeStyle,",
     "                                                            styles.linkText,\n                                                            { color: colors.primary },\n                                                            fontSizeStyle,", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "                            <Text style={[styles.white, fontSizeStyle]}>",
     "                            <Text style={[styles.white, { color: colors.text }, fontSizeStyle]}>", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "style={[styles.searchLyric, fontSizeStyle]}",
     "style={[styles.searchLyric, { color: colors.primary }, fontSizeStyle]}", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "                            <View style={styles.singleLine} />",
     "                            <View style={[styles.singleLine, { backgroundColor: colors.divider }]} />", 1),
    ("src/pages/musicDetail/components/content/lyric/index.tsx",
     "                                style={styles.playIcon}",
     "                                style={[styles.playIcon, { color: colors.text }]}", 1),

    # ---- lyricItem.tsx: inactive lyric lines white -> theme text ----
    # colors is already available in this component (useColors at line 25).
    ("src/pages/musicDetail/components/content/lyric/lyricItem.tsx",
     "                lyricStyles.item,\n                {\n                    fontSize: fontSize || fontSizeConst.content,\n                },",
     "                lyricStyles.item,\n                { color: colors.text },\n                {\n                    fontSize: fontSize || fontSizeConst.content,\n                },", 1),
    ("src/pages/musicDetail/components/content/lyric/lyricItem.tsx",
     '    item: {\n        color: "white",\n        opacity: 0.6,',
     "    item: {\n        opacity: 0.6,", 1),
    # draggingItem is applied LAST in the style array, so its hardcoded
    # white would override the inline theme color -- it must go.
    ("src/pages/musicDetail/components/content/lyric/lyricItem.tsx",
     '    draggingItem: {\n        opacity: 0.9,\n        color: "white",\n    },',
     "    draggingItem: {\n        opacity: 0.9,\n    },", 1),

    # ---- draggingTime.tsx: time bubble -> theme colors ----
    ("src/pages/musicDetail/components/content/lyric/draggingTime.tsx",
     'import { useProgress } from "@/core/trackPlayer";',
     'import { useProgress } from "@/core/trackPlayer";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/content/lyric/draggingTime.tsx",
     "    const progress = useProgress();",
     "    const progress = useProgress();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/content/lyric/draggingTime.tsx",
     "        <Text style={style.draggingTimeText}>",
     "        <Text\n            style={[\n                style.draggingTimeText,\n                {\n                    color: colors.textSecondary,\n                    backgroundColor: colors.divider,\n                },\n            ]}>", 1),

    # ---- playControl.tsx: white control icons -> theme text ----
    ("src/pages/musicDetail/components/bottom/playControl.tsx",
     'import { musicIsPaused } from "@/utils/trackUtils";',
     'import { musicIsPaused } from "@/utils/trackUtils";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/bottom/playControl.tsx",
     "    const orientation = useOrientation();",
     "    const orientation = useOrientation();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/bottom/playControl.tsx",
     '                    color={"white"}', "                    color={colors.text}", 5),

    # ---- seekBar.tsx: time text + slider tints -> theme colors ----
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     'import TrackPlayer, { useProgress } from "@/core/trackPlayer";',
     'import TrackPlayer, { useProgress } from "@/core/trackPlayer";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     "function TimeLabel(props: ITimeLabelProps) {\n    return (\n        <Text style={style.text}>{timeformat(Math.max(props.time, 0))}</Text>\n    );\n}",
     "function TimeLabel(props: ITimeLabelProps) {\n    const colors = useColors();\n    return (\n        <Text style={[style.text, { color: colors.textSecondary }]}>\n            {timeformat(Math.max(props.time, 0))}\n        </Text>\n    );\n}", 1),
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     "    const progress = useProgress(1000);",
     "    const progress = useProgress(1000);\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     '                minimumTrackTintColor={"#cccccc"}',
     "                minimumTrackTintColor={colors.text}", 1),
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     '                maximumTrackTintColor={"#999999"}',
     "                maximumTrackTintColor={colors.divider}", 1),
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     '                thumbTintColor={"#dddddd"}',
     "                thumbTintColor={colors.text}", 1),
    ("src/pages/musicDetail/components/bottom/seekBar.tsx",
     '        color: "#cccccc",\n', "", 1),
]

def main() -> None:
    for rel, old, new, expected in REPLACEMENTS:
        path = ROOT / rel
        # Preserve the file's line endings: playControl.tsx is CRLF;
        # text-mode read would silently normalize it to LF and turn the
        # diff into a whole-file rewrite.
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        crlf = "\r\n" in text
        if crlf:
            text = text.replace("\r\n", "\n")
        found = text.count(old)
        if found != expected:
            raise SystemExit(
                f"FAIL {rel}: pattern {old[:60]!r} found {found}x, expected {expected}x"
            )
        text = text.replace(old, new)
        if crlf:
            text = text.replace("\n", "\r\n")
        path.write_bytes(text.encode("utf-8"))
        print(f"ok {rel}: {found}x  {old[:50]!r}  {'CRLF kept' if crlf else ''}")
    print(f"\nAll {len(REPLACEMENTS)} replacements applied.")

if __name__ == "__main__":
    main()
