import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import bootstrap from "./bootstrap/bootstrap";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import Dialogs from "@/components/dialogs";
import Panels from "@/components/panels";
import PageBackground from "@/components/base/pageBackground";
import { SafeAreaProvider } from "react-native-safe-area-context";
import Debug from "@/components/debug";
import { PortalHost } from "@/components/base/portal";
import globalStyle from "@/constants/globalStyle";
import Theme from "@/core/theme";
import useColors from "@/hooks/useColors";
import { BootstrapComponent } from "./bootstrap/BootstrapComponent";
import { ToastBaseComponent } from "@/components/base/toast";
import { StatusBar } from "react-native";
import { ReduceMotion, ReducedMotionConfig } from "react-native-reanimated";
import { routes } from "@/core/router/routes.tsx";
import ErrorBoundary from "@/components/errorBoundary";


/**
 * 字体颜色
 */


StatusBar.setBackgroundColor("transparent");
StatusBar.setTranslucent(true);


bootstrap();
const Stack = createNativeStackNavigator<any>();


export default function Pages() {
    const theme = Theme.useTheme();
    const colors = useColors();


    return (
        <ErrorBoundary>
            <BootstrapComponent />
            <ReducedMotionConfig mode={ReduceMotion.Never} />
            <GestureHandlerRootView
                style={[
                    globalStyle.flex1,
                    // 根容器底色取主题的 pageBackground，与最终应用面同色，
                    // 开屏藏起后、PageBackground 挂载前那一瞬不再有中间色闪。
                    { backgroundColor: colors?.pageBackground ?? "#fafafa" },
                ]}>
                <SafeAreaProvider>
                    <NavigationContainer theme={theme}>
                        <PageBackground />
                        <Stack.Navigator
                            initialRouteName={routes[0].path}
                            screenOptions={{
                                headerShown: false,
                                animation: "slide_from_right",
                                contentStyle: {
                                    flex: 1,
                                    width: "100%",
                                },
                            }}>
                            {routes.map(route => (
                                <Stack.Screen
                                    key={route.path}
                                    name={route.path}
                                    component={route.component}
                                />
                            ))}
                        </Stack.Navigator>                        
                        <Panels />
                        <Dialogs />
                        <Debug />
                        <ToastBaseComponent />
                        <PortalHost />
                    </NavigationContainer>
                </SafeAreaProvider>
            </GestureHandlerRootView>
        </ErrorBoundary>
    );
}
