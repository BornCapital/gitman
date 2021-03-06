#!/usr/bin/env python

import ansi
import difftools
import fs
import rpmtools

import git

import collections
import os
import pwd
import re
import socket
import subprocess
import sys
import tempfile


## Taken from http://code.google.com/p/waf/source/browse/waflib/Node.py
def ant_glob(*k, **kw):
  """
  This method is used for finding files across folders. It behaves like ant patterns:


  * ``**/*`` find all files recursively
  * ``**/*.class`` find all files ending by .class
  * ``..`` find files having two dot characters


  For example::


          def configure(cfg):
                  cfg.path.ant_glob('**/*.cpp') # find all .cpp files
                  cfg.root.ant_glob('etc/*.txt') # using the filesystem root can be slow
                  cfg.path.ant_glob('*.cpp', excl=['*.c'], src=True, dir=False)


  For more information see http://ant.apache.org/manual/dirtasks.html


  The nodes that correspond to files and folders that do not exist will be removed. To prevent this
  behaviour, pass 'remove=False'


  :param incl: ant patterns or list of patterns to include
  :type incl: string or list of strings
  :param excl: ant patterns or list of patterns to exclude
  :type excl: string or list of strings
  :param dir: return folders too (False by default)
  :type dir: bool
  :param src: return files (True by default)
  :type src: bool
  :param remove: remove files/folders that do not exist (True by default)
  :type remove: bool
  :param maxdepth: maximum depth of recursion
  :type maxdepth: int
  :param ignorecase: ignore case while matching (False by default)
  :type ignorecase: bool
  """

  src = kw.get('src', True)
  dir = kw.get('dir', False)
  maxdepth = kw.get('maxdepth', 25)

  excl = kw.get('excl', ['.git', '.gitignore'])
  incl = k and k[0] or kw.get('incl', '**')
  reflags = kw.get('ignorecase', 0) and re.I
  start_dir = kw.get('start_dir')

  listdir = os.listdir

  def ant_iter(current_dir, accept=None, maxdepth=25, pats=[], dir=False, src=True, remove=True):
    """
    Semi-private and recursive method used by ant_glob.


    :param accept: function used for accepting/rejecting a node, returns the patterns that can be still accepted in recursion
    :type accept: function
    :param maxdepth: maximum depth in the filesystem (25)
    :type maxdepth: int
    :param pats: list of patterns to accept and list of patterns to exclude
    :type pats: tuple
    :param dir: return folders too (False by default)
    :type dir: bool
    :param src: return files (True by default)
    :type src: bool
    """
    dircont = listdir(current_dir)
    dircont.sort()

    for name in dircont:
      npats = accept(name, pats)
      if npats and npats[0]:
        accepted = [] in npats[0]
        abspath = os.path.join(current_dir, name)
        isdir = os.path.isdir(abspath)
        if accepted:
          if isdir:
            if dir:
              yield abspath
          else:
            if src:
              yield abspath
        if isdir:
          if maxdepth:
            for k in ant_iter(abspath, accept=accept, maxdepth=maxdepth - 1, pats=npats, dir=dir, src=src):
              yield k
    raise StopIteration

  def to_list(sth):
    if isinstance(sth, str):
      return sth.split()
    else:
      return sth

  def to_pat(s):
    lst = to_list(s)
    ret = []
    for x in lst:
      x = x.replace('\\', '/').replace('//', '/')
      if x.endswith('/'):
        x += '**'
      lst2 = x.split('/')
      accu = []
      for k in lst2:
        if k == '**':
          accu.append(k)
        else:
          k = k.replace('.', '[.]').replace('*','.*').replace('?', '.').replace('+', '\\+')
          k = '^%s$' % k
          try:
            accu.append(re.compile(k, flags=reflags))
          except Exception as e:
            raise Exception('Invalid pattern: %s' % k, e)
      ret.append(accu)
    return ret


  def filtre(name, nn):
    ret = []
    for lst in nn:
      if not lst:
        pass
      elif lst[0] == '**':
        ret.append(lst)
        if len(lst) > 1:
          if lst[1].match(name):
            ret.append(lst[2:])
        else:
            ret.append([])
      elif lst[0].match(name):
        ret.append(lst[1:])
    return ret

  def accept(name, pats):
    nacc = filtre(name, pats[0])
    nrej = filtre(name, pats[1])
    if [] in nrej:
      nacc = []
    return [nacc, nrej]

  ret = [x for x in ant_iter(start_dir, accept=accept, pats=[to_pat(incl), to_pat(excl)], maxdepth=maxdepth, dir=dir, src=src)]
  #if kw.get('flat', False):
  #  return ' '.join([x.path_from(self) for x in ret])
  return ret


def exists(path):
  'Like os.path.exists(), but also returns true for dangling symlink'
  return os.path.islink(path) or os.path.exists(path)


def parse_config(line, config):
  machine = re.compile('%machine%')
  short_machine = re.compile('%short_machine%')
  line = machine.sub(config['host'], line)
  line = short_machine.sub(config['short_host'], line)
  return line


class ConcatCrontabs:
  def __init__(self, files):
    fd, self.tmpfilename = tempfile.mkstemp()
    with os.fdopen(fd, 'w') as tmpfile:
      print >> tmpfile, '### THIS FILE WAS AUTOGENERATED BY GITMAN. DO NOT EDIT! ###'
      print >> tmpfile
      for file in sorted(files): # sort to insure we always generate in the same order
        with open(file) as f:
          print >> tmpfile, '#>>', file
          content = f.read()
          tmpfile.write(content)
          print >> tmpfile, '#<<\n'

  def __del__(self):
    self.delete()

  @property
  def name(self):
    return self.tmpfilename

  def delete(self):
    if self.tmpfilename:
      try:
        os.unlink(self.tmpfilename)
        self.tmpfilename = None
      except:
        pass


class GitManCallbacks:
  def __init__(self, path, config):
    if 'pre-script' in config:
      self.pre_script = os.path.join(path, config['pre-script'])
      if not os.path.exists(self.pre_script):
        raise RuntimeError('Missing pre-script: %s' % self.pre_script)

    if 'post-script' in config:
      self.post_script = os.path.join(path, config['post-script'])
      if not os.path.exists(self.post_script):
        raise RuntimeError('Missing post-script: %s' % self.post_script)

    if 'deploy-script' in config:
      self.deploy_script = os.path.join(path, config['deploy-script'])
      if not os.path.exists(self.deploy_script):
        raise RuntimeError('Missing deploy-script: %s' % self.deploy_script)

    self.callbacks = list()

  def run_pre_script(self):
    if hasattr(self, 'pre_script'):
      ansi.writeout('Executing pre-script: %s' % self.pre_script)
      subprocess.check_call(self.pre_script)

  def run_post_script(self):
    if hasattr(self, 'pre_script'):
      ansi.writeout('Executing post-script: %s' % self.post_script)
      subprocess.check_call(self.post_script)

  def run_deployment_callbacks(self):
    if hasattr(self, 'deploy_script') and self.callbacks:
      ansi.writeout('Executing deploy-script: %s' % self.deploy_script)
      proc = subprocess.Popen(self.deploy_script, stdin=subprocess.PIPE)
      for callback in self.callbacks:
        action = '%s %s' % callback
        ansi.writeout('->%s' % action)
        print >> proc.stdin, action
      proc.stdin.close()
      n = proc.wait()
      if 0 != n:
        raise subprocess.CalledProcessError(n, self.deploy_script)

  def _run_deploy_script(self, path, command):
    self.callbacks.append((command, path))

  def add_file(self, path):
    self._run_deploy_script(path, 'add')

  def already_added_file(self, path):
    self._run_deploy_script(path, 'already-added')

  def modify_file(self, path):
    self._run_deploy_script(path, 'modify')

  def already_modified_file(self, path):
    self._run_deploy_script(path, 'already-modifed')

  def delete_file(self, path):
    self._run_deploy_script(path, 'delete')

  def already_deleted_file(self, path):
    self._run_deploy_script(path, 'already-deleted')


class GitMan:
  def __init__(self, path, origin=None, branch='master', info=None, assume_host=None, deploy_file='.git/gitman_deploy'):
    self.path = path
    self.deploy_file = deploy_file + '.' + branch.replace('/', '^')
    self.rpmdb = rpmtools.RPM_DB()

    if info:
      self.host = info
    elif assume_host:
      self.host = assume_host
    else:
      self.host = socket.gethostbyaddr(socket.gethostname())[0]

    if os.path.exists(path):
      try:
        self.repo = git.Repo(path)
        self.repo.git.log('--pretty=tformat:%H', '-n', '1') # causes exception if not a valid repo
      except:
        raise RuntimeError('Not a git repo: %s' % path)

      if origin and origin != self.repo.git.config('--get', 'remote.origin.url'):
        raise RuntimeError('Git repo is not a clone of the desired origin')
    else:
      self.repo = git.Repo.clone_from(origin, path)

    if info is None:
      version = self.deployed_version()
      self.check_is_clean()
    else:
      version = None

    if version:
      self.switch_to(version)
      original_config = self.load_config()
      self.original_files, self.original_crontabs, self.orig_rpms = self.load_files(original_config)
    else:
      self.original_files = []
      self.original_crontabs = {}
      self.orig_rpms = {}
    if info is None:
      self.switch_to_head_and_update(branch)
    new_config = self.load_config()
    self.config = new_config

    if info:
      self.config['host'] = info
      self.config['host_file'] = info

    self.new_files, self.new_crontabs, self.new_rpms = self.load_files(new_config)
    self.rpmdb = rpmtools.RPM_DB(rpm_ignore_mtime=(self.config.get('rpm_ignore_mtime', 'False').lower()=='true'))

    self.callbacks = GitManCallbacks(self.path, self.config)
    self.modified = list()

  def hash_file(self, path):
    "git.hash_object() doesn't support empty files, so we need to check this"
    if os.path.islink(path):
      return os.readlink(path)
    if os.path.exists(path) and os.path.getsize(path) == 0:
      return 0
    return self.repo.git.hash_object(path, with_keep_cwd=True) 

  def load_files(self, config):
    host_file = os.path.join(self.path, config['host_dir'], config['host_file'])
    if not os.path.exists(host_file):
      if 'default_host_file' in config:
        host_file = os.path.join(self.path, config['host_dir'], config['default_host_file'])
        config['host_file'] = config['default_host_file']
    comment = re.compile('^\s*#')

    include_files = []
    exclude_files = []
    crontabs = collections.defaultdict(dict)
    rpms = {}

    def parse_file(file):
      root = os.path.join(self.path, config['root'])
      default_attr = None
      dir_attr = None
      intmode = 0
      def parse_attrs(args):
        if default_attr:
          user = default_attr.user
          group = default_attr.group
          if default_attr.extended:
            mode = None
            xattr = default_attr.mode
          else:
            mode = default_attr.mode
            xattr = None
        else:
          user, group, mode, xattr = [None] * 4

        if dir_attr:
          if dir_attr.extended:
            dirmode = None
            dirxattr = dir_attr.mode
          else:
            dirmode = dir_attr.mode
            dirxattr = None
        else:
          dirmode = None
          dirxattr = None

        for arg in args:
          k, v = arg.split('=', 1)
          
          if k == 'user':
            user = v
          elif k == 'group':
            group = v
          elif k == 'mode':
            mode = v
          elif has_xacl and k == 'xattr':
            xattr = v
          elif k == 'dirmode':
            dirmode = v
          elif has_xacl and k == 'dirxattr':
            dirxattr = v
          else:
            raise RuntimeError('Invalid attribute: %s' % k)
            
        return (ACL.from_components(user, group, mode, xattr),
                ACL.from_components(user, group, dirmode, dirxattr))

      with open(file) as f:
        for line in f:
          line = line.strip()
          if not line or comment.match(line):
            continue
          (cmd, rest) = line.split(' ', 1)
          if cmd == 'root':
            root = parse_config(rest.strip(), config)
            root = os.path.join(self.path, root)
          elif cmd == 'import':
            parse_file(os.path.join(self.path, config['host_dir'], rest.strip()))
          elif cmd == 'defattr':
            rest = rest.split()
            if len(rest) == 1 and rest[0] == 'default':
              default_attr = None
              dir_attr = None
            else:
              default_attr, dir_attr = parse_attrs(rest)
          elif cmd == 'crontab':
            user, file = rest.strip().split(' ')
            #TODO: verify is valid crontab file
            crontab_path = os.path.join(root, file)
            if not os.path.exists(crontab_path):
              raise RuntimeError('Crontab file %s does not exist' % crontab_path)
            crontabs[user].setdefault('files', list()).append(crontab_path)
            crontabs[user]['user'] = user
          elif cmd == 'rpm':
            pkg = rpmtools.Package(rest.strip(), rpmdb=self.rpmdb)
            rpms[pkg.name] = pkg
          elif cmd == 'include':
            a = rest.split(' ')
            pattern = a[0]
            if len(a) > 1:
              args = a[1:]
            else:
              args = []
            acl, diracl = parse_attrs(args)
            pattern = pattern.strip()
            if pattern[0] == '/':
              pattern = pattern[1:]
            if os.path.isdir(root):
              files = ant_glob(start_dir=root, incl=pattern.strip(), dir=True)
              for file in files:
                if os.path.isdir(file):
                  fileacl = diracl
                else:
                  fileacl = acl
                include_files.append([file, dict(acl=fileacl, root=root, dirattr=dir_attr)])
          elif cmd == 'exclude':
            pattern = rest.strip()
            if pattern[0] == '/':
              pattern = pattern[1:]
            exclude_files.extend(ant_glob(start_dir=root, incl=pattern, dir=True))
          else:
            raise RuntimeError('Unknown line in config file: %s' % line)
    parse_file(host_file)
    files = {}
    for file, args in include_files:
      f = os.path.join(self.path, file)
      args['isdir'] = os.path.isdir(file)
      args['realfile'] = file
      if not args['isdir']:
        args['hash'] = self.hash_file(file)
      file = file[len(args['root']):]
      files[file] = args

    for file in exclude_files:
      file = file[len(args['root']):]
      files.pop(file, None)

    for usercrontabs in crontabs.values():
      crontab = ConcatCrontabs(usercrontabs['files'])
      hash = self.hash_file(crontab.name)
      usercrontabs['hash'] = hash
      usercrontabs['crontab'] = crontab

    return files, crontabs, rpms

  def crontab_hash(self, user):
    try:
      fd, tmp = tempfile.mkstemp()
      os.close(fd)
      cmd = 'crontab -l -u %s > %s' % (user, tmp)
      rc = os.system(cmd)
      status = os.WEXITSTATUS(rc)
      if rc and status != 1:
        raise RuntimeError('Failed to run: %s' % cmd)
      if status == 1:
        return 0
      return self.hash_file(tmp)
    finally:
      os.unlink(tmp)

  def deleted_files(self):
    files = []
    for file in set(self.original_files) - set(self.new_files):
      files.append([file, self.original_files[file]['realfile'], self.original_files[file]])
    files.sort()
    return files

  def added_files(self):
    files = []
    for file in set(self.new_files) - set(self.original_files):
      files.append([file, self.new_files[file]['realfile'], self.new_files[file]])
    files.sort()
    return files

  def common_files(self):
    files = []
    for file in set(self.new_files) & set(self.original_files):
      files.append([file, self.new_files[file]['realfile'], self.original_files[file], self.new_files[file]])
    files.sort()
    return files

  def modified_files(self):
    return self.modified

  def deleted_crontabs(self):
    crontabs = []
    for user in set(self.original_crontabs) - set(self.new_crontabs):
      crontabs.append(self.original_crontabs[user])
    return crontabs

  def added_crontabs(self):
    crontabs = []
    for user in set(self.new_crontabs) - set(self.original_crontabs):
      crontabs.append(self.new_crontabs[user])
    return crontabs

  def modified_crontabs(self):
    crontabs = []
    for user in set(self.new_crontabs) & set(self.original_crontabs):
      crontabs.append(self.new_crontabs[user])
    return crontabs

  def deleted_rpms(self):
    return [self.orig_rpms[rpm] for rpm in set(self.orig_rpms) - set(self.new_rpms)]

  def added_rpms(self):
    return [self.new_rpms[rpm] for rpm in set(self.new_rpms) - set(self.orig_rpms)]

  def modified_rpms(self):
    return [self.new_rpms[rpm] for rpm in set(self.new_rpms) & set(self.orig_rpms)]

  def show_deployment(self, show_diffs, show_holdup_diffs):
    verbose_info = []
    holdups = []
    failures = []

    def verbose(str):
      verbose_info.append(str)

    def holdup(str):
      holdups.append(str)
      verbose_info.append(str)

    def fail(str):
      failures.append(str)
      verbose_info.append(str)

    #Find files that will be deleted, only if they are unchanged
    for file, sys_file, orig_args in self.deleted_files():
      if not exists(file):
        verbose('DELETED and already removed: %s' % file)
        self.callbacks.already_deleted_file(file)
      else:
        if not orig_args['isdir'] and self.hash_file(file) != orig_args['hash']:
          holdup('DELETED but has local differences: %s' % file)
          if show_diffs or show_holdup_diffs:
            verbose(difftools.get_diff_deployed_to_fs(
              sys_file, file, self.repo, self.deployed_version()))
        else:
          verbose('DELETED: %s' % file)
        self.callbacks.delete_file(file)

    #Find files that will be added, assuming they don't already exist
    for file, sys_file, new_args in self.added_files():
      if exists(file):
        if new_args['isdir'] or self.hash_file(file) == new_args['hash']:
          file_acl = ACL.from_file(file)
          git_acl = new_args['acl']
          if file_acl != git_acl:
            holdup('ADDED and exists locally: %s\n  PERMISSIONS INCORRECT: %s (locally) -> %s' %
                   (file, file_acl, git_acl))
          else:
            verbose('ADDED and exists locally: %s' % file)
          self.callbacks.already_added_file(file)
        else:
          holdup('ADDED and exists with differences: %s' % file)
          if show_diffs:
            verbose(difftools.get_diff_fs_to_newest(
              file, sys_file, self.repo, self.latest_version()))
          if show_holdup_diffs:
            verbose(difftools.get_diff_deployed_to_fs(
              sys_file, file, self.repo, self.deployed_version()))
          self.callbacks.modify_file(file) # modify since what's on local disk is changing, not being added
      else:
        verbose('ADDED: %s' % file)
        self.callbacks.add_file(file)

    #Find files that will be update
    for file, sys_file, orig_args, new_args in self.common_files():
      modified = False
      new_acl = new_args['acl']
      orig_acl = orig_args['acl']
      file_acl = ACL.from_file(file)
      if new_acl != orig_acl:
        holdup('PERMISSIONS changed in repo: %s from %s -> %s' %
               (file, orig_acl, new_acl))
        modified = True
      if file_acl != orig_acl:
        if file_acl == new_acl:
          verbose('PERMISSIONS already changed locally: %s' % (file))
        else:
          holdup('PERMISSIONS were locally modified: %s from %s -> %s' %
                 (file, orig_acl, file_acl))
          modified = True
      if not exists(file):
        holdup('LOCAL file missing: %s' % file)
        modified = True
      elif not orig_args['isdir'] and self.hash_file(file) != orig_args['hash']:
        if not orig_args['isdir'] and self.hash_file(file) != new_args['hash']:
          holdup('LOCAL file has changes: %s' % file)
          modified = True
          if show_diffs or show_holdup_diffs:
            verbose(difftools.get_diff_deployed_to_fs(
              sys_file, file, self.repo, self.deployed_version()))
      if not orig_args['isdir'] and new_args['hash'] != orig_args['hash']:
        verbose('MODIFIED: %s' % file)
        modified = True
        if show_diffs:
          verbose(difftools.get_diff_deployed_to_newest(
            sys_file, self.repo, self.deployed_version(), self.latest_version()))
      if modified:
        self.modified.append((file, sys_file, orig_args, new_args))
        self.callbacks.modify_file(file)

    #Deleted crontabs
    for crontab in self.deleted_crontabs():
      user = crontab['user']
      hash = self.crontab_hash(user)
      if hash == 0: # already deleted
        verbose('DELETED crontab already removed: %s' % user)
      elif hash != crontab['hash']:
        holdup('DELETED crontab but has local differences: %s' % user)
      else:
        verbose('DELETED crontab: %s' % user)

    #Added crontabs
    for crontab in self.added_crontabs():
      user = crontab['user']
      hash = self.crontab_hash(user)
      if hash == 0: # not deployed yet
        verbose('ADDED crontab: %s' % user)
      elif hash == crontab['hash']:
        verbose('ADDED crontab already deployed: %s' % user)
      else:
        holdup('ADDED crontab already exists with differences: %s' % user)

    #Modified crontabs
    for crontab_new in self.modified_crontabs():
      user = crontab_new['user']
      crontab_orig = self.original_crontabs[user]
      hash = self.crontab_hash(user)
      if hash != crontab_orig['hash']:
        holdup('MODIFIED crontab but has local differences: %s' % user)
      elif crontab_new['hash'] == crontab_orig['hash']:
        continue
      elif hash == crontab_new['hash']:
        verbose('MODIFIED crontab already deployed: %s' % user)
      else:
        verbose('MODIFIED crontab: %s' % user)

    #Deleted rpms
    for rpm in self.deleted_rpms():
      if rpm not in self.rpmdb:
        verbose('DELETED rpm already removed: %s' % rpm)
      elif not self.rpmdb.verify(
          rpm, holdup, msg='DELETED rpm but has local differences: %s' % rpm):
        pass
      else :
        verbose("DELETED: %s" % rpm)
        self.rpmdb.remove(rpm)

    #Added rpms
    for rpm in self.added_rpms():
      self.rpmdb.protect(rpm)
      if rpm not in self.rpmdb: # not deployed yet
        verbose('ADDED rpm: %s' % rpm)
        self.rpmdb.install(rpm)
        continue
      elif rpm.version is None:
        verbose('ADDED unversioned rpm, may already be deployed: %s' % rpm)
      elif rpm == self.rpmdb[rpm.name]:
        verbose('ADDED rpm already deployed: %s' % rpm)
      elif rpm < self.rpmdb[rpm.name]:
        fail('RPM downgrades not supported: %s' % rpm)
      else:
        holdup('ADDED rpm already deployed with wrong version: %s (%s deployed)' %
               (rpm, self.rpmdb[rpm.name]))
      if not self.rpmdb.verify(
          rpm, holdup, msg='INSTALLED rpm has local differences: %s' %
          self.rpmdb[rpm.name]):
        self.rpmdb.install(rpm, reinstall=True) # flag this to be reinstalled if --force 

    #Modified rpms
    for rpm in self.modified_rpms():
      self.rpmdb.protect(rpm)
      if rpm not in self.rpmdb:
        if rpm == self.orig_rpms[rpm.name]:
          holdup('MISSING rpm: %s' % rpm)
        else:
          holdup('UPGRADED rpm missing locally: %s' % self.orig_rpms[rpm.name])
      elif rpm < self.rpmdb[rpm.name]:
        fail('RPM downgrades not supported: %s' % rpm)
      elif rpm == self.rpmdb[rpm.name]: # already deployed
        if not self.rpmdb.verify(
            rpm, holdup, msg='INSTALLED rpm has local differences: %s' % rpm):
          self.rpmdb.install(rpm, reinstall=True) # flag this to be reinstalled if --force 
      else: # upgrade rpm
        if not self.rpmdb.verify(
            rpm, holdup, msg='UPGRADED rpm has local differences: %s' % self.rpmdb[rpm.name]):
          pass
        else:
          verbose('UPGRADED rpm: %s' % rpm)
    
    for rpm in self.added_rpms():
      self.rpmdb.install(rpm)
    for rpm in self.modified_rpms():
      self.rpmdb.install(rpm)

    self.rpmdb.run(test=True, holdup=holdup)

    return holdups, verbose_info, failures

  def deploy(self, force, backup, reinstall=True):
    self.callbacks.run_pre_script()

    #Delete files
    for file, sys_file, orig_args in reversed(self.deleted_files()):
      if exists(file):
        if backup:
          os.rename(file, '%s.gitman' % file)
        elif orig_args['isdir']:
          try:
            os.rmdir(file)
          except:
            ansi.writeout('${BRIGHT_RED}ERROR: Failed to remove directory: %s${RESET}' % file)
        else:
          os.unlink(file)

    #Add files
    for file, sys_file, new_args in self.added_files():
      dir = os.path.dirname(file)
      if not os.path.isdir(dir):
        os.makedirs(dir)
        if new_args['dirattr']:
          new_args['dirattr'].applyto(dir)
      if new_args['isdir']:
        if not os.path.exists(file):
          os.mkdir(file)
      else:
        fs.copy(sys_file, file, backup)
      if not os.path.islink(file):
        new_args['acl'].applyto(file)

    #Update files
    for file, sys_file, orig_args, new_args in self.common_files():
      dir = os.path.dirname(file)
      if not os.path.isdir(dir):
        os.makedirs(dir)
        if new_args['dirattr']:
          new_args['dirattr'].applyto(dir)
      if new_args['isdir']:
        if not os.path.exists(file):
          os.mkdir(file)
      else:
        fs.copy(sys_file, file, backup)
      if not os.path.islink(file):
        new_args['acl'].applyto(file)

    for crontab in self.deleted_crontabs():
      cmd = 'crontab -r -u %s' % crontab['user']
      if 0 != os.system(cmd):
        raise RuntimeError('Failed to run cmd: %s' % cmd)

    crontabs = self.added_crontabs()
    crontabs.extend(self.modified_crontabs())

    for crontab in crontabs:
      cmd = 'crontab -u %s %s' % (crontab['user'], crontab['crontab'].name)
      if 0 != os.system(cmd):
        raise RuntimeError('Failed to run cmd: %s' % cmd)

    self.rpmdb.run(test=False, reinstall=reinstall)

    self.callbacks.run_deployment_callbacks()
    self.callbacks.run_post_script()

    with open(os.path.join(self.path, self.deploy_file), 'w') as f:
      f.write(self.latest_version())

  def check_is_clean(self):
    ##TODO: our current commit needs to be on origin
    if self.repo.is_dirty():
      diffs = self.repo.git.diff('-u')
      raise RuntimeError('Repo is dirty! %s' % diffs)
    current_commit = self.repo.git.log('--pretty=tformat:%H', '-n', '1')
    if not self.repo.git.branch('-r', '--contains', current_commit):
      raise RuntimeError('Repo is not pushed %s is not on origin' % current_commit)

  def switch_to(self, version):
    self.repo.git.reset('--hard', version)

  def switch_to_head_and_update(self, branch='master'):
    self.repo.git.fetch()
    if branch == 'master':
      branch = self.repo.active_branch.tracking_branch()
    else:
      self.repo.git.checkout(branch)
    self.switch_to(branch)

  def deployed_version(self):
    try:
      with open(os.path.join(self.path, self.deploy_file), 'r') as f:
        return f.read().rstrip()
    except:
      return None

  def latest_version(self):
    return self.repo.git.log(self.repo.active_branch.tracking_branch(), '--pretty=tformat:"%H"', '-n', '1')[1:-1]

  def undeployed_revisions(self):
    if not self.deployed_version():
      revision_string = self.repo.active_branch.tracking_branch()
    elif self.deployed_version() == self.latest_version():
      return 0
    else:
      revision_string = '%s..%s' % (self.deployed_version(), self.repo.active_branch.tracking_branch())
    return len(self.repo.git.log('--pretty=tformat:"%H"', revision_string).split('\n'))

  def load_config(self):
    base_path = self.path
    config = {
        'securepath': '/usr/sbin:/usr/bin:/sbin:/bin',
        'root': 'root',
        'host': self.host,
        'host_dir': 'hosts'
    };
    config['host_file'] = config['host']
    config['short_host'] = config['host'].split('.')[0]
    config['root'] = os.path.join('machines', config['host'])

    with open(os.path.join(base_path, 'config')) as f:
      for line in f:
        if ':' in line:
          key, value = line.split(':', 1)
          key = key.strip()
          value = value.strip()
          if key:
            config[key] = parse_config(value, config)
    return config;

  def dump_added(self):
    for file, sys_file, new_args in self.added_files():
      print 'ADDED:', file


def main():
  import optparse
  import posix

  if 'HOME' not in os.environ or os.environ['HOME'] == '' or os.environ['HOME'] == '/':
    os.environ['HOME'] = pwd.getpwuid(posix.getuid())[7]

  parser = optparse.OptionParser()
  parser.add_option('-q', '--quiet', action='store_true', help='Silence output')
  parser.add_option('-f', '--force', action='store_true', help='Force apply changes')
  parser.add_option('--no-reinstall-broken', action='store_false', help="Don't reinstall locally modified rpms", dest='reinstall', default=True)
  parser.add_option('-D', '--deploy', action='store_true', help='Deploy changes')
  parser.add_option('-d', '--repo-path', help='Repo path')
  parser.add_option('-b', '--backup', action='store_true', help='backup files')
  parser.add_option('--noacl', action='store_true', help='Disable ACL support')
  parser.add_option('--origin', help='URL for Git Repository origin')
  parser.add_option('--branch', default='master', help='Default: %default')
  parser.add_option('--diffs', action='store_true', help='Show diffs')
  parser.add_option('--info', metavar='MACHINE', help='Dump deployment info for a machine')
  parser.add_option('--assume-host', metavar='HOSTNAME', help='Assume the given hostname')
  parser.add_option('--holdup-diffs', action='store_true', help='Show holdup diffs')

  (options, args) = parser.parse_args()

  if options.noacl:
    os.environ['GITMAN_NOACL'] = '1'

  # import ACL in the global namespace
  # ACL module uses GITMAN_NOACL environment variable for conditional
  # compilation
  eval(
    compile(
      'from acl import ACL, has_xacl',
      __file__,
      'single'),
    globals(),
    globals())

  if not options.repo_path:
    parser.error('-d/--repo-path required')
  if options.force and not options.deploy:
    parser.error('Cannot force without deployment')
  if options.info:
    if options.quiet or options.deploy or options.backup or options.diffs or options.holdup_diffs:
      parser.error('Cannot use -q/-D/-b/--diffs/--holdup-diffs with --info')
  if options.diffs and options.holdup_diffs:
    parser.error('--diffs and --holdup-diffs should not be used together')
  verbose = not options.quiet and not options.info
  gitman = GitMan(
    os.path.abspath(options.repo_path),
    options.origin,
    options.branch,
    assume_host=options.assume_host,
    info=options.info)
  if verbose:
    ansi.writeout('Deployed version: %s' % gitman.deployed_version())
    ansi.writeout('Newest version: %s' % gitman.latest_version())
    ansi.writeout('  %d revisions between deployed and latest' %
                  gitman.undeployed_revisions())
  if options.info is None:
    holdups, verbose_info, failures = gitman.show_deployment(options.diffs, options.holdup_diffs)
    if verbose:
      ansi.writeout('\n'.join(verbose_info))
    if failures:
      ansi.writeout('${BRIGHT_RED}%s${RESET}' % '\n'.join(failures))
    if len(holdups) > 0 and not options.force:
      ansi.writeout('${BRIGHT_YELLOW}Force deployment needed:${RESET}')
      ansi.writeout('${BRIGHT_RED}%s${RESET}' % '\n'.join(holdups))
      if options.deploy:
        sys.exit('Deployment skipped due to holdups...')

    if options.deploy:
      if failures:
        sys.exit('Deployment skipped due to failures...')
      gitman.deploy(backup=options.backup, force=options.force, reinstall=options.reinstall)
  else:
    print 'Showing deployment info for:', gitman.config['host_file']
    gitman.dump_added()

