Pod::Spec.new do |s|
  s.name             = 'FileSaver'
  s.version          = '1.0.0'
  s.summary          = 'Save a file via the iOS Files picker (UIDocumentPickerViewController export mode).'
  s.homepage         = 'https://example.com'
  s.license          = { :type => 'MIT' }
  s.author           = { 'MusicFree' => '' }
  s.source           = { :git => '', :tag => '1.0.0' }
  s.platform         = :ios, '13.0'
  s.source_files     = '*.{h,m}'
  s.dependency 'React-Core'
end
