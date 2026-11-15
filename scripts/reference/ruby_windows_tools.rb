# SPDX-License-Identifier: BSD-2-Clause
# Resolve Windows executable suffixes for POSIX-style tool availability checks.
if RUBY_PLATFORM.match?(/mingw|mswin/)
  module WindowsExecutableSuffix
    def executable?(path)
      super || (File.extname(path).empty? && super("#{path}.exe"))
    end
  end
  File.singleton_class.prepend(WindowsExecutableSuffix)

  if ENV["RV23_ACT4_WINDOWS_IDL"] == "1"
    require "bundler/setup"
    require "idlc"
    module WindowsIdlProgress
      def compile_file(*args)
        progress = @pb
        @pb = nil
        super
      ensure
        @pb = progress
      end
    end
    Idl::Compiler.prepend(WindowsIdlProgress)
  end
end
