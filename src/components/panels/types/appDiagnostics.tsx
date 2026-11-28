/**
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
