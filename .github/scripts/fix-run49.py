#!/usr/bin/env python3
"""Run #49 fixes on master (old version):
1. Port the input-flash fix from dev-0.6.3 (search page top inset goes to 0
   during the push transition, so the input first renders at the status
   bar then jumps down): new hook useStableTopInset + searchPage uses it.
2. Backup export on iOS: the internal folder picker is sandbox-only, so
   use the system share sheet instead -- the user can save the backup to
   any location in the Files app (iCloud, On My iPhone, ...).

Run against a checkout of master (repo root as argv[1], default '.').
Every replacement asserts its expected occurrence count.
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

USE_STABLE_TOP_INSET = """import { useSafeAreaInsets } from "react-native-safe-area-context";

/**
 * 顶部安全区高度（状态栏/刘海/灵动岛）。页面转场动画期间，系统返回的 top 会短暂变成 0，
 * 导致顶部输入框先贴到状态栏、动画结束后再跳回正确位置（闪一下）。
 * 这里记住曾经测到的最大值，top 一旦量出来就不再回落到 0。
 */
let maxTopInset = 0;

export default function useStableTopInset(): number {
    const { top } = useSafeAreaInsets();
    if (top > maxTopInset) {
        maxTopInset = top;
    }
    return Math.max(top, maxTopInset);
}
"""

# New files to create: (relative path, content)
NEW_FILES = [
    ("src/hooks/useStableTopInset.ts", USE_STABLE_TOP_INSET),
]

# (relative path, old, new, expected occurrences)
REPLACEMENTS = [
    # ---- input-flash fix: searchPage ----
    ("src/pages/searchPage/index.tsx",
     'import { useI18N } from "@/core/i18n";',
     'import { useI18N } from "@/core/i18n";\nimport useStableTopInset from "@/hooks/useStableTopInset";', 1),
    ("src/pages/searchPage/index.tsx",
     "    const { t } = useI18N();",
     "    const { t } = useI18N();\n    const topInset = useStableTopInset();", 1),
    ("src/pages/searchPage/index.tsx",
     '        <SafeAreaView edges={["bottom", "top"]} style={style.wrapper}>',
     '        <SafeAreaView edges={["bottom"]} style={[style.wrapper, { paddingTop: topInset }]}>', 1),

    # ---- backup export on iOS: system share sheet ----
    ("src/pages/setting/settingTypes/backupSetting.tsx",
     'import { ScrollView, StyleSheet } from "react-native";',
     'import { Platform, ScrollView, StyleSheet } from "react-native";', 1),
    ("src/pages/setting/settingTypes/backupSetting.tsx",
     'import { getDocumentAsync } from "expo-document-picker";',
     'import { getDocumentAsync } from "expo-document-picker";\nimport Share from "react-native-share";\nimport { DocumentDirectoryPath } from "react-native-fs";', 1),
    ("src/pages/setting/settingTypes/backupSetting.tsx",
     '    const onBackupToLocal = async () => {\n        navigate(ROUTE_PATH.FILE_SELECTOR, {',
     '    const onBackupToLocal = async () => {\n'
     '        // iOS 沙盒内无法自选任意文件夹：改用系统分享单，\n'
     '        // 用户可在“存储到‘文件’”里把备份存到手机任意位置。\n'
     '        if (Platform.OS === "ios") {\n'
     '            const raw = Backup.backup();\n'
     '            const filePath = `${DocumentDirectoryPath}/backup.json`;\n'
     '            try {\n'
     '                await writeInChunks(filePath, raw);\n'
     '            } catch (e: any) {\n'
     '                Toast.warn(t("toast.backupFail", { reason: e?.message ?? e }));\n'
     '                return;\n'
     '            }\n'
     '            try {\n'
     '                await Share.open({\n'
     '                    url: `file://${filePath}`,\n'
     '                    type: "application/json",\n'
     '                    filename: "backup.json",\n'
     '                });\n'
     '                Toast.success(t("toast.backupSuccess"));\n'
     '            } catch {\n'
     '                // 用户取消分享，不提示；备份已保存在应用 Documents 内\n'
     '            }\n'
     '            return;\n'
     '        }\n'
     '        navigate(ROUTE_PATH.FILE_SELECTOR, {', 1),
]

def main() -> None:
    for rel, content in NEW_FILES:
        path = ROOT / rel
        if path.exists():
            raise SystemExit(f"FAIL {rel}: file already exists, refusing to overwrite")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"created {rel}")
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
    print(f"\nAll {len(REPLACEMENTS)} replacements applied + {len(NEW_FILES)} new file(s).")

if __name__ == "__main__":
    main()
