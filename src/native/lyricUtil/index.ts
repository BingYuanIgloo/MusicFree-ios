import Config from "@/core/appConfig";
import Toast from "@/utils/toast";
import { NativeModule, NativeModules } from "react-native";
import { errorLog } from "@/utils/log.ts";

export enum NativeTextAlignment {
    // 左对齐
    LEFT = 3,
    // 右对齐
    RIGHT = 5,
    // 居中
    CENTER = 17,
}

// 状态栏歌词的工具
interface ILyricUtil extends NativeModule {
    /** 显示状态栏歌词 */
    showStatusBarLyric: (
        initLyric?: string,
        config?: Record<string, any>,
    ) => Promise<void>;
    /** 隐藏状态栏歌词 */
    hideStatusBarLyric: () => Promise<void>;
    /** 设置歌词文本 */
    setStatusBarLyricText: (lyric: string) => Promise<void>;
    /** 设置距离顶部的距离 */
    setStatusBarLyricTop: (percent: number) => Promise<void>;
    /** 设置距离左部的距离 */
    setStatusBarLyricLeft: (percent: number) => Promise<void>;
    /** 设置宽度 */
    setStatusBarLyricWidth: (percent: number) => Promise<void>;
    /** 设置字体 */
    setStatusBarLyricFontSize: (fontSize: number) => Promise<void>;
    /** 设置对齐 */
    setStatusBarLyricAlign: (alignment: NativeTextAlignment) => Promise<void>;
    /** 设置颜色 */
    setStatusBarColors: (
        textColor: string | null,
        backgroundColor: string | null,
    ) => Promise<void>;
    /** 检查权限 */
    checkSystemAlertPermission: () => Promise<boolean>;
    /** 请求悬浮窗 */
    requestSystemAlertPermission: () => Promise<boolean>;
}

const LyricUtil: ILyricUtil = NativeModules.LyricUtil || {};

// iOS 没有 LyricUtil 原生模块：缺失的方法用空实现代替，避免调用 undefined 抛错。
// 桌面歌词是安卓悬浮窗功能，iOS 上无对应 API（真正的替代是灵动岛歌词，另行实现）。
const noopAsync = async (): Promise<void> => {};
const noopAsyncFalse = async (): Promise<boolean> => false;
if (!LyricUtil.checkSystemAlertPermission) {
    LyricUtil.checkSystemAlertPermission = noopAsyncFalse;
}
if (!LyricUtil.requestSystemAlertPermission) {
    LyricUtil.requestSystemAlertPermission = noopAsyncFalse;
}
if (!LyricUtil.showStatusBarLyric) {
    LyricUtil.showStatusBarLyric = noopAsync;
}
if (!LyricUtil.hideStatusBarLyric) {
    LyricUtil.hideStatusBarLyric = noopAsync;
}
if (!LyricUtil.setStatusBarLyricText) {
    LyricUtil.setStatusBarLyricText = noopAsync;
}
if (!LyricUtil.setStatusBarLyricTop) {
    LyricUtil.setStatusBarLyricTop = noopAsync;
}
if (!LyricUtil.setStatusBarLyricLeft) {
    LyricUtil.setStatusBarLyricLeft = noopAsync;
}
if (!LyricUtil.setStatusBarLyricWidth) {
    LyricUtil.setStatusBarLyricWidth = noopAsync;
}
if (!LyricUtil.setStatusBarLyricFontSize) {
    LyricUtil.setStatusBarLyricFontSize = noopAsync;
}
if (!LyricUtil.setStatusBarLyricAlign) {
    LyricUtil.setStatusBarLyricAlign = noopAsync;
}
if (!LyricUtil.setStatusBarColors) {
    LyricUtil.setStatusBarColors = noopAsync;
}

const originalShowStatusBarLyric = LyricUtil.showStatusBarLyric;

const showStatusBarLyric: ILyricUtil["showStatusBarLyric"] = async (
    initLyric,
    config,
) => {
    try {
        await originalShowStatusBarLyric(initLyric, config);
    } catch (e) {
        errorLog("状态栏歌词开启失败", e);
        Toast.warn("状态栏歌词开启失败，请到手机系统设置打开悬浮窗权限");
        Config.setConfig("lyric.showStatusBarLyric", false);
    }
};

LyricUtil.showStatusBarLyric = showStatusBarLyric;

export default LyricUtil;
