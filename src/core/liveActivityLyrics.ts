import { requireOptionalNativeModule } from "expo-modules-core";
import { NativeModules } from "react-native";

/**
 * 灵动岛歌词（Live Activity）的 JS 桥。
 *
 * 不直接 import "react-native-widget-extension"：那个包还没进
 * package.json（yarn.lock 暂时加不进它的 @expo/config-plugins
 * 依赖树，见任务报告），静态 import 会让 Metro 打包直接失败。
 * 这里改用 expo-modules-core（expo 的传递依赖，随 expo 一定装上）
 * 按名字找原生模块 ReactNativeWidgetExtension，找不到就静默 no-op，
 * App 不会因此崩掉。原生模块一旦编进包（pod + Module.swift），
 * 这里立刻就能用，不用再改 JS。
 *
 * 原生侧约定见 ios/MusicFreeWidgets/Module.swift：
 *   areActivitiesEnabled() -> Bool
 *   startActivity(title, artist, currentLine, nextLine, startedAtMs, durationSec, isPlaying)
 *   updateActivity(currentLine, nextLine, startedAtMs, durationSec, isPlaying)
 *   endActivity()
 *
 * 调用节奏：只在歌词行变化时 update（iOS 18 起应用内更新会被
 * 节流到约 5–15 秒一次，逐行推已经是最省的打法）；切歌时
 * start，播完 / 无歌词 / 关掉开关时 end。
 * 4 KB 上限：每行截到 150 字，只传文字不传图。
 */

interface IWidgetExtensionModule {
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
    const idx = chars.findIndex(ch => /[\u4e00-\u9fff]/.test(ch));
    if (idx <= 0) {
        return { main: text, trans: "" };
    }
    return {
        main: chars.slice(0, idx).join("").trim(),
        trans: chars.slice(idx).join("").trim(),
    };
}

const MAX_LINE_LENGTH = 150;

let cachedModule: IWidgetExtensionModule | null | undefined;

function getModule(): IWidgetExtensionModule | null {
    if (cachedModule !== undefined) {
        return cachedModule;
    }
    try {
        cachedModule =
            requireOptionalNativeModule<IWidgetExtensionModule>(
                "ReactNativeWidgetExtension",
            ) ?? null;
    } catch {
        cachedModule = null;
    }
    // 后台 headless 任务里 Expo 的模块注册表不一定可用，
    // requireOptionalNativeModule 会返回 null，导致后台歌词
    // 同步静默失败（歌词卡住、只在切回前台才刷新）。
    // 退到经典 NativeModules 桥：原生模块在 headless 任务里
    // 同样注册着，可以直接拿到。
    if (!cachedModule) {
        try {
            const nm = (NativeModules as Record<string, unknown>)
                .ReactNativeWidgetExtension as
                | IWidgetExtensionModule
                | undefined;
            cachedModule = nm ?? null;
        } catch {
            cachedModule = null;
        }
    }
    return cachedModule;
}

/** 原生模块是否存在（包已装 + pod 已编进）。不存在时所有调用都是 no-op。 */
export function isLiveActivityModuleAvailable(): boolean {
    return getModule() !== null;
}

/** 用户有没有在系统设置里关掉 Live Activities。模块缺失时返回 false。 */
export function areLyricsLiveActivitiesEnabled(): boolean {
    try {
        return getModule()?.areActivitiesEnabled() ?? false;
    } catch {
        return false;
    }
}

let activityActive = false;
let lastSentLine = "";
let lastSentIsPlaying = false;

function truncate(line: string): string {
    return line.length > MAX_LINE_LENGTH
        ? line.slice(0, MAX_LINE_LENGTH)
        : line;
}

export function startLyricsLiveActivity(
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
        );
        if (ok) {
            activityActive = true;
            lastSentLine = currentLine;
            lastSentIsPlaying = isPlaying;
        } else {
            activityActive = false;
        }
    } catch {
        activityActive = false;
    }
}

export function updateLyricsLiveActivity(
    currentLine: string,
    currentLineTrans: string,
    nextLine: string,
    nextLineTrans: string,
    startedAtMs: number,
    durationSec: number,
    isPlaying: boolean,
): void {
    // 行和播放状态都没变就不推：同一行重复 update 纯属浪费更新预算。
    // 只翻播放 / 暂停时，行不变但图标要变，必须推。
    if (
        activityActive &&
        currentLine === lastSentLine &&
        isPlaying === lastSentIsPlaying
    ) {
        return;
    }
    const mod = getModule();
    if (!mod) {
        return;
    }
    try {
        if (!activityActive) {
            // 活动还没开（例如 App 启动时歌已在播）：这次 update
            // 当作 start 用不上——调用方应先 start；这里直接丢弃，
            // 避免无标题的半个活动出现在岛上。
            return;
        }
        mod.updateActivity(
            truncate(currentLine),
            truncate(currentLineTrans),
            truncate(nextLine),
            truncate(nextLineTrans),
            startedAtMs,
            Math.max(durationSec, 0),
            isPlaying,
        );
        lastSentLine = currentLine;
        lastSentIsPlaying = isPlaying;
    } catch {
        activityActive = false;
    }
}

export function endLyricsLiveActivity(): void {
    const mod = getModule();
    if (!mod) {
        activityActive = false;
        lastSentLine = "";
        lastSentIsPlaying = false;
        return;
    }
    try {
        mod.endActivity();
    } catch {
        // 结束失败也无所谓：活动最多 8 小时，系统会自己收掉。
    } finally {
        activityActive = false;
        lastSentLine = "";
        lastSentIsPlaying = false;
    }
}
/** 当前有没有在跑的歌词活动（JS 侧记录的状态）。 */
export function isLyricsLiveActivityActive(): boolean {
    return activityActive;
}
