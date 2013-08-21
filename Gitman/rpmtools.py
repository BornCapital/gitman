import os
import re
import rpm
import subprocess
import tempfile
import sys

RPM_RE = re.compile(r'^(?P<name>.+)\-(?P<version>[^-]+)\-(?P<release>[^\.]+).*?(\.rpm)?$')


def try_int(x):
  try:
    return int(x)
  except ValueError:
    return x


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

    ver1 = [try_int(x) for x in self.version.split('.')]
    ver2 = [try_int(x) for x in rhs.version.split('.')]

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
    self.__remove_set = set()
    self.__protect_set = set()
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

  def install(self, pkg, reinstall=False):
    if reinstall:
      self.__reinstall_set.add(pkg)
    if (pkg.name not in self.__pkgs or
        not pkg.version or # pkg is newer maybe?
        pkg > self.__pkgs[pkg.name]):
      self.__install_set.add(pkg)
  
  def remove(self, pkg):
    self.__remove_set.add(pkg)

  def protect(self, pkg):
    self.__protect_set.add(pkg.name)

  def run(self, test=True, holdup=None, reinstall=True):
    with tempfile.NamedTemporaryFile() as yum_script:
      protected = set()
      doing = {"erase": [], "reinstall": [], "install": []}
      for pkg in self.__remove_set:
        yum_script.write("erase %s\n" % pkg)
        doing["erase"].append(pkg.name)
      if reinstall:
        for pkg in self.__reinstall_set:
          yum_script.write("reinstall %s\n" % pkg.url)
          doing["reinstall"].append(pkg.name)
      for pkg in self.__install_set:
        yum_script.write("install %s\n" % pkg.url)
        doing["install"].append(pkg.name)
      yum_script.write("config errorlevel 2\n")
      yum_script.write("run\n")
      yum_script.flush()

      test_cmd = "" if not test else "--setopt=tsflags=test"
      protected_cmd = "" if len(self.__protect_set) == 0 else "--setopt=protected_packages=%s" % ",".join(self.__protect_set)
      cmd = ('-y %s %s shell %s' % (test_cmd, protected_cmd, yum_script.name)).split()
      if test:
        cmd.insert(0, '-q')
      cmd[0:0] = ["python", os.path.join(os.path.dirname(os.path.realpath(__file__)), 'shell.py')]

      proc = subprocess.Popen(cmd)
      output = proc.communicate()[0]
#TODO: ctrl-c will not stop this and leave it in an incomplete state
#and require a yum-cleanup
      rc = proc.wait()

      if rc != 0:
        def get_info():
          return "erase: %s, reinstall: %s, install: %s" % (
            ",".join(doing["erase"]), ",".join(doing["reinstall"]), ",".join(doing["install"])
          )
        if test and holdup:
          holdup("Unable to run rpm transaction: \n%s" % 
            get_info())
        else:
          raise RuntimeError("Unable to run rpm transaction:\n%s" % 
              get_info())

  def verify(self, pkg, holdup=None, msg=None):
    if pkg.name not in self.__pkgs:
      return True

    cmd = ['rpm', '-V', pkg.name]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = proc.communicate()[0]
    rc = proc.wait()
    verify_successful = True

    if rc != 0:
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
          if line.startswith('Unsatisfied dependencies'):
            reasons.append((line, 'package'))
            verify_successful = False
            break
          fields = line.split()
          if len(fields) > 2:
            flags, opt, file = fields
          else:
            flags, file = line.split()
            opt = None
          if opt == 'c': # config file:
            continue
          verify_successful = False
          for flag in flags:
            if flag in reasons_map:
              reasons.append((reasons_map[flag], file))

      if not verify_successful:
        if msg:
          holdup(msg)
        for reason, file in reasons:
          holdup('\t%s: %s' % (file, reason))

    return verify_successful


if __name__ == '__main__':
  import unittest

  class RPMtoolsTestCase(unittest.TestCase):
    def testPackage(self):
      p = Package('jsoncpp-0.6.0rc2-3.x86_64.rpm')
      self.assertEqual(p.name, 'jsoncpp')
      self.assertEqual(p.version, '0.6.0rc2')
      self.assertEqual(p.release, '3')

      p2 = Package('jsoncpp-0.6.0rc1-3.x86_64.rpm')
      self.assertTrue(p > p2)

      p3 = Package('python-borncapital-0.9-22.noarch')
      self.assertEqual(p3.name, 'python-borncapital')
      self.assertEqual(p3.version, '0.9')
      self.assertEqual(p3.release, '22')

      p4 = Package('bc-www-utils-1.0-2.noarch.rpm')
      self.assertEqual(p4.name, 'bc-www-utils')
      self.assertEqual(p4.version, '1.0')
      self.assertEqual(p4.release, '2')

  unittest.main()

