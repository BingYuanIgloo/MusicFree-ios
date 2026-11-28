import React, { useMemo } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import rpx from "@/utils/rpx";

import LocalMusicSheet from "@/core/localMusicSheet";
import { ROUTE_PATH } from "@/core/router";
import ThemeText from "@/components/base/themeText";
import Toast from "@/utils/toast";
import toast from "@/utils/toast";
import useOrientation from "@/hooks/useOrientation";
import { showPanel } from "@/components/panels/usePanel";
import TrackPlayer, { useCurrentMusic, useMusicQuality } from "@/core/trackPlayer";
import { iconSizeConst } from "@/constants/uiConst";
import PersistStatus from "@/utils/persistStatus";
import HeartIcon from "../heartIcon";
import Icon from "@/components/base/icon.tsx";
import PluginManager from "@/core/pluginManager";
import downloader from "@/core/downloader";
import i18n from "@/core/i18n";
import useColors from "@/hooks/useColors";

// 音质单字（原来是白色 PNG 图，浅色下看不清；改成文字后跟主题变色）。
const qualityShortText: Record<string, string> = {
    low: "低",
    standard: "标",
    high: "高",
    super: "超",
};

export default function Operations() {
    const musicItem = useCurrentMusic();
    const colors = useColors();
    const currentQuality = useMusicQuality();
    const isDownloaded = LocalMusicSheet.useIsLocal(musicItem);

    const rate = PersistStatus.useValue("music.rate", 100);
    const rateValue = rate ?? 100;
    const rateText =
        rateValue % 100 === 0
            ? `${rateValue / 100}.0x`
            : `${rateValue / 100}x`;
    const orientation = useOrientation();

    const supportComment = useMemo(() => {
        return !musicItem
            ? false
            : !!PluginManager.getByMedia(musicItem)?.supportedMethods.has("getMusicComments");
    }, [musicItem]);

    return (
        <View
            style={[
                styles.wrapper,
                orientation === "horizontal" ? styles.horizontalWrapper : null,
            ]}>
            <HeartIcon />
            <Pressable
                onPress={() => {
                    if (!musicItem) {
                        return;
                    }
                    showPanel("MusicQuality", {
                        musicItem,
                        async onQualityPress(quality) {
                            const changeResult =
                                await TrackPlayer.changeQuality(quality);
                            if (!changeResult) {
                                Toast.warn(i18n.t("toast.currentQualityNotAvailableForCurrentMusic"));
                            }
                        },
                    });
                }}>
                <ThemeText fontSize="title" fontWeight="semibold">
                    {qualityShortText[currentQuality]}
                </ThemeText>
            </Pressable>
            <Icon
                name={isDownloaded ? "check-circle-outline" : "arrow-down-tray"}
                size={iconSizeConst.normal}
                color={colors.text}
                onPress={() => {
                    if (musicItem && !isDownloaded) {
                        showPanel("MusicQuality", {
                            type: "download",
                            musicItem,
                            async onQualityPress(quality) {
                                downloader.download(musicItem, quality);
                            },
                        });
                    }
                }}
            />
            <Pressable
                onPress={() => {
                    if (!musicItem) {
                        return;
                    }
                    showPanel("PlayRate", {
                        async onRatePress(newRate) {
                            if (rate !== newRate) {
                                try {
                                    await TrackPlayer.setRate(newRate / 100);
                                    PersistStatus.set("music.rate", newRate);
                                } catch { }
                            }
                        },
                    });
                }}>
                <ThemeText fontSize="title" fontWeight="semibold">
                    {rateText}
                </ThemeText>
            </Pressable>
            <Icon
                name="chat-bubble-oval-left-ellipsis"
                size={iconSizeConst.normal}
                color={colors.text}
                opacity={supportComment ? 1 : 0.2}
                onPress={() => {
                    if (!supportComment) {
                        toast.warn(i18n.t("toast.commmentNotAvaliableForCurrentMusic"));
                        return;
                    }
                    if (musicItem) {
                        showPanel("MusicComment", {
                            musicItem,
                        });
                    }
                }}
            />
            <Icon
                name="ellipsis-vertical"
                size={iconSizeConst.normal}
                color={colors.text}
                onPress={() => {
                    if (musicItem) {
                        showPanel("MusicItemOptions", {
                            musicItem: musicItem,
                            from: ROUTE_PATH.MUSIC_DETAIL,
                        });
                    }
                }}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    wrapper: {
        width: "100%",
        height: rpx(80),
        marginBottom: rpx(24),
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-around",
    },
    horizontalWrapper: {
        marginBottom: 0,
    },
});
