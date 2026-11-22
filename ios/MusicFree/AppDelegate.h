#import <RCTAppDelegate.h>
#import <UIKit/UIKit.h>

// SDK 58 已删除 EXAppDelegateWrapper（SDK 54 起已废弃，54 版头文件注明
// SDK 55 移除；Expo 官方模板也已改用 Swift 的 ExpoAppDelegate）。
// 本 App 的 AppDelegate.mm 只用 RCTAppDelegate 的接口（moduleName /
// initialProps / sourceURLForBridge / bundleURL / 链接与推送代理），
// 所以直接继承 RCTAppDelegate，不改 Swift、不引入 SceneDelegate。
// 注意：不要改成编译器提示的 EXReactDelegateWrapper——它是 NSObject，
// 没有 moduleName/initialProps，也不是 UIApplicationDelegate，不能做父类。
@interface AppDelegate : RCTAppDelegate

@end
