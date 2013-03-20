#!/usr/bin/env python
import sys
sys.path.insert(0,'/usr/share/yum-cli/')
import shell
old_run = shell.YumShell.do_run
def do_run(self, line):
  ret = old_run(self, line)
  if ret == False:
    self.result = 1
  return ret
shell.YumShell.do_run = do_run
try:
  import yummain
  yummain.user_main(sys.argv[1:], exit_code=True)
except KeyboardInterrupt, e:
    print >> sys.stderr, "\n\nExiting on user cancel."
    sys.exit(1)
