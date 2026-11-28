#!/usr/bin/env python3
"""Audit fixes on master (old version) — follow-up to run #49:
1. Detail-page icons still white-on-light after the #48 re-theme:
   albumCover/operations.tsx (download/comment/more), heartIcon (heart),
   lyric/lyricOperations.tsx (font-size/offset/search/translate/more)
   -> color={colors.text}.
2. Status bar defaults to white text on every page in light theme
   -> derive barStyle from the theme (dark-content in light theme).
3. Song-options panel "查看评论" displaced: FlatList getItemLayout reserves
   a slot for hidden rows that render null -> filter hidden rows first.
4. Top-inset flash on pushed pages (same root cause as the search-page
   input flash): verticalSafeAreaView + setting + musicDetail use the
   stable-top-inset pattern instead of top-edge SafeAreaView.
5. MMKV dirs are never pre-created by setupFolder() -> create them.

Run against a checkout of master (repo root as argv[1], default '.').
Every replacement asserts its expected occurrence count.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

# (relative path, old, new, expected occurrences)
REPLACEMENTS = [
    # ---- 1a. operations.tsx: white icons -> colors.text ----
    ("src/pages/musicDetail/components/content/albumCover/operations.tsx",
     'import i18n from "@/core/i18n";',
     'import i18n from "@/core/i18n";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/content/albumCover/operations.tsx",
     "export default function Operations() {\n    const musicItem = useCurrentMusic();",
     "export default function Operations() {\n    const musicItem = useCurrentMusic();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/content/albumCover/operations.tsx",
     'color="white"',
     "color={colors.text}", 3),

    # ---- 1b. heartIcon: white heart -> colors.text ----
    ("src/pages/musicDetail/components/content/heartIcon/index.tsx",
     'import MusicSheet, { useFavorite } from "@/core/musicSheet";',
     'import MusicSheet, { useFavorite } from "@/core/musicSheet";\nimport useColors from "@/hooks/useColors";', 1),
    ("src/pages/musicDetail/components/content/heartIcon/index.tsx",
     "export default function () {\n    const musicItem = useCurrentMusic();",
     "export default function () {\n    const musicItem = useCurrentMusic();\n    const colors = useColors();", 1),
    ("src/pages/musicDetail/components/content/heartIcon/index.tsx",
     'color="white"',
     "color={colors.text}", 1),

    # ---- 1c. lyricOperations.tsx: white icons -> colors.text ----
    ("src/pages/musicDetail/components/content/lyric/lyricOperations.tsx",
     'color="white"',
     "color={colors.text}", 3),
    ("src/pages/musicDetail/components/content/lyric/lyricOperations.tsx",
     'showTranslation && hasTranslation ? colors.primary : "white"',
     "showTranslation && hasTranslation ? colors.primary : colors.text", 1),
    ("src/pages/musicDetail/components/content/lyric/lyricOperations.tsx",
     'color={"white"}',
     "color={colors.text}", 1),

    # ---- 2. statusBar: theme-aware default ----
    ("src/components/base/statusBar.tsx",
     'import useColors from "@/hooks/useColors";',
     'import useColors from "@/hooks/useColors";\nimport Theme from "@/core/theme";', 1),
    ("src/components/base/statusBar.tsx",
     "    const colors = useColors();",
     "    const colors = useColors();\n    const theme = Theme.useTheme();", 1),
    ("src/components/base/statusBar.tsx",
     'barStyle={barStyle ?? "light-content"}',
     'barStyle={barStyle ?? (theme.dark ? "light-content" : "dark-content")}', 1),

    # ---- 3. musicItemOptions: filter hidden rows before FlatList ----
    ("src/components/panels/types/musicItemOptions.tsx",
     "data={options}",
     "data={options.filter(_ => _.show !== false)}", 1),

    # ---- 4a. verticalSafeAreaView: stable top inset ----
    ("src/components/base/verticalSafeAreaView.tsx",
     'import { SafeAreaView } from "react-native-safe-area-context";',
     'import { SafeAreaView } from "react-native-safe-area-context";\nimport useStableTopInset from "@/hooks/useStableTopInset";', 1),
    ("src/components/base/verticalSafeAreaView.tsx",
     "    const { children, style, mode } = props;",
     "    const { children, style, mode } = props;\n    const topInset = useStableTopInset();", 1),
    ("src/components/base/verticalSafeAreaView.tsx",
     '<SafeAreaView style={style} mode={mode} edges={["top", "bottom"]}>',
     '<SafeAreaView style={[style, { paddingTop: topInset }]} mode={mode} edges={["bottom"]}>', 1),

    # ---- 4b. setting page: stable top inset ----
    ("src/pages/setting/index.tsx",
     'import useColors from "@/hooks/useColors";',
     'import useColors from "@/hooks/useColors";\nimport useStableTopInset from "@/hooks/useStableTopInset";', 1),
    ("src/pages/setting/index.tsx",
     "    const colors = useColors();",
     "    const colors = useColors();\n    const topInset = useStableTopInset();", 1),
    ("src/pages/setting/index.tsx",
     '<SafeAreaView edges={["bottom", "top"]} style={[style.wrapper, { backgroundColor: colors?.pageBackground ?? "#fafafa" }]}>',
     '<SafeAreaView edges={["bottom"]} style={[style.wrapper, { backgroundColor: colors?.pageBackground ?? "#fafafa", paddingTop: topInset }]}>', 1),

    # ---- 4c. musicDetail page: stable top inset ----
    ("src/pages/musicDetail/index.tsx",
     'import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";',
     'import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";\nimport useStableTopInset from "@/hooks/useStableTopInset";', 1),
    ("src/pages/musicDetail/index.tsx",
     "    const orientation = useOrientation();",
     "    const orientation = useOrientation();\n    const topInset = useStableTopInset();", 1),
    ("src/pages/musicDetail/index.tsx",
     "<SafeAreaView style={globalStyle.fwflex1}>",
     '<SafeAreaView edges={["bottom"]} style={[globalStyle.fwflex1, { paddingTop: topInset }]}>', 1),

    # ---- 5. MMKV dirs pre-created in setupFolder ----
    ("src/entry/bootstrap/bootstrap.ts",
     "        checkAndCreateDir(pathConst.localLrcPath),",
     "        checkAndCreateDir(pathConst.localLrcPath),\n        checkAndCreateDir(pathConst.mmkvPath),\n        checkAndCreateDir(pathConst.mmkvCachePath),", 1),
]

def main() -> None:
    for rel, old, new, expected in REPLACEMENTS:
        path = ROOT / rel
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
