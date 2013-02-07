import os
import re
import rpm
import subprocess


RPM_RE = re.compile(r'^(?P<name>.+)\-(?P<version>[\d\.]+)\-(?P<release>.*?)(\.rpm)?$')


class Package(object):
  __slots__ = 'name version release url'.split()

  def __init__(self, url=None, **kwargs):
    if url:
      fn = os.path.basename(url)
      match = RPM_RE.match(fn)

      if not match:
        self.name = fn
        self.version = None
        self.release = None
        self.url = url
      else:
        self.name = match.group('name')
        self.version = match.group('version')
        self.release = match.group('release')
        self.url = url
    else:
      for k, v in kwargs.items():
        setattr(self, k, v)

  def __cmp__(self, rhs):
    if self.version is None or rhs.version is None:
      return False

    ver1 = [int(x) for x in self.version.split('.')]
    ver2 = [int(x) for x in rhs.version.split('.')]

    while len(ver1) < len(ver2):
      ver1.append(0)
    while len(ver2) < len(ver1):
      ver2.append(0)

    result = cmp(ver1, ver2)

    if result == 0:
      rel1 = self.release
      rel2 = rhs.release
      if '.' in rel1:
        rel1 = rel1.split('.', 1)[0]
      if '.' in rel2:
        rel2 = rel2.split('.', 1)[0]

      result = cmp(rel1, rel2)

    return result

  def __str__(self):
    if self.version:
      assert(self.release) 
      return '%s-%s-%s' % (self.name, self.version, self.release)
    return self.name


class RPM_DB:
  def __init__(self):
    self.__install_set = set()
    self.__reinstall_set = set()
    self.update_installed_packages()

  def update_installed_packages(self):
    ts = rpm.TransactionSet()
    self.__pkgs = dict()
    for pkg in ts.dbMatch():
      name = pkg['name']
      version = pkg['version']
      release = pkg['release']
      self.__pkgs[name] = Package(name=name, version=version, release=release, url=None)

  def __contains__(self, pkg):
    return pkg.name in self.__pkgs

  def __getitem__(self, pkg_name):
    return self.__pkgs[pkg_name]

  def check_version(self, pkg):
    if pkg in self:
      curpkg = self.__pkgs[pkg.name]
    return True

  def queue_install(self, pkg, reinstall=False):
    if reinstall:
      self.__reinstall_set.add(pkg)
    if (pkg.name not in self.__pkgs or
        not pkg.version or # pkg is newer maybe?
        pkg > self.__pkgs[pkg.name]):
      self.__install_set.add(pkg)

  def install(self):
    if len(self.__reinstall_set):
      cmd = 'yum reinstall -q -y'.split()
      cmd.extend([pkg.url for pkg in self.__reinstall_set])

      rc = subprocess.call(cmd)

      if rc != 0:
        raise RuntimeError('yum failed to reinstall required packages: %s' %
                          ' '.join(cmd))

    if len(self.__install_set):
      cmd = 'yum install -q -y'.split()
      cmd.extend([pkg.url for pkg in self.__install_set])

      rc = subprocess.call(cmd)

      if rc != 0:
        raise RuntimeError('yum failed to install required packages: %s' %
                          ' '.join(cmd))

  def remove(self, pkg, test=False, holdup=None):
    if test:
      cmd = 'rpm --quiet --test -e'.split()
    else:
      cmd = 'yum remove -y'.split()

    if type(pkg) is Package:
      cmd.append(str(pkg))
    else:
      cmd.extend([str(rpm) for rpm in pkg])
    
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = proc.communicate()[0]
    rc = proc.wait()

    if rc != 0:
      if not test:
        raise RuntimeError('Failed to remove %s' % pkg)
      if holdup:
        holdup('DELETED rpm cannot be removed: %s\n%s' % (pkg, output.rstrip()))
      return False

    return True

  def verify(self, pkg, holdup=None, msg=None):
    if pkg.name not in self.__pkgs:
      return True

    cmd = ['rpm', '-V', pkg.name]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = proc.communicate()[0]
    rc = proc.wait()

    if rc != 0:
      if holdup:
        reasons_map = {
          'S' : 'File Size differs',
          'M' : 'Mode differs (includes permissions and file type)',
          '5' : 'MD5 sum differs',
          'D' : 'Device major/minor number mismatch',
          'L' : 'ReadLink(2) path mismatch',
          'U' : 'User ownership differs',
          'G' : 'Group ownership differs',
          'T' : 'Mtime differs',
          'P' : 'Capabilities differ',
        }

        reasons = list()

        for line in output.split('\n'):
          if len(line) > 0:
            flags, file = line.split()
            for flag in flags:
              if flag in reasons_map:
                reasons.append((reasons_map[flag], file))

        if msg:
          holdup(msg)
        for reason, file in reasons:
          holdup('\t%s: %s' % (file, reason))

      return False

    return True
