import React from "react";
import { StyleSheet } from "react-native";
import settingTypes from "./settingTypes";
import { SafeAreaView } from "react-native-safe-area-context";
import StatusBar from "@/components/base/statusBar";
import { useParams } from "@/core/router";
import HorizontalSafeAreaView from "@/components/base/horizontalSafeAreaView.tsx";
import AppBar from "@/components/base/appBar";
import { useI18N } from "@/core/i18n";
import useColors from "@/hooks/useColors";
import useStableTopInset from "@/hooks/useStableTopInset";

export default function Setting() {
    const { type } = useParams<"setting">();
    const settingItem = settingTypes[type];

    const { t } = useI18N();
    const colors = useColors();
    const topInset = useStableTopInset();

    return (
        <SafeAreaView edges={["bottom"]} style={[style.wrapper, { backgroundColor: colors?.pageBackground ?? "#fafafa", paddingTop: topInset }]}>
            <StatusBar />
            {settingItem.showNav === false ? null : (
                <AppBar>{t(settingItem.i18nKey as any)}</AppBar>
            )}

            {type === "plugin" ? (
                <settingItem.component />
            ) : (
                <HorizontalSafeAreaView style={style.wrapper}>
                    <settingItem.component />
                </HorizontalSafeAreaView>
            )}
        </SafeAreaView>
    );
}

const style = StyleSheet.create({
    wrapper: {
        width: "100%",
        flex: 1,
    },
    appbar: {
        shadowColor: "transparent",
        backgroundColor: "#2b333eaa",
    },
    header: {
        backgroundColor: "transparent",
        shadowColor: "transparent",
    },
});
