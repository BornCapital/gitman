#!/usr/bin/env python
import sys
sys.path.insert(0,'/usr/share/yum-cli/')
import cli
import shell
import yummain
import yum
exit_code = 0

def ins_wrapper(name):
  old = getattr(cli.YumBaseCli, name)
  def do(*args, **kwargs):
    global exit_code
    try:
      old(*args, **kwargs)
    except:
      exit_code = 1
      raise
  setattr(cli.YumBaseCli, name, do)
ins_wrapper('install')
ins_wrapper('reinstall')

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
