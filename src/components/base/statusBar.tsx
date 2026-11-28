import React from "react";
import { StatusBar, StatusBarProps, View } from "react-native";
import useColors from "@/hooks/useColors";
import Theme from "@/core/theme";

interface IStatusBarProps extends StatusBarProps {}

export default function (props: IStatusBarProps) {
    const colors = useColors();
    const theme = Theme.useTheme();
    const { backgroundColor, barStyle } = props;

    return (
        <>
            <StatusBar
                backgroundColor={"rgba(0,0,0,0)"}
                barStyle={barStyle ?? (theme.dark ? "light-content" : "dark-content")}
            />
            <View
                style={{
                    zIndex: 10000,
                    position: "absolute",
                    top: 0,
                    backgroundColor:
                        backgroundColor ?? colors.appBar ?? colors.primary,
                    width: "100%",
                    height: StatusBar.currentHeight,
                }}
            />
        </>
    );
}
