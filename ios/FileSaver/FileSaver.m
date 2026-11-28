#import "FileSaver.h"
#import <React/RCTUtils.h>

@implementation FileSaver {
  RCTPromiseResolveBlock _resolve;
  RCTPromiseRejectBlock _reject;
}

RCT_EXPORT_MODULE(FileSaver);

RCT_EXPORT_METHOD(saveFile:(NSString *)filePath
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  _resolve = resolve;
  _reject = reject;
  dispatch_async(dispatch_get_main_queue(), ^{
    if (!filePath || ![[NSFileManager defaultManager] fileExistsAtPath:filePath]) {
      if (_reject) {
        _reject(@"ENOENT", @"File does not exist", nil);
        _resolve = nil;
        _reject = nil;
      }
      return;
    }
    NSURL *url = [NSURL fileURLWithPath:filePath];
    UIDocumentPickerViewController *picker = nil;
    if (@available(iOS 14.0, *)) {
      // asCopy:YES: the file is copied to the chosen location,
      // the app keeps its own copy (offline playback still works).
      picker = [[UIDocumentPickerViewController alloc] initForExportingURLs:@[url] asCopy:YES];
    } else {
      picker = [[UIDocumentPickerViewController alloc] initWithURLs:@[url] inMode:UIDocumentPickerModeExportToService];
    }
    picker.delegate = self;
    picker.modalPresentationStyle = UIModalPresentationFormSheet;
    UIViewController *root = RCTPresentedViewController();
    if (!root) {
      if (_reject) {
        _reject(@"NO_ROOT", @"No presenting view controller", nil);
        _resolve = nil;
        _reject = nil;
      }
      return;
    }
    [root presentViewController:picker animated:YES completion:nil];
  });
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  if (_resolve) {
    // 返回用户选的目标位置（file:// URL 字符串），JS 拿到后把真正下好的
    // 文件写进去（覆盖刚才的占位空文件）。原来只回 YES，JS 不知道存哪了。
    NSURL *dest = urls.firstObject;
    _resolve(dest ? dest.absoluteString : @"");
    _resolve = nil;
    _reject = nil;
  }
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller {
  if (_resolve) {
    // 取消返回空串：JS 以此判断“用户没选位置”，直接不下载、不提示成功。
    _resolve(@"");
    _resolve = nil;
    _reject = nil;
  }
}

// 把已下载好的文件写进用户在保存框里选的位置（安全域 URL，需先取访问权）。
// destURLString 是 saveFile 返回的那个 file:// URL。
RCT_EXPORT_METHOD(copyFileToURL:(NSString *)sourcePath
                  destURLString:(NSString *)destURLString
                  resolver:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
{
  dispatch_async(dispatch_get_main_queue(), ^{
    NSURL *destURL = [NSURL URLWithString:destURLString];
    if (!destURL || !sourcePath || ![[NSFileManager defaultManager] fileExistsAtPath:sourcePath]) {
      if (reject) reject(@"BAD_ARG", @"bad source or destination", nil);
      return;
    }
    BOOL access = [destURL startAccessingSecurityScopedResource];
    NSError *error = nil;
    NSFileManager *fm = [NSFileManager defaultManager];
    // 先删掉保存框当时拷过去的占位空文件，再拷真的文件进去。
    [fm removeItemAtURL:destURL error:nil];
    BOOL ok = [fm copyItemAtPath:sourcePath toURL:destURL error:&error];
    if (access) [destURL stopAccessingSecurityScopedResource];
    if (ok) {
      resolve(@(YES));
    } else {
      reject(@"COPY_FAIL", error.localizedDescription ?: @"copy failed", nil);
    }
  });
}

@end
