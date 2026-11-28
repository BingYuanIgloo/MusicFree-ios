import React from "react";
import { StyleProp, ViewStyle } from "react-native";
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
    return (
        <SafeAreaView style={[style, { paddingTop: topInset }]} mode={mode} edges={["bottom"]}>
            {children}
        </SafeAreaView>
    );
}
