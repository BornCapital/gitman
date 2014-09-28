import os

if os.getenv('GITMAN_NOACL', '0') != '1':
  try:
    import posix1e
    
    # check if the features we need are supported
    if (posix1e.HAS_ACL_CHECK and
        posix1e.HAS_ACL_ENTRY and
        posix1e.HAS_ACL_FROM_MODE and
        posix1e.HAS_EQUIV_MODE and
        posix1e.HAS_EXTENDED_CHECK):
      has_xacl = True
    else:
      del posix1e
      has_xacl = False
  except ImportError:
    has_xacl = False
else:
  has_xacl = False

import errno
import functools
import grp

import pwd
import stat


class ExtendedACLError(RuntimeError):
  pass


if has_xacl:
  class posix_acl_wrapper:
    '''Wraps posix1e acl calls to trap exceptions and rethrow something
       easier to understand...'''

    def __getattr__(self, attr):
      attr = getattr(posix1e, attr)
      if callable(attr):
        return functools.partial(posix_acl_wrapper.__wrap, attr)
      return attr

    @staticmethod
    def __wrap(func, *args, **kwargs):
      try:
        return func(*args, **kwargs)
      except IOError as e:
        raise ExtendedACLError(str(e))

  posix_acl = posix_acl_wrapper()


class ACL(object):
  @staticmethod
  def from_file(file):
    if not os.path.exists(file):
      return None
    elif os.path.islink(file):
      return SymlinkACL.__from_file(file)
    try:
      if has_xacl and posix_acl.has_extended(file):
        return ExtendedACL.__from_file(file)
    except ExtendedACLError:
      pass
    return SimpleACL.__from_file(file)

  @staticmethod
  def from_components(user=None, group=None, mode=None, xattr=None):
    if has_xacl and xattr:
      return ExtendedACL(user, group, xattr, mode).simplify()
    return SimpleACL(user, group, mode)

  @staticmethod
  def __get_ownership(file):
    stat_info = os.stat(file)
    try:
      user = pwd.getpwuid(stat_info.st_uid)[0]
    except KeyError:
      user = stat_info.st_uid
    try:
      group = grp.getgrgid(stat_info.st_gid)[0]
    except KeyError:
      group = stat_info.st_gid
    return user, group, stat_info

  @classmethod
  def __from_file(klass, file):
    user, group, stat_info = ACL.__get_ownership(file)
    return klass(user, group, klass.mode_from_stat(file, stat_info))

  def __init__(self, user, group):
    super(ACL, self).__init__()
    self.__user = user
    self.__group = group

  def __check_user(self, rhs):
    return (self.user is None or
            rhs.user is None or
            self.user == rhs.user)

  def __check_group(self, rhs):
    return (self.group is None or
            rhs.group is None or
            self.group == rhs.group)

  def __check_mode(self, self_mode, rhs_mode):
    return (self_mode is None or # if mode not defined, then it's equal
            rhs_mode is None or
            self_mode == rhs_mode)

  def __str__(self):
    user = self.user if self.user else 'default'
    group = self.group if self.group else 'default'
    return '%s.%s.%s' % (user, group, self.modestr)

  @property
  def user(self):
    return self.__user

  @property
  def group(self):
    return self.__group

  def applyto(self, file):
    user, group, stat_info = ACL.__get_ownership(file)

    if self.user and self.user != user:
      need_user = True
    else:
      need_user = False

    if self.group and self.group != group:
      need_group = True
    else:
      need_group = False

    if need_user:
      group = self.group
      gid = -1
      if group:
        gid = grp.getgrnam(self.group).gr_gid
      uid = pwd.getpwnam(self.user).pw_uid
      os.chown(file, uid, gid)
    elif need_group:
      gid = grp.getgrnam(self.group).gr_gid
      os.chgrp(file, gid)
    return stat_info


class SimpleACL(ACL):
  @staticmethod
  def mode_from_stat(file, stat_info):
    return stat.S_IMODE(stat_info.st_mode)

  def __init__(self, user, group, mode):
    super(SimpleACL, self).__init__(user, group)
    if mode and type(mode) is not int:
      mode = int(mode, 8)
    self.__mode = mode
  
  def __eq__(self, rhs):
    return (type(rhs) is SimpleACL and
            self._ACL__check_user(rhs) and
            self._ACL__check_group(rhs) and
            self._ACL__check_mode(self.__mode, rhs.__mode))

  def __ne__(self, rhs):
    return (type(rhs) is not SimpleACL or
            not self._ACL__check_user(rhs) or
            not self._ACL__check_group(rhs) or
            not self._ACL__check_mode(self.__mode, rhs.__mode))

  @property
  def mode(self):
    return self.__mode

  @property
  def modestr(self):
    return '%04o' % self.__mode if self.mode else 'default'

  @property
  def extended(self):
    return False

  def applyto(self, file):
    stat_info = super(SimpleACL, self).applyto(file)
    if self.__mode and self.__mode != SimpleACL.mode_from_stat(file, stat_info):
      os.chmod(file, self.__mode)

_ACL_TYPES = list()
_ACL_TYPES.append(SimpleACL)


if has_xacl:
  class ExtendedACL(ACL):
    @staticmethod
    def mode_from_stat(file, stat_info):
      return posix_acl.ACL(file=file)

    def __init__(self, user, group, xattr, chmod=0):
      super(ExtendedACL, self).__init__(user, group)

      assert(xattr)

      if type(chmod) is not int:
        if chmod is None:
          chmod = 0 
        else:
          chmod = int(chmod, 8)

      if type(xattr) is not posix1e.ACL:
        xattr = posix_acl.ACL(text=xattr)

        if not xattr.valid():
          has_tags = set([x.tag_type for x in xattr])
          for entry in posix_acl.ACL(mode=chmod):
            if entry.tag_type not in has_tags:
              xattr.append(entry)
          if not xattr.valid():
            xattr.calc_mask()

      self.__xattr = xattr

    def __eq__(self, rhs):
      return (type(rhs) is ExtendedACL and
              self._ACL__check_user(rhs) and
              self._ACL__check_group(rhs) and
              self.__xattr == rhs.__xattr)

    def __ne__(self, rhs):
      return (type(rhs) is not ExtendedACL or
              not self._ACL__check_user(rhs) or
              not self._ACL__check_group(rhs) or
              self.__xattr != rhs.__xattr)

    @property
    def mode(self):
      return self.__xattr

    @property
    def modestr(self):
      return self.mode.to_any_text(
        separator=',', options=posix_acl.TEXT_ABBREVIATE)

    @property
    def extended(self):
      return True

    def simplify(self):
      '''If this ExtendedACL only represents a SimpleACL, construct and
         return a SimpleACL, otherwise return self'''
      for elem in self.__xattr:
        if elem.tag_type in (posix1e.ACL_USER, posix1e.ACL_GROUP, posix1e.ACL_MASK):
          return self
      try:
        return SimpleACL(self.user, self.group, self.__xattr.equiv_mode())
      except IOError:
        return self

    def applyto(self, file):
      super(ExtendedACL, self).applyto(file)
      if self.__xattr:
        try:
          self.__xattr.applyto(file)
        except ExtendedACLError:
          raise RuntimeError('Failed to write Extended ACL for file "%s".' % file)

  _ACL_TYPES.append(ExtendedACL)


class SymlinkACL(ACL):
  @staticmethod
  def mode_from_stat(file, stat_info):
    return 0

  def __init__(self, user, group, mode):
    super(SymlinkACL, self).__init__(user, group)
  
  def __eq__(self, rhs):
    return (type(rhs) in _ACL_TYPES)

  def __ne__(self, rhs):
    return (type(rhs) not in _ACL_TYPES)

  @property
  def modestr(self):
    return '0777'

  @property
  def extended(self):
    return False

  def applyto(self, file):
    return

