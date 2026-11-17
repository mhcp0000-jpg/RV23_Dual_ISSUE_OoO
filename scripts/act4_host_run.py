# SPDX-License-Identifier: Apache-2.0
"""Launch the unmodified ACT4 framework with Windows Ruby tool resolution."""
import subprocess
from pathlib import Path
import act.parse_udb_config as udb
import act.config as act_config
from act4_header_io import install
from act.act import main

udb._find_gemfile=lambda:Path('C:/rv_workspaces/rv23/out/act4/bundle/Gemfile')
assert act_config.REQUIRED_SAIL_VERSION in ('0.13.1', '0.16')
if act_config.REQUIRED_SAIL_VERSION == '0.13.1':
    act_config.REQUIRED_SAIL_VERSION = '0.16'
    print('LOCAL COMPATIBILITY MODE: Sail 0.16 for H; upstream ACT4 requires 0.13.1. Not an official certification run.', flush=True)
install()
original_run=subprocess.run
def portable_run(command,*args,**kwargs):
    if isinstance(command,(list,tuple)) and command and str(command[0])=='bundle':
        ruby='C:/rv_toolchains/ruby-act4/rubyinstaller-3.4.10-1-x64/bin/'
        command=[ruby+'ruby.exe',ruby+'bundle',*command[1:]]
    return original_run(command,*args,**kwargs)
subprocess.run=portable_run
main()
