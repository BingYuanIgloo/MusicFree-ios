import React from "react";
import { StyleSheet } from "react-native";
import rpx from "@/utils/rpx";
import SeekBar from "./seekBar";
import PlayControl from "./playControl";
import useOrientation from "@/hooks/useOrientation";
import { panelInfoStore } from "@/components/panels/usePanel";
import GlassSurface from "@/components/base/glassSurface";

export default function Bottom() {
    const orientation = useOrientation();
    // 面板打开时隐藏底部播放栏。
    //
    // 根因：面板挂在根节点（entry 里 Stack.Navigator 之后，zIndex 15010），
    // 但详情页属于原生 Stack 的一个页面，原生页面内容会在面板上面绘制，
    // 播放栏会盖住面板的最后一行（查看评论被遮一半）。zIndex 再大也修不了
    // 这种跨原生层级的压盖——面板是模态的，打开时底栏本来就点不到，
    // 所以直接隐藏是最稳妥的做法；面板关掉（收起动画走完）后底栏自动恢复。
    const panelInfo = panelInfoStore.useValue();
    if (panelInfo.name) {
        return null;
    }
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
