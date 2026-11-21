import Theme from "@/core/theme";
import React from "react";
import {
    Platform,
    StyleSheet,
    View,
    type StyleProp,
    type ViewStyle,
} from "react-native";
import { GlassView, isGlassEffectAPIAvailable } from "expo-glass-effect";

/**
 * 真液体玻璃表面（仅 iOS 26+）。
 *
 * expo-glass-effect 底层是系统原生的 UIGlassEffect（iOS 26 的玻璃材质），
 * 会真实折射 / 反射背后的文字、背景、图片 —— 不是高斯模糊，也不是贴图。
 *
 * 玻璃不可用时（iOS < 26、API 不存在、原生模块未安装）降级为普通实色 View，
 * 绝不用 blur 冒充玻璃。
 *
 * 使用规则：
 * - 只包浮在内容上面的 chrome（迷你播放器条、弹窗、播放控制区），不要包内容本身；
 * - 不要给 GlassView 设 backgroundColor（材质自己给底色，设了会盖掉效果）；
 * - 不要对 GlassView 做 opacity / transform 动画（改 glassEffectStyle 切换，它自带原生动画）。
 */
interface IGlassSurfaceProps {
    style?: StyleProp<ViewStyle>;
    /** 玻璃不可用时的兜底底色；不传则透明（保持原来无底色的样子） */
    fallbackColor?: string;
    /** 玻璃样式，默认 regular；玻璃叠玻璃时用 clear */
    glassEffectStyle?: "regular" | "clear";
    accessible?: boolean;
    accessibilityLabel?: string;
    children?: React.ReactNode;
}

let glassAvailable: boolean | null = null;
function isGlassAvailable(): boolean {
    if (glassAvailable !== null) {
        return glassAvailable;
    }
    try {
        // 有些 iOS 26 beta 没有这个 API，不先查就用 GlassView 会闪退。
        glassAvailable =
            Platform.OS === "ios" && isGlassEffectAPIAvailable();
    } catch {
        // 原生模块未安装（比如旧包）：当作没有玻璃处理。
        glassAvailable = false;
    }
    return glassAvailable;
}

export default function GlassSurface(props: IGlassSurfaceProps) {
    const {
        style,
        fallbackColor,
        glassEffectStyle = "regular",
        accessible,
        accessibilityLabel,
        children,
    } = props;
    const theme = Theme.useTheme();

    if (isGlassAvailable()) {
        return (
            <GlassView
                style={style}
                glassEffectStyle={glassEffectStyle}
                // 跟随 App 自己的深浅主题，而不是系统外观（用户可能在 App 里选了深色而系统是浅色）。
                colorScheme={theme.dark ? "dark" : "light"}
                accessible={accessible}
                accessibilityLabel={accessibilityLabel}>
                {children}
            </GlassView>
        );
    }

    return (
        <View
            style={[
                style,
                fallbackColor !== undefined
                    ? { backgroundColor: fallbackColor }
                    : null,
            ]}
            accessible={accessible}
            accessibilityLabel={accessibilityLabel}>
            {children}
        </View>
    );
}

export const glassSurfaceStyles = StyleSheet.create({});
