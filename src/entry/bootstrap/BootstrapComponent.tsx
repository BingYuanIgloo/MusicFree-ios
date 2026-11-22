import { useAppConfig } from "@/core/appConfig";
import Theme from "@/core/theme";
import useCheckUpdate from "@/hooks/useCheckUpdate";
import { useListenOrientationChange } from "@/hooks/useOrientation";
import { getDefaultStore, useAtomValue } from "jotai";
import { useEffect } from "react";
import { ActivityIndicator, AppState, NativeEventSubscription, ScrollView, StyleSheet, Text, useColorScheme, View } from "react-native";
import bootstrapAtom from "./bootstrap.atom";
import { initTrackPlayer } from "./bootstrap";
import { showDialog } from "@/components/dialogs/useDialog";
import i18n from "@/core/i18n";

export function BootstrapComponent() {
    const bootstrapState = useAtomValue(bootstrapAtom);

    useListenOrientationChange();
    useCheckUpdate();

    const followSystem = useAppConfig("theme.followSystem");

    const colorScheme = useColorScheme();

    useEffect(() => {
        if (followSystem) {
            if (colorScheme === "dark") {
                Theme.setTheme("p-dark");
            } else if (colorScheme === "light") {
                Theme.setTheme("p-light");
            }
        }
    }, [colorScheme, followSystem]);

    useEffect(() => {
        let appStateEventSubscription: NativeEventSubscription | null = null;

        const reinitializeTrackPlayerWithDialog = () => {
            showDialog("LoadingDialog", {
                title: i18n.t("dialog.loading.reinitializeTrackPlayer"), 
                promise: initTrackPlayer(),
                onResolve(data, hideDialog) {
                    hideDialog();
                },
                onReject(reason, hideDialog) {
                    hideDialog();
                },
            });
        };

        if (bootstrapState.state === "TrackPlayerError") {
            if (AppState.currentState === "active") {
                reinitializeTrackPlayerWithDialog();
            } else {
                appStateEventSubscription = AppState.addEventListener("change", (nextState) => {
                    if (nextState === "active" && getDefaultStore().get(bootstrapAtom).state === "TrackPlayerError") {
                        reinitializeTrackPlayerWithDialog();
                    }
                });
            }
        }

        return () => {
            if (appStateEventSubscription) {
                appStateEventSubscription.remove();
            }
        };
    }, [bootstrapState]);

    // 启动中 / 启动失败时显示全屏提示，避免白屏无反馈。
    // （开屏隐藏前这层被开屏盖住；开屏隐藏后若仍在启动，用户能看到进度。）
    if (bootstrapState.state === "Loading") {
        return (
            <View style={styles.overlay}>
                <ActivityIndicator size="large" color="#4b91c5" />
                <Text style={styles.title}>MusicFree</Text>
                <Text style={styles.sub}>正在启动…</Text>
            </View>
        );
    }
    if (bootstrapState.state === "Fatal" || bootstrapState.state === "TrackPlayerError") {
        const reason = bootstrapState.reason;
        return (
            <View style={styles.overlay}>
                <Text style={styles.title}>启动遇到问题</Text>
                <Text style={styles.sub}>
                    {bootstrapState.state === "TrackPlayerError" ? "播放器初始化失败" : "初始化失败"}
                </Text>
                <ScrollView style={styles.errBox}>
                    <Text style={styles.errText}>{String((reason && reason.message) || reason || "")}</Text>
                    <Text style={[styles.errText, {marginTop: 8}]}>{String((reason && reason.stack) || "")}</Text>
                </ScrollView>
                <Text style={styles.sub}>请把这屏文字截图发给开发者。</Text>
            </View>
        );
    }

    return null;
}

const styles = StyleSheet.create({
    overlay: {
        ...StyleSheet.absoluteFillObject,
        zIndex: 999,
        elevation: 999,
        backgroundColor: "#fff",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
    },
    title: {fontSize: 20, fontWeight: "bold", marginTop: 16, marginBottom: 8},
    sub: {fontSize: 14, color: "#666", textAlign: "center"},
    errBox: {maxHeight: 300, width: "100%", marginTop: 12},
    errText: {fontSize: 12, color: "#c00"},
});
