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
    _resolve(@(YES));
    _resolve = nil;
    _reject = nil;
  }
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller {
  if (_resolve) {
    _resolve(@(NO));
    _resolve = nil;
    _reject = nil;
  }
}

@end
