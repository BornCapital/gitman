#!/usr/bin/env python

from Gitman.acl import *

import getpass
import grp
import os
import pwd
import tempfile
import unittest


def create_tempfile(mode=0644, xattr=None):
  f = tempfile.NamedTemporaryFile()
  if xattr:
    if 0 != os.system('setfacl -m "%s" %s' % (xattr, f.name)):
      raise RuntimeError('Failed to run setfacl')
  else:
    os.chmod(f.name, mode)
  return f


ALL_USERS = [x[0] for x in sorted(pwd.getpwall())]
ALL_GROUPS = [x[0] for x in sorted(grp.getgrall())]


last_chown_file = None
last_chown_user = None
last_chown_group = None
last_chgrp_file = None
last_chgrp_group = None

def chown(f, uid, gid):
  global last_chown_file, last_chown_user, last_chown_group
  last_chown_file = f
  last_chown_user = pwd.getpwuid(uid)[0]
  if gid == -1:
    last_chgrp_group = None
  else:
    last_chown_group = grp.getgrgid(gid)[0]

def chgrp(f, gid):
  global last_chgrp_file, last_chgrp_group
  last_chgrp_file = f
  last_chgrp_group = grp.getgrgid(gid)[0]

# replace os.chown/chgrp methods
os.chown = chown
os.chgrp = chgrp


# decide if we hace xacl support, if we can write xacls
# on this volume
if has_xacl:
  with create_tempfile() as f:
    username = getpass.getuser()
    try:
      ACL.from_components(xattr='u::r,g::r,o::r,u:%s:rw' % username).applyto(f)
    except ExtendedACLError:
      has_fs_xacl = False
    else:
      has_fs_xacl = True
else:
  has_fs_xacl = False


class ACLTestCase(unittest.TestCase):
  def test_simple_acl_from_file(self):
    with create_tempfile() as f:
      stat_info = os.stat(f.name)
      user = pwd.getpwuid(stat_info.st_uid)[0]
      group = grp.getgrgid(stat_info.st_gid)[0]
      acl = ACL.from_file(f.name)
      self.assertEqual(type(acl), SimpleACL)
      self.assertEqual(acl.user, user)
      self.assertEqual(acl.group, group)
      self.assertEqual(acl.mode, 0644)
      self.assertEqual(str(acl), '%s.%s.0644' % (user, group))

    with create_tempfile(0400) as f:
      acl = ACL.from_file(f.name)
      self.assertEqual(type(acl), SimpleACL)
      self.assertEqual(acl.mode, 0400)

  def test_simple_acl_from_components(self):
    acl = ACL.from_components()
    self.assertEqual(type(acl), SimpleACL)
    self.assertEqual(str(acl), 'default.default.default')
    self.assertEqual(acl.user, None)
    self.assertEqual(acl.group, None)
    self.assertEqual(acl._SimpleACL__mode, None)
    acl = ACL.from_components('user', 'group')
    self.assertEqual(type(acl), SimpleACL)
    self.assertEqual(str(acl), 'user.group.default')
    acl = ACL.from_components('user', 'group', 0755)
    self.assertEqual(type(acl), SimpleACL)
    self.assertEqual(str(acl), 'user.group.0755')

  def test_simple_acl_equality(self):
    default_acl = ACL.from_components()
    acl1 = ACL.from_components('user')
    acl2 = ACL.from_components('user', 'group')
    acl3 = ACL.from_components('user', 'group', 0600)

    self.assertEqual(default_acl, default_acl)
    self.assertFalse(default_acl != default_acl)
    self.assertEqual(default_acl, acl1)
    self.assertFalse(default_acl != acl1)
    self.assertEqual(default_acl, acl2)
    self.assertFalse(default_acl != acl2)
    self.assertEqual(default_acl, acl3)
    self.assertFalse(default_acl != acl3)

    self.assertEqual(acl1, acl2)
    self.assertFalse(acl1 != acl2)
    self.assertEqual(acl1, acl3)
    self.assertFalse(acl1 != acl3)

    self.assertEqual(acl2, acl3)
    self.assertFalse(acl2 != acl3)

    acl4 = ACL.from_components('user2')
    acl5 = ACL.from_components(group='group2')
    acl6 = ACL.from_components(mode=0400)

    self.assertNotEqual(acl4, acl1)
    self.assertNotEqual(acl4, acl2)
    self.assertNotEqual(acl4, acl3)
    self.assertNotEqual(acl5, acl2)
    self.assertNotEqual(acl5, acl3)
    self.assertNotEqual(acl6, acl3)

  def test_simple_acl_applyto(self):
    with create_tempfile(0400) as f:
      acl = ACL.from_components(mode=0644)
      acl.applyto(f.name)
      acl2 = ACL.from_file(f.name)
      self.assertEqual(acl, acl2)

    with create_tempfile(0400) as f:
      acl = ACL.from_components(ALL_USERS[0], ALL_GROUPS[0], 0644)
      acl.applyto(f.name)
      acl2 = ACL.from_file(f.name)
      self.assertEqual(acl.mode, acl2.mode)
      self.assertEqual(f.name, last_chown_file)
      self.assertEqual(ALL_USERS[0], last_chown_user)
      self.assertEqual(ALL_GROUPS[0], last_chown_group)

    with create_tempfile(0400) as f:
      acl = ACL.from_components(group=ALL_GROUPS[0], mode=0644)
      acl.applyto(f.name)
      acl2 = ACL.from_file(f.name)
      self.assertEqual(acl.mode, acl2.mode)
      self.assertEqual(f.name, last_chgrp_file)
      self.assertEqual(ALL_GROUPS[0], last_chgrp_group)

  if has_xacl:
    def test_extended_acl_from_components(self):
      acl = ACL.from_components('foo', 'bar', mode=0644, xattr='u:%s:rwx' % ALL_USERS[0])
      self.assertEqual(acl.user, 'foo')
      self.assertEqual(acl.group, 'bar')
      self.assertEqual(acl.modestr, 'u::rw-,u:%s:rwx,g::r--,m::rwx,o::r--' % ALL_USERS[0])

    def test_extended_acl_simplify(self):
      acl = ExtendedACL(None, None, xattr='u::rw,g::r,o::r')
      acl2 = acl.simplify()
      self.assertEqual(type(acl), ExtendedACL)
      self.assertEqual(type(acl2), SimpleACL)
      self.assertEqual(acl2.user, None)
      self.assertEqual(acl2.group, None)
      self.assertEqual(acl2.mode, 0644)

  if has_fs_xacl:
    def test_extended_acl_from_file(self):
      xattr='u::rw,g::r,o::r,u:%s:rwx' % ALL_USERS[0]
      xacl = ACL.from_components(xattr=xattr)
      with create_tempfile(xattr=xattr) as f:
        stat_info = os.stat(f.name)
        user = pwd.getpwuid(stat_info.st_uid)[0]
        group = grp.getgrgid(stat_info.st_gid)[0]
        acl = ACL.from_file(f.name)
        self.assertEqual(type(acl), ExtendedACL)
        self.assertEqual(acl.user, user)
        self.assertEqual(acl.group, group)
        self.assertEqual(acl, xacl)

    def test_extended_acl_applyto(self):
      with create_tempfile() as f:
        acl = ACL.from_components(mode=0644, xattr='u:%s:rwx' % ALL_USERS[0])
        acl.applyto(f.name)
        acl2 = ACL.from_file(f.name)
        self.assertEqual(acl, acl2)


if __name__ == '__main__':
  unittest.main()

