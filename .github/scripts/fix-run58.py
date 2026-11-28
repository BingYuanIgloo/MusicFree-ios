#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix-run58: MusicFree iOS — #56 用户反馈全量修复（build #57）。
在 master fa94b5a 之上应用。用法：python3 fix-run58.py [repo_root]
默认 repo_root 为当前目录。所有替换均为精确字符串匹配；失败会汇总报错并退出非零。
行尾处理：先把文件统一成 LF 做匹配，写回时恢复原行尾（CRLF 文件保持 CRLF）。
"""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

FAILURES = []
SUCCESSES = []


def _norm(text):
    return text.replace("\r\n", "\n")


def _read(path):
    with open(os.path.join(ROOT, path), "rb") as f:
        raw = f.read()
    crlf = b"\r\n" in raw
    return raw.decode("utf-8"), crlf


def _write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(os.path.join(ROOT, path), "wb") as f:
        f.write(text.encode("utf-8"))


def replace(path, old, new, count=1, tag=""):
    try:
        text, crlf = _read(path)
    except FileNotFoundError:
        FAILURES.append(f"{path}: file not found [{tag}]")
        return
    old_n, new_n, text_n = _norm(old), _norm(new), _norm(text)
    n = text_n.count(old_n)
    if n == 0:
        FAILURES.append(f"{path}: pattern not found [{tag}]")
        return
    if n < count:
        FAILURES.append(f"{path}: pattern found {n} time(s), need {count} [{tag}]")
        return
    text_n = text_n.replace(old_n, new_n, count)
    _write(path, text_n, crlf)
    SUCCESSES.append(f"{path} [{tag}]")


def replace_re(path, pattern, repl, tag="", flags=0):
    try:
        text, crlf = _read(path)
    except FileNotFoundError:
        FAILURES.append(f"{path}: file not found [{tag}]")
        return
    text_n = _norm(text)
    new_n, n = re.subn(pattern, repl, text_n, flags=flags)
    if n == 0:
        FAILURES.append(f"{path}: regex no match [{tag}]")
        return
    _write(path, new_n, crlf)
    SUCCESSES.append(f"{path} x{n} [{tag}]")


def write_new(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    SUCCESSES.append(f"{path} [new file]")


# ============================================================
# A. 跟随系统深浅色：加 Appearance 监听（mode.tsx 只在开关打开那一刻读一次，
#    之后切系统深浅色 App 不动，就是这个 bug）
# ============================================================
replace(
    "src/core/theme.ts",
    'import Config from "@/core/appConfig";',
    'import Config from "@/core/appConfig";\nimport { Appearance } from "react-native";',
    tag="A1 theme import Appearance",
)

replace(
    "src/core/theme.ts",
    """    const bgUrl = Config.getConfig("theme.background");""",
    """    // 跟随系统：系统深浅色一切换就跟着变（之前只在开关打开那一刻
    // 读一次 Appearance.getColorScheme()，之后切系统深浅色 App 不动）。
    const applySystemScheme = () => {
        if (!Config.getConfig("theme.followSystem")) {
            return;
        }
        const scheme = Appearance.getColorScheme();
        if (scheme === "dark") {
            setTheme("p-dark");
        } else if (scheme === "light") {
            setTheme("p-light");
        }
    };
    applySystemScheme();
    Appearance.addChangeListener(() => applySystemScheme());

    const bgUrl = Config.getConfig("theme.background");""",
    tag="A2 theme follow-system listener",
)

# ============================================================
# B. 开屏动画背景跟随深浅色：SplashScreenBackground 加深浅两套颜色
#    浅色 #fafafa（白），深色 #282828（灰）。Storyboard 用的是这个命名颜色，
#    加了 appearances 后系统会自动按当前外观选。
# ============================================================
replace(
    "ios/MusicFree/Images.xcassets/SplashScreenBackground.colorset/Contents.json",
    """{
  "colors" : [
    {
      "color" : {
        "color-space" : "srgb",
        "components" : {
          "alpha" : "1.000",
          "blue" : "40",
          "green" : "40",
          "red" : "40"
        }
      },
      "idiom" : "universal"
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}""",
    """{
  "colors" : [
    {
      "color" : {
        "color-space" : "srgb",
        "components" : {
          "alpha" : "1.000",
          "blue" : "250",
          "green" : "250",
          "red" : "250"
        }
      },
      "idiom" : "universal",
      "appearances" : [
        {
          "appearance" : "luminosity",
          "value" : "light"
        }
      ]
    },
    {
      "color" : {
        "color-space" : "srgb",
        "components" : {
          "alpha" : "1.000",
          "blue" : "40",
          "green" : "40",
          "red" : "40"
        }
      },
      "idiom" : "universal",
      "appearances" : [
        {
          "appearance" : "luminosity",
          "value" : "dark"
        }
      ]
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}""",
    tag="B splash light/dark colorset",
)

# ============================================================
# C. 底部安全区（黑条 / 灰条）—— iOS 上去掉
#    根因：VerticalSafeAreaView 用 SafeAreaView edges=["bottom"]，每页底部
#    都垫一块（Home Indicator 区）；面板 ScrollView 又拿 safeAreaInsets.bottom
#    当 marginBottom，面板底下就露出被遮罩变暗的页面＝灰条/黑条。
#    iOS 的小白条是悬浮在内容上的，不需要预留这块。只改 iOS，安卓不动。
# ============================================================
replace(
    "src/components/base/verticalSafeAreaView.tsx",
    """import React from "react";
import { StyleProp, ViewStyle } from "react-native";""",
    """import React from "react";
import { Platform, StyleProp, ViewStyle } from "react-native";""",
    tag="C1 VerticalSafeAreaView import Platform",
)
replace(
    "src/components/base/verticalSafeAreaView.tsx",
    """    const topInset = useStableTopInset();
    return (
        <SafeAreaView style={[style, { paddingTop: topInset }]} mode={mode} edges={["bottom"]}>""",
    """    const topInset = useStableTopInset();
    // iOS 不留底部安全区：Home Indicator 是悬浮在内容上的，预留
    // 就会在迷你播放条 / 面板底下留一条灰带（黑条）。安卓保留。
    return (
        <SafeAreaView style={[style, { paddingTop: topInset }]} mode={mode} edges={Platform.OS === "ios" ? [] : ["bottom"]}>""",
    tag="C2 VerticalSafeAreaView no bottom edge on iOS",
)
replace(
    "src/pages/searchPage/index.tsx",
    """        <SafeAreaView edges={["bottom"]} style={[style.wrapper, { paddingTop: topInset }]}>""",
    """        <SafeAreaView edges={[]} style={[style.wrapper, { paddingTop: topInset }]}>""",
    tag="C3 search page no bottom edge",
)
# 面板里所有 marginBottom / paddingBottom: safeAreaInsets.bottom -> 0（iOS 不留底边）
for _p in [
    "src/components/panels/types/addToMusicSheet.tsx",
    "src/components/panels/types/importMusicSheet.tsx",
    "src/components/panels/types/musicItemLyricOptions.tsx",
    "src/components/panels/types/musicQuality.tsx",
    "src/components/panels/types/playList/body.tsx",
    "src/components/panels/types/playRate.tsx",
    "src/components/panels/types/sheetTags.tsx",
    "src/components/panels/types/simpleSelect.tsx",
    "src/components/panels/types/musicItemOptions.tsx",
]:
    replace_re(
        _p,
        r"(marginBottom|paddingBottom): safeAreaInsets\.bottom",
        r"\1: 0",
        tag="C4 panel bottom inset -> 0",
    )
# panelBase：positionMethod="top" 时不要再减 safeAreaInsets.bottom
replace(
    "src/components/panels/base/panelBase.tsx",
    """                    top: positionMethod === "top" ? (Dimensions.get("window").height + safeAreaInsets.top) - height - safeAreaInsets.bottom : Dimensions.get("window").height - height,""",
    """                    top: positionMethod === "top" ? (Dimensions.get("window").height + safeAreaInsets.top) - height : Dimensions.get("window").height - height,""",
    tag="C5 panelBase top-method no bottom inset",
)

# ============================================================
# D. 面板点不开（倍速/音质/评论/三个点/加号）：KeyboardAvoidingView 默认包住
#    所有面板，iOS 上 behavior="position" 会把面板顶出屏幕，只剩遮罩变灰。
#    能正常打开的 PlayList / TimingClose 恰好都传了 keyboardAvoidBehavior="none"。
#    改成：不传就不包；真要包的（带输入框的）iOS 用 "padding" 不用 "position"。
# ============================================================
replace(
    "src/components/panels/base/panelBase.tsx",
    """            {keyboardAvoidBehavior === "none" ? (
                panelBody
            ) : (
                <KeyboardAvoidingView
                    style={style.kbContainer}
                    behavior={Platform.OS === "ios" ? 
                        orientation === "horizontal" ? keyboardAvoidBehavior: "position"
                        : ( keyboardAvoidBehavior || "position")}>
                    {panelBody}
                </KeyboardAvoidingView>
            )}""",
    """            {!keyboardAvoidBehavior || keyboardAvoidBehavior === "none" ? (
                panelBody
            ) : (
                <KeyboardAvoidingView
                    style={style.kbContainer}
                    behavior={Platform.OS === "ios" ?
                        orientation === "horizontal" ? keyboardAvoidBehavior : "padding"
                        : (keyboardAvoidBehavior || "padding")}>
                    {panelBody}
                </KeyboardAvoidingView>
            )}""",
    tag="D panelBase no KeyboardAvoidingView by default, padding on iOS",
)

# ============================================================
# E. 搜索点一下闪：useStableTopInset 初始 max 是 0，第一帧 top=0，
#    量出来 59 后才跳回去。先给一个 Dynamic Island 的初值 59，
#    之后量到更大的再往上记，永远不回落到 0。
# ============================================================
replace(
    "src/hooks/useStableTopInset.ts",
    """let maxTopInset = 0;""",
    """// 先给 Dynamic Island 的初值 59：第一帧 top 还没量出来时是 0，
    // 输入框会先贴到状态栏、量出来后再跳回正确位置（闪一下）。
    // 有了初值就不再从 0 起跳；量到更大的再往上记，永不回落。
    let maxTopInset = 59;""",
    tag="E stable top inset initial 59",
)

# ============================================================
# F. 迷你播放条改成悬浮胶囊（给以后液态玻璃准备；只改样式，不动 SDK）
#    满宽长方形 -> 左右留边、底部悬空、圆角=高的一半（胶囊）、加阴影。
# ============================================================
replace(
    "src/components/musicBar/index.tsx",
    """const style = StyleSheet.create({
    wrapper: {
        width: "100%",
        height: rpx(132),
        flexDirection: "row",
        alignItems: "center",
        paddingRight: rpx(24),
    },""",
    """const style = StyleSheet.create({
    wrapper: {
        // 悬浮胶囊：左右留边、底部悬空、圆角=高的一半。
        // 液态玻璃的底栏就是这种胶囊形（长方形套玻璃只是玻璃条，
        // 不是浮起来的胶囊）。先改形状，以后套玻璃材质直接就是胶囊。
        height: rpx(132),
        flexDirection: "row",
        alignItems: "center",
        paddingRight: rpx(24),
        marginHorizontal: rpx(24),
        marginBottom: rpx(12),
        borderRadius: rpx(66),
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 12,
        elevation: 8,
    },""",
    tag="F musicBar floating capsule",
)

print(f"part1 done: ok={len(SUCCESSES)} fail={len(FAILURES)}")
for f in FAILURES:
    print("FAIL:", f)

# ============================================================
# G. 灵动岛 / 锁屏歌词排版（用户给的文字版方案）
#    Good Time - Owl City            大字体（一行：歌名 - 歌手）
#    It's always a good time         大字体（当前句主歌词）
#    快乐时光永远都在                小字体（当前句翻译，同色只小字号）
#    Woah oh oh oh                   小字体（下一句主歌词）
#    哇哦哦哦                        更小字体（下一句翻译）
#    按钮（居中不动）
#    新增 currentLineTrans / nextLineTrans 两个字段。
# ============================================================

# ---- G1. Attributes.swift：ContentState 加两个翻译字段 ----
replace(
    "ios/MusicFreeWidgets/Attributes.swift",
    """        /// 当前歌词行（空字符串表示当前无歌词行）
        var currentLine: String
        /// 下一行歌词（可为空）
        var nextLine: String""",
    """        /// 当前歌词行（空字符串表示当前无歌词行）
        var currentLine: String
        /// 当前行翻译（中文；无翻译时为空字符串）
        var currentLineTrans: String
        /// 下一行歌词（可为空）
        var nextLine: String
        /// 下一行翻译（无翻译时为空字符串）
        var nextLineTrans: String""",
    tag="G1 Attributes add trans fields",
)
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """    static let contentState = LyricsLiveActivityAttributes.ContentState(
        currentLine: "故事的小黄花 从出生那年就飘着",
        nextLine: "童年的荡秋千 随记忆一直晃到现在",
        startedAt: Date(), duration: 269, isPlaying: true)""",
    """    static let contentState = LyricsLiveActivityAttributes.ContentState(
        currentLine: "故事的小黄花 从出生那年就飘着",
        currentLineTrans: "",
        nextLine: "童年的荡秋千 随记忆一直晃到现在",
        nextLineTrans: "",
        startedAt: Date(), duration: 269, isPlaying: true)""",
    tag="G1b preview contentState",
)

# ---- G2. Module.swift：start/update 接两个翻译字段 ----
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """        Function("startActivity") {
            (
                title: String,
                artist: String,
                currentLine: String,
                nextLine: String,
                startedAtMs: Double,
                durationSec: Double,
                isPlaying: Bool
            ) -> Bool in""",
    """        Function("startActivity") {
            (
                title: String,
                artist: String,
                currentLine: String,
                currentLineTrans: String,
                nextLine: String,
                nextLineTrans: String,
                startedAtMs: Double,
                durationSec: Double,
                isPlaying: Bool
            ) -> Bool in""",
    tag="G2a Module startActivity signature",
)
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    nextLine: nextLine,
                    startedAt: startedAt,
                    duration: max(durationSec, 0),
                    isPlaying: isPlaying
                )
                // 2 分钟后标记为过期：App 被杀掉后灵动岛很快消失；""",
    """                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    currentLineTrans: currentLineTrans,
                    nextLine: nextLine,
                    nextLineTrans: nextLineTrans,
                    startedAt: startedAt,
                    duration: max(durationSec, 0),
                    isPlaying: isPlaying
                )
                // 2 分钟后标记为过期：App 被杀掉后灵动岛很快消失；""",
    tag="G2b Module startActivity state",
)
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """        Function("updateActivity") {
            (
                currentLine: String,
                nextLine: String,
                startedAtMs: Double,
                durationSec: Double,
                isPlaying: Bool
            ) -> Void in""",
    """        Function("updateActivity") {
            (
                currentLine: String,
                currentLineTrans: String,
                nextLine: String,
                nextLineTrans: String,
                startedAtMs: Double,
                durationSec: Double,
                isPlaying: Bool
            ) -> Void in""",
    tag="G2c Module updateActivity signature",
)
replace(
    "ios/MusicFreeWidgets/Module.swift",
    """                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    nextLine: nextLine,
                    startedAt: startedAt,
                    duration: max(durationSec, 0),
                    isPlaying: isPlaying
                )
                // 更新也带 2 分钟过期时间：App 被杀掉后不再更新，""",
    """                let contentState = LyricsLiveActivityAttributes.ContentState(
                    currentLine: currentLine,
                    currentLineTrans: currentLineTrans,
                    nextLine: nextLine,
                    nextLineTrans: nextLineTrans,
                    startedAt: startedAt,
                    duration: max(durationSec, 0),
                    isPlaying: isPlaying
                )
                // 更新也带 2 分钟过期时间：App 被杀掉后不再更新，""",
    tag="G2d Module updateActivity state",
)

# ---- G3. LyricsLiveActivity.swift：锁屏 + 灵动岛排版 ----
# 锁屏横幅：歌名-歌手并成一行大字；当前句 20pt；翻译 14pt 同色；下一句 13pt 灰；
# 下一句翻译 11pt 灰。视图树固定（四个歌词 Text 一直渲染，空串自动塌掉），
# 行变化只换字符串，不闪。
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """            // MARK: - 锁屏横幅
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(context.attributes.title)
                        .font(.system(size: 14, weight: .bold))
                        .lineLimit(1)
                    Text(context.attributes.artist)
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Text(context.state.currentLine)
                    .font(.system(size: 18, weight: .semibold))
                    .lineLimit(2)
                Text(context.state.nextLine)
                    .font(.system(size: 13))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)""",
    """            // MARK: - 锁屏横幅
            // 排版：歌名 - 歌手一行大字；当前句 20pt 白；翻译 14pt 同色；
            // 下一句 13pt 灰；下一句翻译 11pt 灰；按钮居中。
            VStack(alignment: .leading, spacing: 4) {
                Text("\\(context.attributes.title) - \\(context.attributes.artist)")
                    .font(.system(size: 16, weight: .bold))
                    .lineLimit(1)
                Text(context.state.currentLine)
                    .font(.system(size: 20, weight: .semibold))
                    .lineLimit(2)
                Text(context.state.currentLineTrans)
                    .font(.system(size: 14))
                    .lineLimit(1)
                Text(context.state.nextLine)
                    .font(.system(size: 13))
                    .foregroundStyle(.secondary)
                    .opacity(0.75)
                    .lineLimit(1)
                Text(context.state.nextLineTrans)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .opacity(0.65)
                    .lineLimit(1)""",
    tag="G3a lock screen layout",
)
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.attributes.title)
                            .font(.system(size: 14, weight: .bold))
                            .lineLimit(1)
                        Text(context.attributes.artist)
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }""",
    """            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text("\\(context.attributes.title) - \\(context.attributes.artist)")
                        .font(.system(size: 17, weight: .bold))
                        .lineLimit(1)
                }""",
    tag="G3b island leading title-artist one line",
)
replace(
    "ios/MusicFreeWidgets/LyricsLiveActivity.swift",
    """                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.state.currentLine)
                            .font(.system(size: 16, weight: .semibold))
                            .lineLimit(2)
                        Text(context.state.nextLine)
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)""",
    """                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.state.currentLine)
                            .font(.system(size: 20, weight: .semibold))
                            .lineLimit(2)
                        Text(context.state.currentLineTrans)
                            .font(.system(size: 14))
                            .lineLimit(1)
                        Text(context.state.nextLine)
                            .font(.system(size: 13))
                            .foregroundStyle(.secondary)
                            .opacity(0.75)
                            .lineLimit(1)
                        Text(context.state.nextLineTrans)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                            .opacity(0.65)
                            .lineLimit(1)""",
    tag="G3c island bottom lyric layout",
)

print(f"part2 done: ok={len(SUCCESSES)} fail={len(FAILURES)}")
for f in FAILURES:
    print("FAIL:", f)

# ============================================================
# H. JS 侧：歌词主句/翻译拆分 + Live Activity 桥接（4 个字段）
# ============================================================

# ---- H1. liveActivityLyrics.ts：接口 + splitLyricLine ----
replace(
    "src/core/liveActivityLyrics.ts",
    """interface IWidgetExtensionModule {
    areActivitiesEnabled: () => boolean;
    startActivity: (
        title: string,
        artist: string,
        currentLine: string,
        nextLine: string,
        startedAtMs: number,
        durationSec: number,
        isPlaying: boolean,
    ) => boolean;
    updateActivity: (
        currentLine: string,
        nextLine: string,
        startedAtMs: number,
        durationSec: number,
        isPlaying: boolean,
    ) => void;
    endActivity: () => void;
}""",
    """interface IWidgetExtensionModule {
    areActivitiesEnabled: () => boolean;
    startActivity: (
        title: string,
        artist: string,
        currentLine: string,
        currentLineTrans: string,
        nextLine: string,
        nextLineTrans: string,
        startedAtMs: number,
        durationSec: number,
        isPlaying: boolean,
    ) => boolean;
    updateActivity: (
        currentLine: string,
        currentLineTrans: string,
        nextLine: string,
        nextLineTrans: string,
        startedAtMs: number,
        durationSec: number,
        isPlaying: boolean,
    ) => void;
    endActivity: () => void;
}

/**
 * 把一行歌词拆成主句 + 翻译。
 * 有独立 translation 字段的直接用；没有的（一行里英文+中文混着，
 * 如 "It's always a good time 快乐时光永远都在"）按首个中文字符切开。
 * 纯中文歌（无英文主句）不拆，原样返回。
 */
export function splitLyricLine(
    line: string,
    translation?: string | null,
): { main: string; trans: string } {
    if (translation) {
        return { main: line ?? "", trans: translation };
    }
    const text = line ?? "";
    const chars = [...text];
    const idx = chars.findIndex(ch => /[\\u4e00-\\u9fff]/.test(ch));
    if (idx <= 0) {
        return { main: text, trans: "" };
    }
    return {
        main: chars.slice(0, idx).join("").trim(),
        trans: chars.slice(idx).join("").trim(),
    };
}""",
    tag="H1a liveActivity interface + splitLyricLine",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """export function startLyricsLiveActivity(
    title: string,
    artist: string,
    currentLine: string,
    nextLine: string,
    startedAtMs: number,
    durationSec: number,
    isPlaying: boolean,
): void {
    const mod = getModule();
    if (!mod) {
        return;
    }
    try {
        // 原生返回 true 才算真的启动成功；返回 false 说明
        // Activity.request 失败，下次行变化会重新 start，不卡死。
        const ok = mod.startActivity(
            title,
            artist,
            truncate(currentLine),
            truncate(nextLine),
            startedAtMs,
            Math.max(durationSec, 0),
            isPlaying,
        );""",
    """export function startLyricsLiveActivity(
    title: string,
    artist: string,
    currentLine: string,
    currentLineTrans: string,
    nextLine: string,
    nextLineTrans: string,
    startedAtMs: number,
    durationSec: number,
    isPlaying: boolean,
): void {
    const mod = getModule();
    if (!mod) {
        return;
    }
    try {
        // 原生返回 true 才算真的启动成功；返回 false 说明
        // Activity.request 失败，下次行变化会重新 start，不卡死。
        const ok = mod.startActivity(
            title,
            artist,
            truncate(currentLine),
            truncate(currentLineTrans),
            truncate(nextLine),
            truncate(nextLineTrans),
            startedAtMs,
            Math.max(durationSec, 0),
            isPlaying,
        );""",
    tag="H1b startLyricsLiveActivity 4 fields",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """export function updateLyricsLiveActivity(
    currentLine: string,
    nextLine: string,
    startedAtMs: number,
    durationSec: number,
    isPlaying: boolean,
): void {""",
    """export function updateLyricsLiveActivity(
    currentLine: string,
    currentLineTrans: string,
    nextLine: string,
    nextLineTrans: string,
    startedAtMs: number,
    durationSec: number,
    isPlaying: boolean,
): void {""",
    tag="H1c updateLyricsLiveActivity 4 fields",
)
replace(
    "src/core/liveActivityLyrics.ts",
    """        mod.updateActivity(
            truncate(currentLine),
            truncate(nextLine),
            startedAtMs,
            Math.max(durationSec, 0),
            isPlaying,
        );""",
    """        mod.updateActivity(
            truncate(currentLine),
            truncate(currentLineTrans),
            truncate(nextLine),
            truncate(nextLineTrans),
            startedAtMs,
            Math.max(durationSec, 0),
            isPlaying,
        );""",
    tag="H1d updateActivity call 4 fields",
)

# ---- H2. lyricManager.ts：syncLiveActivity 拆主句/翻译；播完暂停就收岛 ----
replace(
    "src/core/lyricManager.ts",
    """        const showTranslation = PersistStatus.get("lyric.showTranslation");
        const formatLine = (item: IParsedLrcItem | null | undefined) =>
            (item?.lrc ?? "") +
            (showTranslation && item?.translation
                ? `\\n${item.translation}`
                : "");

        const currentLine = formatLine(currentLyricItem);
        const items = this.lyricParser?.getLyricItems() ?? [];
        const nextLine = formatLine(items[currentLyricItem.index + 1]);""",
    """        const showTranslation = PersistStatus.get("lyric.showTranslation");
        // 主句 / 翻译分开传给灵动岛（岛上分两行、不同字号显示）。
        // 有独立 translation 字段的直接用；没有的按首个中文字符切。
        const splitItem = (item: IParsedLrcItem | null | undefined) => {
            const lrc = item?.lrc ?? "";
            const trans = showTranslation ? (item?.translation ?? null) : null;
            if (trans) {
                return { main: lrc, trans };
            }
            const chars = [...lrc];
            const idx = chars.findIndex(ch => /[\\u4e00-\\u9fff]/.test(ch));
            if (idx <= 0) {
                return { main: lrc, trans: "" };
            }
            return {
                main: chars.slice(0, idx).join("").trim(),
                trans: chars.slice(idx).join("").trim(),
            };
        };

        const cur = splitItem(currentLyricItem);
        const items = this.lyricParser?.getLyricItems() ?? [];
        const nxt = splitItem(items[currentLyricItem.index + 1]);
        const currentLine = cur.main;
        const currentLineTrans = cur.trans;
        const nextLine = nxt.main;
        const nextLineTrans = nxt.trans;""",
    tag="H2a lyricManager split main/trans",
)
replace(
    "src/core/lyricManager.ts",
    """        startLyricsLiveActivity(
            musicItem.title,
            musicItem.artist,
            currentLine,
            nextLine,
            startedAtMs,
            durationSec,
            this.lastPlaybackPlaying,
        );""",
    """        startLyricsLiveActivity(
            musicItem.title,
            musicItem.artist,
            currentLine,
            currentLineTrans,
            nextLine,
            nextLineTrans,
            startedAtMs,
            durationSec,
            this.lastPlaybackPlaying,
        );""",
    tag="H2b lyricManager start call 4 fields",
)
# 播完暂停（进度走到时长末尾、状态变 Paused）就收岛：之前只有 Stopped /
# QueueEnded 才收，歌放完停在末尾变 Paused 时岛一直留着。
replace(
    "src/core/lyricManager.ts",
    """            } else if (state === State.Paused) {
                this.lastPlaybackPlaying = false;
                this.syncLiveActivity();
            }""",
    """            } else if (state === State.Paused) {
                this.lastPlaybackPlaying = false;
                // 暂停在曲末（进度已到时长）：这首已经播完，不是中途暂停，
                // 岛留着就是“没播也有歌词条”。直接收掉；中途暂停不受影响。
                const pos = this.lastProgress.position || 0;
                const dur = this.lastProgress.duration || 0;
                if (dur > 0 && pos >= dur - 1.5) {
                    endLyricsLiveActivity();
                    return;
                }
                this.syncLiveActivity();
            }""",
    tag="H2c lyricManager end on paused-at-end",
)

# ---- H3. headless service：拆主句/翻译；5 秒轮询防歌词卡住；播完收岛 ----
replace(
    "src/service/index.ts",
    """import {
    endLyricsLiveActivity,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";""",
    """import {
    endLyricsLiveActivity,
    splitLyricLine,
    startLyricsLiveActivity,
} from "@/core/liveActivityLyrics";""",
    tag="H3a headless import splitLyricLine",
)
replace(
    "src/service/index.ts",
    """            const line = current.lrc ?? "";
            const now = Date.now();
            const lineChanged = !!line && line !== lastHeadlessLyricLine;
            const heartbeatDue =
                now - lastHeadlessPushTime >= HEADLESS_HEARTBEAT_MS;
            if (!line || (!lineChanged && !heartbeatDue)) {
                return;
            }
            lastHeadlessLyricLine = line;
            lastHeadlessPushTime = now;
            const idx = items.indexOf(current);
            const next = items[idx + 1]?.lrc ?? "";
            // 走 start：原生侧已有活动就更新，没有就新建，
            // 后台也能把岛拉起来，不依赖主线程。
            startLyricsLiveActivity(
                data.title ?? "",
                data.artist ?? "",
                line,
                next,
                Date.now() - position * 1000,
                duration,
                true,
            );""",
    """            const cur = splitLyricLine(current.lrc ?? "", current.translation ?? null);
            const line = cur.main;
            const now = Date.now();
            const lineChanged = !!line && line !== lastHeadlessLyricLine;
            const heartbeatDue =
                now - lastHeadlessPushTime >= HEADLESS_HEARTBEAT_MS;
            if (!line || (!lineChanged && !heartbeatDue)) {
                return;
            }
            lastHeadlessLyricLine = line;
            lastHeadlessPushTime = now;
            const idx = items.indexOf(current);
            const nextItem = items[idx + 1];
            const nxt = splitLyricLine(nextItem?.lrc ?? "", nextItem?.translation ?? null);
            // 走 start：原生侧已有活动就更新，没有就新建，
            // 后台也能把岛拉起来，不依赖主线程。
            startLyricsLiveActivity(
                data.title ?? "",
                data.artist ?? "",
                line,
                cur.trans,
                nxt.main,
                nxt.trans,
                Date.now() - position * 1000,
                duration,
                true,
            );""",
    tag="H3b headless split main/trans",
)
replace(
    "src/service/index.ts",
    """    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
        headlessSyncLyric(evt.position ?? 0, evt.duration ?? 0);
    });""",
    """    RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, evt => {
        PersistStatus.set("music.progress", evt.position);
        headlessSyncLyric(evt.position ?? 0, evt.duration ?? 0);
    });

    // 歌词 30 秒后卡住不动的兜底：锁屏/后台时进度事件可能停发，
    // 歌词行就再也不更新（进度条是定时器自己走的，所以还在动）。
    // 每 5 秒主动拿一次真实进度重算当前行，事件停了也能继续推。
    setInterval(async () => {
        try {
            const { position, duration } = await RNTrackPlayer.getProgress();
            headlessSyncLyric(position ?? 0, duration ?? 0);
        } catch {}
    }, 5000);""",
    tag="H3c headless 5s poll",
)
replace(
    "src/service/index.ts",
    """    // 播完 / 队列结束：后台也收掉灵动岛，不然锁屏留一首卡在最后的歌。
    RNTrackPlayer.addEventListener(Event.PlaybackState, ({ state }) => {
        if (state === State.Stopped) {
            lastHeadlessLyricLine = "";
            endLyricsLiveActivity();
        }
    });""",
    """    // 播完 / 队列结束：后台也收掉灵动岛，不然锁屏留一首卡在最后的歌。
    RNTrackPlayer.addEventListener(Event.PlaybackState, async ({ state }) => {
        if (state === State.Stopped) {
            lastHeadlessLyricLine = "";
            endLyricsLiveActivity();
        } else if (state === State.Paused) {
            // 暂停在曲末＝播完：收岛；中途暂停不收（点播放可恢复）。
            try {
                const { position, duration } = await RNTrackPlayer.getProgress();
                if (duration > 0 && position >= duration - 1.5) {
                    lastHeadlessLyricLine = "";
                    endLyricsLiveActivity();
                }
            } catch {}
        }
    });""",
    tag="H3d headless end on paused-at-end",
)

# ---- H4. 软件内歌词页：唱到的那句放大提亮，上下句缩小变淡 ----
replace(
    "src/pages/musicDetail/components/content/lyric/lyricItem.tsx",
    """            style={[
                lyricStyles.item,
                { color: colors.text },
                {
                    fontSize: fontSize || fontSizeConst.content,
                },
                highlight
                    ? [
                        lyricStyles.highlightItem,
                        {
                            color: colors.primary,
                        },
                    ]
                    : null,
                light ? lyricStyles.draggingItem : null,
            ]}>""",
    """            style={[
                lyricStyles.item,
                { color: colors.text },
                {
                    // 唱到的那句放大（×1.25）提亮；上下句保持原大小、透明度 0.6 变淡。
                    fontSize: highlight
                        ? (fontSize || fontSizeConst.content) * 1.25
                        : (fontSize || fontSizeConst.content),
                },
                highlight
                    ? [
                        lyricStyles.highlightItem,
                        {
                            color: colors.primary,
                        },
                    ]
                    : null,
                light ? lyricStyles.draggingItem : null,
            ]}>""",
    tag="H4 lyric page current line bigger",
)

print(f"part3 done: ok={len(SUCCESSES)} fail={len(FAILURES)}")
for f in FAILURES:
    print("FAIL:", f)

# ============================================================
# I. 下载：先选位置，再下载（用户要的顺序）
#    现在是先下到 App 目录、再弹管理器；取消也提示成功、文件还留在 App 目录。
#    改成：点下载 -> 先弹 Files 保存框（占位空文件）-> 点保存才开始下；
#    取消就什么都不下、不提示成功。FileSaver 返回目标 URL（原来只回布尔值），
#    再加一个 copyFileToURL 把下好的文件写进用户选的位置（覆盖占位空文件）。
# ============================================================

# ---- I1. FileSaver.m：返回目标 URL + 新增 copyFileToURL ----
replace(
    "ios/FileSaver/FileSaver.m",
    """- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (_resolve) {
    _resolve(@(YES));
    _resolve = nil;
    _reject = nil;
  }
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller {
  if (_resolve) {
    _resolve(@(NO));
    _resolve = nil;
    _reject = nil;
  }
}""",
    """- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (_resolve) {
    // 返回用户选的目标位置（file:// URL 字符串），JS 拿到后把真正下好的
    // 文件写进去（覆盖刚才的占位空文件）。原来只回 YES，JS 不知道存哪了。
    NSURL *dest = urls.firstObject;
    _resolve(dest ? dest.absoluteString : @"");
    _resolve = nil;
    _reject = nil;
  }
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller {
  if (_resolve) {
    // 取消返回空串：JS 以此判断“用户没选位置”，直接不下载、不提示成功。
    _resolve(@"");
    _resolve = nil;
    _reject = nil;
  }
}

// 把已下载好的文件写进用户在保存框里选的位置（安全域 URL，需先取访问权）。
// destURLString 是 saveFile 返回的那个 file:// URL。
RCT_EXPORT_METHOD(copyFileToURL:(NSString *)sourcePath
                  destURLString:(NSString *)destURLString
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  dispatch_async(dispatch_get_main_queue(), ^{
    NSURL *destURL = [NSURL URLWithString:destURLString];
    if (!destURL || !sourcePath || ![[NSFileManager defaultManager] fileExistsAtPath:sourcePath]) {
      if (reject) reject(@"BAD_ARG", @"bad source or destination", nil);
      return;
    }
    BOOL access = [destURL startAccessingSecurityScopedResource];
    NSError *error = nil;
    NSFileManager *fm = [NSFileManager defaultManager];
    // 先删掉保存框当时拷过去的占位空文件，再拷真的文件进去。
    [fm removeItemAtURL:destURL error:nil];
    BOOL ok = [fm copyItemAtPath:sourcePath toURL:destURL error:&error];
    if (access) [destURL stopAccessingSecurityScopedResource];
    if (ok) {
      resolve(@(YES));
    } else {
      reject(@"COPY_FAIL", error.localizedDescription ?: @"copy failed", nil);
    }
  });
}""",
    tag="I1 FileSaver return dest URL + copyFileToURL",
)

# ---- I2. saveToFiles.ts：返回目标 URL（string|null），加 copyToPickedURL ----
replace(
    "src/utils/saveToFiles.ts",
    """import { NativeModules } from "react-native";

/**
 * 用苹果自带的文件管理器保存一个文件：弹出 UIDocumentPickerViewController
 *（导出模式），上面有 Save 按钮，下面有 Save as 文件名，用户自选目录。
 * 返回 true = 用户点了 Save，false = 取消 / 模块不可用 / 出错。
 * asCopy:YES，App 自己那份还在，不影响离线播放。
 */
export async function saveFileToFiles(filePath: string): Promise<boolean> {
    try {
        const mod = (NativeModules as Record<string, unknown>).FileSaver as
            | { saveFile?: (filePath: string) => Promise<boolean> }
            | undefined;
        if (!mod?.saveFile) {
            return false;
        }
        return !!(await mod.saveFile(filePath));
    } catch {
        return false;
    }
}""",
    """import { NativeModules } from "react-native";

type FileSaverModule = {
    saveFile?: (filePath: string) => Promise<string>;
    copyFileToURL?: (sourcePath: string, destURL: string) => Promise<boolean>;
};

/**
 * 用苹果自带的文件管理器保存一个文件：弹出 UIDocumentPickerViewController
 *（导出模式），上面有 Save 按钮，下面有 Save as 文件名，用户自选目录。
 * 返回用户选的目标位置（file:// URL 字符串）；取消 / 模块不可用 / 出错
 * 返回 null。调用方用返回值是否为空判断用户有没有点保存。
 * asCopy:YES，App 自己那份还在，不影响离线播放。
 */
export async function saveFileToFiles(filePath: string): Promise<string | null> {
    try {
        const mod = (NativeModules as Record<string, unknown>).FileSaver as
            | FileSaverModule
            | undefined;
        if (!mod?.saveFile) {
            return null;
        }
        const dest = await mod.saveFile(filePath);
        return dest ? dest : null;
    } catch {
        return null;
    }
}

/** 把已下载好的文件写进用户在保存框里选的位置（覆盖占位空文件）。 */
export async function copyFileToPickedURL(
    sourcePath: string,
    destURL: string,
): Promise<boolean> {
    try {
        const mod = (NativeModules as Record<string, unknown>).FileSaver as
            | FileSaverModule
            | undefined;
        if (!mod?.copyFileToURL) {
            return false;
        }
        return !!(await mod.copyFileToURL(sourcePath, destURL));
    } catch {
        return false;
    }
}""",
    tag="I2 saveToFiles return dest URL + copyToPickedURL",
)

# ---- I3. downloader.ts：先弹保存框（占位文件），用户点了保存才开始下载 ----
replace(
    "src/core/downloader.ts",
    """import { copyFile, downloadFile, exists, unlink } from "react-native-fs";""",
    """import { copyFile, downloadFile, exists, unlink, writeFile } from "react-native-fs";""",
    tag="I3a0 downloader import writeFile",
)
replace(
    "src/core/downloader.ts",
    """import { saveFileToFiles } from "@/utils/saveToFiles";""",
    """import { copyFileToPickedURL, saveFileToFiles } from "@/utils/saveToFiles";""",
    tag="I3a downloader import copyFileToPickedURL",
)
replace(
    "src/core/downloader.ts",
    """        // 下载
        const { promise } = downloadFile({""",
    """        // 先选位置，再下载：先弹 Files 保存框（拿一个同名占位空文件去弹，
        // 不然保存框没文件可存）。用户取消 -> 直接不下、不提示成功、不留文件；
        // 用户点了保存 -> 再开始下载，下完写进用户选的位置。
        const placeholderPath = this.getCacheDownloadPath(
            `${nextTask.filename}.${extension}`,
        );
        let pickedDestURL: string | null = null;
        try {
            await writeFile(placeholderPath, "", "utf8");
            pickedDestURL = await saveFileToFiles(placeholderPath);
        } catch {
            pickedDestURL = null;
        }
        if (!pickedDestURL) {
            // 用户取消了保存框：取消本次下载任务，不提示“下载成功”、不留文件。
            // 直接从任务表和队列里删掉（remove() 只删 Pending/Error 状态，
            // 现在是 Preparing，所以手动删），再把计数减回去、继续下一个任务。
            await unlink(placeholderPath).catch(() => {});
            downloadTasks.delete(getMediaUniqueKey(musicItem));
            const downloadQueue = getDefaultStore().get(downloadQueueAtom);
            const newDownloadQueue = downloadQueue.filter(
                item => !isSameMediaItem(item, musicItem),
            );
            getDefaultStore().set(downloadQueueAtom, newDownloadQueue);
            this.downloadingCount = Math.max(0, this.downloadingCount - 1);
            this.downloadNextPendingTask();
            return;
        }

        // 下载
        const { promise } = downloadFile({""",
    tag="I3b downloader picker-first",
)
replace(
    "src/core/downloader.ts",
    """            this.markTaskAsCompleted(musicItem);

            // 下完弹出苹果文件管理器（Save 按钮，自选目录）：
            // asCopy，App 自己那份还在 download/music/，离线播放不受影响。
            try {
                await saveFileToFiles(targetDownloadPath.replace(/^file:\\/\\//, ""));
            } catch {
                // 弹不出也不影响已下载的文件本身。
            }""",
    """            this.markTaskAsCompleted(musicItem);

            // 写进用户在保存框里选的位置（覆盖占位空文件）；
            // App 自己那份仍在 download/music/，离线播放不受影响。
            try {
                await copyFileToPickedURL(
                    targetDownloadPath.replace(/^file:\\/\\//, ""),
                    pickedDestURL,
                );
            } catch {
                // 写不进用户选的位置也不影响已下载的文件本身。
            }""",
    tag="I3c downloader write to picked dest",
)
replace(
    "src/core/downloader.ts",
    """        // 清理工作
        await unlink(cacheDownloadPath);
        this.downloadNextPendingTask();""",
    """        // 清理工作
        await unlink(cacheDownloadPath);
        await unlink(placeholderPath).catch(() => {});
        this.downloadNextPendingTask();""",
    tag="I3d downloader cleanup placeholder",
)

print(f"part4 done: ok={len(SUCCESSES)} fail={len(FAILURES)}")
for f in FAILURES:
    print("FAIL:", f)

# ============================================================
# J. 备份恢复不全：compare() 版本号异常会抛错，而跳过检查在 try/catch
#    外面，一个坏版本号就中断整个恢复（只恢复了前几条、速度还显得快）。
#    改成：跳过检查也包进 try/catch，坏版本当作没装过；安装失败重试一次。
# ============================================================
replace(
    "src/core/backup.ts",
    """    for (const _ of plugins ?? []) {
        // 校验是否安装过: 同源且本地版本更高就忽略掉
        if (
            validPlugins.find(
                plugin =>
                    plugin.instance.srcUrl === _.srcUrl &&
                    compare(
                        plugin.instance.version ?? "0.0.0",
                        _.version ?? "0.0.1",
                        ">=",
                    ),
            )
        ) {
            continue;
        }
        try {
            const result = await PluginManager.installPluginFromUrl(_.srcUrl);
            resumeResults.push({
                srcUrl: _.srcUrl,
                success: result.success,
                message: result.message,
            });
        } catch (e: any) {
            resumeResults.push({
                srcUrl: _.srcUrl,
                success: false,
                message: e?.message ?? String(e),
            });
        }
    }""",
    """    for (const _ of plugins ?? []) {
        // 校验是否安装过: 同源且本地版本更高就忽略掉。
        // compare() 碰到不规范版本号会抛错，之前这段在 try/catch 外面，
        // 一个坏版本就中断整个恢复（只恢复了前几条、速度还显得快）。
        let alreadyInstalled = false;
        try {
            alreadyInstalled = !!validPlugins.find(
                plugin =>
                    plugin.instance.srcUrl === _.srcUrl &&
                    compare(
                        plugin.instance.version ?? "0.0.0",
                        _.version ?? "0.0.1",
                        ">=",
                    ),
            );
        } catch {
            // 坏版本当作没装过，走正常安装流程（安装侧自己会判重）。
            alreadyInstalled = false;
        }
        if (alreadyInstalled) {
            continue;
        }
        // 安装失败重试一次（临时网络抖动很常见），两次都失败才记失败。
        let lastError: any = null;
        let installed = false;
        for (let attempt = 0; attempt < 2 && !installed; attempt++) {
            try {
                const result = await PluginManager.installPluginFromUrl(_.srcUrl);
                resumeResults.push({
                    srcUrl: _.srcUrl,
                    success: result.success,
                    message: result.message,
                });
                installed = true;
            } catch (e: any) {
                lastError = e;
            }
        }
        if (!installed) {
            resumeResults.push({
                srcUrl: _.srcUrl,
                success: false,
                message: lastError?.message ?? String(lastError),
            });
        }
    }""",
    tag="J backup resume robust + retry",
)

# ============================================================
# K. 诊断小窗：日志 + 图层 + 点按检测（用户要的“F12 元素检查”）
#    日志实时显示，错误标红；图层从底到顶列出每一层；点按检测点哪都告诉你是哪层。
# ============================================================

write_new(
    "src/core/appLogger.ts",
    '''/**
 * 诊断日志：拦截 console + 全局 JS 报错，存一个环形缓冲（最多 500 条），
 * 诊断面板实时显示，错误标红，一键复制。
 * 在 bootstrap 里最先 installAppLogger()，这样启动后的日志都能抓到。
 */
import { GlobalState } from "@/utils/stateMapper";

export type AppLogLevel = "log" | "info" | "warn" | "error";

export interface AppLogEntry {
    id: number;
    time: number;
    level: AppLogLevel;
    text: string;
}

const MAX_LOGS = 500;

let logs: AppLogEntry[] = [];
let nextId = 1;
let installed = false;

const logsStore = new GlobalState<AppLogEntry[]>([]);

function formatArg(arg: unknown): string {
    if (typeof arg === "string") {
        return arg;
    }
    try {
        return JSON.stringify(arg) ?? String(arg);
    } catch {
        return String(arg);
    }
}

function push(level: AppLogLevel, text: string) {
    logs.push({ id: nextId++, time: Date.now(), level, text });
    if (logs.length > MAX_LOGS) {
        logs = logs.slice(logs.length - MAX_LOGS);
    }
    logsStore.setValue([...logs]);
}

/** 在 bootstrap 最先调用。重复调用无害。 */
export function installAppLogger() {
    if (installed) {
        return;
    }
    installed = true;
    const origLog = console.log.bind(console);
    const origInfo = console.info.bind(console);
    const origWarn = console.warn.bind(console);
    const origError = console.error.bind(console);

    console.log = (...args: unknown[]) => {
        push("log", args.map(formatArg).join(" "));
        origLog(...args);
    };
    console.info = (...args: unknown[]) => {
        push("info", args.map(formatArg).join(" "));
        origInfo(...args);
    };
    console.warn = (...args: unknown[]) => {
        push("warn", args.map(formatArg).join(" "));
        origWarn(...args);
    };
    console.error = (...args: unknown[]) => {
        push("error", args.map(formatArg).join(" "));
        origError(...args);
    };

    try {
        const prevHandler = (global as any).ErrorUtils?.getGlobalHandler?.();
        (global as any).ErrorUtils?.setGlobalHandler?.(
            (err: any, isFatal?: boolean) => {
                push(
                    "error",
                    `[全局错误${isFatal ? "（致命）" : ""}] ${err?.message ?? String(err)}\\n${err?.stack ?? ""}`,
                );
                if (prevHandler) {
                    prevHandler(err, isFatal);
                }
            },
        );
    } catch {}
}

/** 供诊断面板订阅（实时刷新）。 */
export function useAppLogs() {
    return logsStore.useValue();
}

export function getAppLogs(): AppLogEntry[] {
    return [...logs];
}

export function clearAppLogs() {
    logs = [];
    logsStore.setValue([]);
}

/** 复制用的纯文本：时间 + 级别 + 内容。 */
export function appLogsToText(): string {
    return logs
        .map(e => {
            const d = new Date(e.time);
            const hh = String(d.getHours()).padStart(2, "0");
            const mm = String(d.getMinutes()).padStart(2, "0");
            const ss = String(d.getSeconds()).padStart(2, "0");
            return `[${hh}:${mm}:${ss}] [${e.level.toUpperCase()}] ${e.text}`;
        })
        .join("\\n");
}

export function appLog(level: AppLogLevel, text: string) {
    push(level, text);
}
''',
)

write_new(
    "src/components/panels/types/appDiagnostics.tsx",
    '''/**
 * 诊断小窗（用户要的“F12 元素检查”+ 日志）。
 * 两个页签：日志 / 图层。
 * 日志：实时滚动，错误红、警告橙，一键复制、清空。
 * 图层：从底到顶列出当前每一层（页面 / 迷你播放条 / 底部安全区 /
 * 面板遮罩 / 面板），带位置和大小，灰条在哪一层一眼看到。
 * 点按检测：打开后点屏幕任意处，直接告诉你点到的是哪一层。
 */
import React, { useMemo, useRef, useState } from "react";
import {
    Dimensions,
    Pressable,
    ScrollView,
    StyleSheet,
    View,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import rpx from "@/utils/rpx";
import ThemeText from "@/components/base/themeText";
import PanelBase from "../base/panelBase";
import PanelHeader from "../base/panelHeader";
import { hidePanel, panelInfoStore } from "../usePanel";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
    appLogsToText,
    clearAppLogs,
    useAppLogs,
    type AppLogEntry,
} from "@/core/appLogger";
import Toast from "@/utils/toast";
import TrackPlayer, { useCurrentMusic } from "@/core/trackPlayer";
import Divider from "@/components/base/divider";
import { useI18N } from "@/core/i18n";

const levelColor: Record<AppLogEntry["level"], string> = {
    log: "#888888",
    info: "#888888",
    warn: "#E8912D",
    error: "#E5484D",
};

function timeStr(t: number) {
    const d = new Date(t);
    const p = (n: number) => String(n).padStart(2, "0");
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

interface LayerInfo {
    name: string;
    frame: string;
    note: string;
}

export default function AppDiagnostics() {
    const { t } = useI18N();
    const logs = useAppLogs();
    const [tab, setTab] = useState<"logs" | "layers">("logs");
    const [inspecting, setInspecting] = useState(false);
    const [inspectResult, setInspectResult] = useState("");
    const insets = useSafeAreaInsets();
    const musicItem = useCurrentMusic();
    const panelInfo = panelInfoStore.useValue();
    const scrollRef = useRef<ScrollView>(null);

    const win = Dimensions.get("window");

    // 图层：从底到顶。面板开着时遮罩 + 面板在最上面；底部安全区是
    // 单独一层（iOS 已去掉留白，这里显示 0，方便确认黑条是不是它）。
    const layers = useMemo<LayerInfo[]>(() => {
        const list: LayerInfo[] = [];
        list.push({
            name: "页面（当前界面）",
            frame: `0, 0, ${Math.round(win.width)} x ${Math.round(win.height)}`,
            note: "最底层。歌单/详情/设置都在这一层。",
        });
        if (musicItem) {
            list.push({
                name: "迷你播放条（悬浮胶囊）",
                frame: `左右各留 ${Math.round(rpx(24))}，高 ${Math.round(rpx(132))}，底边距 ${Math.round(rpx(12))}`,
                note: "歌在播时才有。胶囊形，悬浮在页面上方。",
            });
        }
        list.push({
            name: "底部安全区",
            frame: `高 ${Math.round(insets.bottom)}（0 = 已去掉）`,
            note:
                insets.bottom > 0
                    ? "系统还报了一个底部安全区高度，内容被它顶起来就会留灰带。"
                    : "iOS 已去掉，内容贴到底边，Home Indicator 悬浮在上面。",
        });
        if (panelInfo.name) {
            list.push({
                name: "面板遮罩（变灰那层）",
                frame: `全屏，黑色 50% 透明`,
                note: "点任何面板按钮都会先出现它；只有它、没有面板内容 = 面板没弹出来。",
            });
            list.push({
                name: `面板：${panelInfo.name}`,
                frame: `底部弹出，宽 ${Math.round(win.width)}`,
                note: "最顶层。面板内容应该贴着屏幕底边，没有灰带。",
            });
        }
        return list;
    }, [win.width, win.height, insets.bottom, musicItem, panelInfo.name]);

    // 点按检测：按 Y 坐标判断点到哪一层（面板 > 安全区 > 迷你播放条 > 页面）。
    const inspectAt = (y: number) => {
        const h = win.height;
        let hit = "页面（当前界面）";
        if (musicItem && y >= h - insets.bottom - rpx(12) - rpx(132) && y < h - insets.bottom - rpx(12)) {
            hit = "迷你播放条（悬浮胶囊）";
        }
        if (insets.bottom > 0 && y >= h - insets.bottom) {
            hit = "底部安全区";
        }
        if (panelInfo.name) {
            // 面板从底边往上弹，点到底部区域就是面板或它的遮罩。
            hit = `面板：${panelInfo.name}（或它的遮罩）`;
        }
        const msg = `点到 (${Math.round(y)}px)：${hit}`;
        setInspectResult(msg);
        return msg;
    };

    const copyLogs = async () => {
        const text = appLogsToText();
        if (!text) {
            Toast.warn("暂无日志");
            return;
        }
        await Clipboard.setStringAsync(text);
        Toast.success("日志已复制");
    };

    return (
        <>
            <PanelBase
                height={rpx(1100)}
                renderBody={() => (
                    <>
                        <PanelHeader title="诊断" hideButtons />
                        <View style={style.tabRow}>
                            <Pressable
                                style={[style.tab, tab === "logs" && style.tabActive]}
                                onPress={() => setTab("logs")}>
                                <ThemeText>日志</ThemeText>
                            </Pressable>
                            <Pressable
                                style={[style.tab, tab === "layers" && style.tabActive]}
                                onPress={() => setTab("layers")}>
                                <ThemeText>图层</ThemeText>
                            </Pressable>
                        </View>
                        {tab === "logs" ? (
                            <>
                                <View style={style.btnRow}>
                                    <Pressable style={style.btn} onPress={copyLogs}>
                                        <ThemeText>复制日志</ThemeText>
                                    </Pressable>
                                    <Pressable
                                        style={style.btn}
                                        onPress={() => {
                                            clearAppLogs();
                                            Toast.success("已清空");
                                        }}>
                                        <ThemeText>清空</ThemeText>
                                    </Pressable>
                                </View>
                                <ScrollView
                                    ref={scrollRef}
                                    style={style.logList}
                                    onContentSizeChange={() =>
                                        scrollRef.current?.scrollToEnd({ animated: false })
                                    }>
                                    {logs.length === 0 ? (
                                        <ThemeText>暂无日志（操作一下 App 就会有）</ThemeText>
                                    ) : (
                                        logs.map(e => (
                                            <ThemeText
                                                key={e.id}
                                                style={[
                                                    style.logLine,
                                                    { color: levelColor[e.level] },
                                                ]}>
                                                {`[${timeStr(e.time)}] ${e.text}`}
                                            </ThemeText>
                                        ))
                                    )}
                                </ScrollView>
                            </>
                        ) : (
                            <ScrollView style={style.logList}>
                                <ThemeText style={style.layerHint}>
                                    从底到顶。灰条在哪一层，直接看它在哪一行。
                                </ThemeText>
                                <Divider />
                                {layers.map((l, i) => (
                                    <View key={i} style={style.layerRow}>
                                        <ThemeText fontWeight="bold">
                                            {`${i + 1}. ${l.name}`}
                                        </ThemeText>
                                        <ThemeText style={style.layerFrame}>{l.frame}</ThemeText>
                                        <ThemeText style={style.layerNote}>{l.note}</ThemeText>
                                    </View>
                                ))}
                                <Divider />
                                <Pressable
                                    style={[style.btn, inspecting && style.tabActive]}
                                    onPress={() => {
                                        setInspecting(v => !v);
                                        setInspectResult("");
                                    }}>
                                    <ThemeText>
                                        {inspecting ? "关闭点按检测" : "开启点按检测"}
                                    </ThemeText>
                                </Pressable>
                                {inspecting ? (
                                    <ThemeText style={style.layerHint}>
                                        已开启：点屏幕任意处，下面会显示点到的是哪一层。
                                    </ThemeText>
                                ) : null}
                                {inspectResult ? (
                                    <ThemeText style={style.inspectResult}>
                                        {inspectResult}
                                    </ThemeText>
                                ) : null}
                            </ScrollView>
                        )}
                    </>
                )}
            />
            {/* 点按检测遮罩：开启时盖在最上面，只负责取点坐标、报图层，
                不拦截面板本身的关闭（点遮罩空白处也会先报一层再关面板）。 */}
            {inspecting ? (
                <Pressable
                    style={style.inspectOverlay}
                    onPress={e => {
                        const y = (e.nativeEvent as any).pageY ?? (e.nativeEvent as any).locationY ?? 0;
                        inspectAt(y);
                    }}
                />
            ) : null}
        </>
    );
}

const style = StyleSheet.create({
    tabRow: {
        flexDirection: "row",
        paddingHorizontal: rpx(24),
        marginBottom: rpx(12),
    },
    tab: {
        paddingHorizontal: rpx(24),
        paddingVertical: rpx(12),
        marginRight: rpx(16),
        borderRadius: rpx(16),
    },
    tabActive: {
        backgroundColor: "rgba(0,0,0,0.08)",
    },
    btnRow: {
        flexDirection: "row",
        paddingHorizontal: rpx(24),
        marginBottom: rpx(12),
    },
    btn: {
        paddingHorizontal: rpx(24),
        paddingVertical: rpx(12),
        marginRight: rpx(16),
        borderRadius: rpx(16),
        backgroundColor: "rgba(0,0,0,0.08)",
    },
    logList: {
        flex: 1,
        paddingHorizontal: rpx(24),
        marginBottom: rpx(24),
    },
    logLine: {
        fontSize: 12,
        lineHeight: 18,
    },
    layerHint: {
        opacity: 0.7,
        marginVertical: rpx(12),
    },
    layerRow: {
        marginVertical: rpx(12),
    },
    layerFrame: {
        opacity: 0.7,
        fontSize: 12,
    },
    layerNote: {
        opacity: 0.7,
        fontSize: 12,
    },
    inspectResult: {
        marginTop: rpx(12),
        fontWeight: "bold",
    },
    inspectOverlay: {
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 20000,
    },
});
''',
)

# 注册诊断面板
replace(
    "src/components/panels/types/index.ts",
    """import EditMusicSheetInfo from "./editMusicSheetInfo";""",
    """import EditMusicSheetInfo from "./editMusicSheetInfo";
import AppDiagnostics from "./appDiagnostics";""",
    tag="K1 register AppDiagnostics import",
)
replace(
    "src/components/panels/types/index.ts",
    """    MusicItemLyricOptions,
    EditMusicSheetInfo,
};""",
    """    MusicItemLyricOptions,
    EditMusicSheetInfo,
    /** 诊断小窗：日志 + 图层 + 点按检测 */
    AppDiagnostics,
};""",
    tag="K2 register AppDiagnostics",
)

# bootstrap 最先装日志拦截（实际路径是 src/entry/bootstrap/bootstrap.ts）
replace(
    "src/entry/bootstrap/bootstrap.ts",
    """import TrackPlayer from "@/core/trackPlayer";""",
    """import TrackPlayer from "@/core/trackPlayer";
import { installAppLogger } from "@/core/appLogger";""",
    tag="K3 bootstrap import appLogger",
)
replace(
    "src/entry/bootstrap/bootstrap.ts",
    """async function bootstrapImpl() {
    const logger = perfLogger();""",
    """async function bootstrapImpl() {
    // 诊断日志最先装：拦截 console + 全局报错，诊断面板实时看。
    installAppLogger();
    const logger = perfLogger();""",
    tag="K3b bootstrap installAppLogger call",
)

# 诊断入口：关于页加一行“诊断日志”，点开诊断小窗
replace(
    "src/pages/setting/settingTypes/aboutSetting.tsx",
    """import Divider from "@/components/base/divider";""",
    """import Divider from "@/components/base/divider";
import { showPanel } from "@/components/panels/usePanel";""",
    tag="K4 about import showPanel",
)
replace(
    "src/pages/setting/settingTypes/aboutSetting.tsx",
    """                <ThemeText fontSize="title">开发者的话: </ThemeText>""",
    """                <TouchableOpacity
                    onPress={() => showPanel("AppDiagnostics")}
                    style={{ marginVertical: rpx(16) }}>
                    <ThemeText fontWeight="bold">诊断日志 / 图层检查 →</ThemeText>
                    <ThemeText style={style.content}>
                        看实时日志（错误标红）、一键复制；图层页从底到顶列出每一层，
                        点按检测点哪都告诉你是哪一层，黑条灰条在哪一层一眼看到。
                    </ThemeText>
                </TouchableOpacity>
                <Divider style={style.content} />
                <ThemeText fontSize="title">开发者的话: </ThemeText>""",
    tag="K5 about diagnostics entry",
)

print(f"part5 done: ok={len(SUCCESSES)} fail={len(FAILURES)}")
for f in FAILURES:
    print("FAIL:", f)

# ============================================================
# 汇总并退出
# ============================================================
print("=" * 60)
print(f"fix-run58: ok={len(SUCCESSES)} fail={len(FAILURES)}")
for s in SUCCESSES:
    print("  OK:", s)
if FAILURES:
    print("--- FAILURES ---")
    for f in FAILURES:
        print("  FAIL:", f)
    sys.exit(1)
print("ALL OK")
