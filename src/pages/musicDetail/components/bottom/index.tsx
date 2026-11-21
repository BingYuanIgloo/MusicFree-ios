import React from "react";
import { StyleSheet } from "react-native";
import GlassSurface from "@/components/base/glassSurface";
import rpx from "@/utils/rpx";
import SeekBar from "./seekBar";
import PlayControl from "./playControl";
import useOrientation from "@/hooks/useOrientation";

export default function Bottom() {
    const orientation = useOrientation();
    return (
        // 底部控制区浮在模糊专辑图之上：真玻璃会折射背后的专辑图。
        // 玻璃不可用时保持透明（和原来一样），不改样子。
        <GlassSurface
            style={[
                style.wrapper,
                orientation === "horizontal"
                    ? {
                        height: rpx(156),
                    }
                    : undefined,
            ]}>
            <SeekBar />
            <PlayControl />
        </GlassSurface>
    );
}

const style = StyleSheet.create({
    wrapper: {
        width: "100%",
        height: rpx(240),
    },
});
