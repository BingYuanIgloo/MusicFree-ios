import React from "react";
import { Platform, StyleProp, ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import useStableTopInset from "@/hooks/useStableTopInset";

interface IVerticalSafeAreaViewProps {
    mode?: "margin" | "padding";
    children: JSX.Element | JSX.Element[];
    style?: StyleProp<ViewStyle>;
}
export default function VerticalSafeAreaView(
    props: IVerticalSafeAreaViewProps,
) {
    const { children, style, mode } = props;
    const topInset = useStableTopInset();
    // iOS 不留底部安全区：Home Indicator 是悬浮在内容上的，预留
    // 就会在迷你播放条 / 面板底下留一条灰带（黑条）。安卓保留。
    return (
        <SafeAreaView style={[style, { paddingTop: topInset }]} mode={mode} edges={Platform.OS === "ios" ? [] : ["bottom"]}>
            {children}
        </SafeAreaView>
    );
}
