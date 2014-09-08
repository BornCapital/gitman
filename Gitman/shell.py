#!/usr/bin/env python
import sys
sys.path.insert(0,'/usr/share/yum-cli/')
import cli
import shell
import yummain
import yum
exit_code = 0
old_install = cli.YumBaseCli.install
def install(*args, **kwargs):
  global exit_code
  try:
    old_install(*args, **kwargs)
  except yum.Errors.InstallError:
    exit_code = 1
    raise
cli.YumBaseCli.install = install

old_exit = sys.exit
def exit(code=0):
  if code == 0:
    old_exit(exit_code)
  else:
    old_exit(code)
sys.exit = exit

old_run = shell.YumShell.do_run
def do_run(self, line):
  ret = old_run(self, line)
  if ret == False:
    self.result = 1
  return ret
shell.YumShell.do_run = do_run
try:
  yummain.user_main(sys.argv[1:], exit_code=True)
except KeyboardInterrupt, e:
    print >> sys.stderr, "\n\nExiting on user cancel."
    sys.exit(1)
