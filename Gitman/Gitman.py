#!/usr/bin/env python

import git
import posix1e as posix_acl

import collections
import grp
import os
import pwd
import re
import shutil
import socket
import stat
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

def parse_config(line, config):
  machine = re.compile('%machine%')
  short_machine = re.compile('%short_machine%')
  line = machine.sub(config['host'], line)
  line = short_machine.sub(config['short_host'], line)
  return line

def check_file_perms(file, user, group, mode, xattrs, **kwargs):
  if user == None and group == None and mode == None and xattrs == None:
    return True
  elif not os.path.isfile(file):
    return False

  stat_info = os.stat(file)
  uid = stat_info.st_uid
  gid = stat_info.st_gid
  ouser = pwd.getpwuid(uid)[0]
  ogroup = grp.getgrgid(gid)[0] 
  omode = ('%o' % stat.S_IMODE(stat_info.st_mode)).zfill(4)
  oxattrs = posix_acl.ACL(file=file)
  return user == ouser and group == ogroup and mode == omode and (xattrs is None or xattrs == oxattrs)

def get_file_perms(file):
  if not os.path.isfile(file):
    return False

  stat_info = os.stat(file)
  uid = stat_info.st_uid
  gid = stat_info.st_gid
  user = pwd.getpwuid(uid)[0]
  group = grp.getgrgid(gid)[0] 
  mode = ('%o' % stat.S_IMODE(stat_info.st_mode)).zfill(4)
  xattrs = posix_acl.ACL(file=file)
  return '%s.%s.%s.%s' % (user, group, mode, xattrs.to_any_text(separator=',', options=posix_acl.TEXT_ABBREVIATE))

def get_file_perms_string(args):
  if args['xattrs'] is None:
    xattrs = createacl(int(args['mode'], 8), '')
  else:
    xattrs = args['xattrs']

  return '%s.%s.%s.%s' % (
    args['user'],
    args['group'],
    args['mode'],
    xattrs.to_any_text(separator=',', options=posix_acl.TEXT_ABBREVIATE))

def createacl(mode, xattrstr):
  acl = posix_acl.ACL(mode=mode)

  for e in acl:
    if e.tag_type == posix_acl.ACL_GROUP_OBJ:
      group_perms = e.permset
      break

  mask = None

  acl2 = posix_acl.ACL(text=xattrstr)
  for e in acl2:
    if e.tag_type == posix_acl.ACL_MASK:
      mask = e
    acl.append(e)

  if mask is None:
    mask = acl.append()
    mask.tag_type = posix_acl.ACL_MASK
    mask.permset = group_perms

  return acl


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
    

class GitMan:
  def __init__(self, path, deploy_file='.git/gitman_deploy'):
    self.path = path
    self.deploy_file = deploy_file

    self.repo = git.Repo(path)
    version = self.deployed_version()
    self.check_is_clean()
    if version:
      self.switch_to(version)
      original_config = self.load_config()
      self.original_files, foo, self.original_crontabs = self.load_files(original_config)
    else:
      self.original_files = []
      self.original_crontabs = {}
    self.switch_to_head_and_update()
    new_config = self.load_config()
    self.config = new_config
    self.new_files, foo, self.new_crontabs = self.load_files(new_config)

  def load_files(self, config):
    host_file = os.path.join(self.path, config['host_dir'], config['host_file'])
    comment = re.compile('^\s*#')

    include_files = []
    exclude_files = []
    crontabs = collections.defaultdict(dict)
    cmds = []

    def parse_file(file):
      root = os.path.join(self.path, config['root'])
      default_attr = [None, None, None, None]
      def parse_attrs(args):
        user, group, mode, xattr = default_attr
        for arg in args:
          k, v = arg.split('=', 1)
          
          if k == 'user':
            user = v
          elif k == 'group':
            group = v
          elif k == 'mode':
            mode = v
            intmode = int(mode, 8)
          elif k == 'xattr':
            xattr = v
            
        if xattr and type(xattr) != posix_acl.ACL:
          xattr = createacl(int(mode, 8), xattr)

        return user, group, mode, xattr

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
            default_attr = parse_attrs(rest.split())[:]
          elif cmd == 'crontab':
            user, file = rest.strip().split(' ')
            #TODO: verify is valid crontab file
            crontab_path = os.path.join(root, file)
            if not os.path.exists(crontab_path):
              raise RuntimeError('Crontab file %s does not exist' % crontab_path)
            crontabs[user].setdefault('files', list()).append(crontab_path)
            crontabs[user]['user'] = user
          elif cmd == 'include':
            a = rest.split(' ')
            pattern = a[0]
            if len(a) > 1:
              args = a[1:]
            else:
              args = []
            user, group, mode, xattrs = parse_attrs(args)
            pattern = pattern.strip()
            if pattern[0] == '/':
              pattern = pattern[1:]
            files = ant_glob(start_dir=root, incl=pattern.strip(), dir=True)
            for file in files:
              include_files.append([file, dict(user=user, group=group, mode=mode, root=root, xattrs=xattrs)])
          elif cmd == 'exclude':
            exclude_files.extend(ant_glob(start_dir=root, incl=rest.strip(), dir=True))
          else:
            raise RuntimeError('Unknown line in config file: %s' % line)
    parse_file(host_file)
    files = {}
    dirs = {}
    for file, args in include_files:
      if not os.path.isdir(file):
        f = os.path.join(self.path, file)
        args['hash'] = self.repo.git.hash_object(file, with_keep_cwd=True) 
        args['realfile'] = file
        file = file[len(args['root']):]
        if not file in files:
          files[file] = args
      else:
        dirs[dir] = True

    for file in exclude_files:
      files.pop(file, None)

    for usercrontabs in crontabs.values():
      crontab = ConcatCrontabs(usercrontabs['files'])
      hash = self.repo.git.hash_object(crontab.name, with_keep_cwd=True)
      usercrontabs['hash'] = hash
      usercrontabs['crontab'] = crontab

    return files, cmds, crontabs

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
      return self.repo.git.hash_object(tmp)
    finally:
      os.unlink(tmp)

  def deleted_files(self):
    files = []
    for file in set(self.original_files) - set(self.new_files):
      files.append([file, self.original_files[file]['realfile'], self.original_files[file]])
    return files

  def added_files(self):
    files = []
    for file in set(self.new_files) - set(self.original_files):
      files.append([file, self.new_files[file]['realfile'], self.new_files[file]])
    return files

  def modified_files(self):
    files = []
    for file in set(self.new_files) & set(self.original_files):
      files.append([file, self.new_files[file]['realfile'], self.original_files[file], self.new_files[file]])
    return files

  def deleted_crontabs(self):
    crontabs = []
    for user in set(self.original_crontabs.keys()) - set(self.new_crontabs.keys()):
      crontabs.append(self.original_crontabs[user])
    return crontabs

  def added_crontabs(self):
    crontabs = []
    for user in set(self.new_crontabs.keys()) - set(self.original_crontabs.keys()):
      crontabs.append(self.new_crontabs[user])
    return crontabs

  def modified_crontabs(self):
    crontabs = []
    for user in set(self.new_crontabs.keys()) & set(self.original_crontabs.keys()):
      crontabs.append(self.new_crontabs[user])
    return crontabs

  def show_deployment(self):
    verbose_info = []
    holdups = []
    can_deploy = True
    def verbose(str):
      verbose_info.append(str)

    def holdup(str):
      holdups.append(str)
      verbose_info.append(str)

    #Find files that will be deleted, only if they are unchanged
    for file, sys_file, orig_args in self.deleted_files():
      if not os.path.exists(file):
        verbose('DELETED: %s (locally and in new config)' % file)
      else:
        if self.repo.git.hash_object(file) != orig_args['hash']:
          holdup('DELETED: %s (locally modified)' % file)
        else:
          verbose('DELETED: %s' % file)

    #Find files that will be added, assuming they don't already exist
    for file, sys_file, new_args in self.added_files():
      if os.path.exists(file):
        if self.repo.git.hash_object(file) == new_args['hash']:
          if not check_file_perms(file, **new_args):
            holdup('ADDED: %s\n  PERMISSIONS INCORRECT: %s (locally) -> %s' %
                   (file, get_file_perms(file), get_file_perms_string(new_args)))
          else:
            verbose('ADDED: %s (already exists locally, no changes)' % file)
        else:
          holdup('ADDED: %s (exists but has diffrences locally)' % file)
      else:
        verbose('ADDED: %s' % file)

    #Find files that will be update
    for file, sys_file, orig_args, new_args in self.modified_files():
      if new_args['user'] != orig_args['user'] or \
         new_args['group'] != orig_args['group'] or \
         new_args['mode'] != orig_args['mode']:
        holdup('PERMISSIONS: %s from %s -> %s' %
               (file, get_file_perms_string(orig_args), get_file_perms_string(new_args)))
      if not check_file_perms(file, **orig_args):
        if not check_file_perms(file, **new_args):
          verbose('PERMISSIONS: %s from %s -> %s' %
                  (file, get_file_perms(file), get_file_perms_string(new_args)))
        else:
          holdup('PERMISSIONS: %s (locally changed) from %s -> %s' %
                 (file, get_file_perms_string(orig_args), get_file_perms(file)))
      if not os.path.exists(file):
        holdup('MISSING FILE: %s' % file)
      elif self.repo.git.hash_object(file) != orig_args['hash']:
        if self.repo.git.hash_object(file) != new_args['hash']:
          holdup('LOCALLY MODIFIED: %s' % file)
        else:
          verbose('INCORRECT VERSION: %s' % file)
      # check current perms
      if new_args['hash'] != orig_args['hash']:
        verbose('MODIFIED: %s' % file)
      # user change

    #Deleted crontabs
    for crontab in self.deleted_crontabs():
      user = crontab['user']
      hash = self.crontab_hash(user)
      if hash == 0: # already deleted
        verbose('DELETED crontab: %s (already deployed)' % user)
      elif hash != crontab['hash']:
        holdup('DELETED (locally modified) crontab: %s' % user)
      else:
        verbose('DELETED crontab: %s' % user)

    #Added crontabs
    for crontab in self.added_crontabs():
      user = crontab['user']
      hash = self.crontab_hash(user)
      if hash == 0: # not deployed yet
        verbose('ADDED crontab: %s' % user)
      elif hash == crontab['hash']:
        verbose('ADDED crontab: %s (already deployed)' % user)
      else:
        holdup('ADDED (locally exists) crontab: %s' % user)

    #Modified crontabs
    for crontab_new in self.modified_crontabs():
      user = crontab_new['user']
      crontab_orig = self.original_crontabs[user]
      hash = self.crontab_hash(user)
      if hash != crontab_orig['hash']:
        holdup('MODIFIED (locally modified) crontab: %s' % user)
      elif crontab_new['hash'] == crontab_orig['hash']:
        continue
      elif hash == crontab_new['hash']:
        verbose('MODIFIED crontab: %s (already deployed)' % user)
      else:
        verbose('MODIFIED crontab: %s' % user)

    return holdups, verbose_info

  def setperms(self, file, args):
    if args['mode']:
      os.chmod(file, int(args['mode'], 8))
    if args['user']:
      group = args['group']
      gid = -1
      if group:
        gid = grp.getgrnam(args['group']).gr_gid
      uid = pwd.getpwnam(args['user']).pw_uid
      os.chown(file, uid, gid)
    elif args['group']:
      os.chgrp(file, args['group'])
    if args['xattrs']:
      args['xattrs'].applyto(file)

  def deploy(self, force, backup):
#Delete files
    for file, sys_file, orig_args in self.deleted_files():
      if os.path.exists(file):
        if backup:
          os.rename(file, '%s.gitman' % file)
        else:
          os.unlink(file)

#Add files
    for file, sys_file, new_args in self.added_files():
      if os.path.exists(file) and backup:
        shutil.move(file, '%s.gitman' % file)
      dir = os.path.dirname(file)
      if not os.path.isdir(dir):
        os.makedirs(dir)
      shutil.copy(sys_file, file)
      self.setperms(file, new_args)

#Update files
    for file, sys_file, orig_args, new_args in self.modified_files():
      if os.path.exists(file) and backup:
        shutil.move(file, '%s.gitman' % file)
      shutil.copy(sys_file, file)
      self.setperms(file, new_args)

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

  def switch_to_head_and_update(self):
    self.repo.git.fetch()
    branch = self.repo.active_branch.tracking_branch()
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
    else:
      revision_string = '%s..%s' % (self.deployed_version(), self.repo.active_branch.tracking_branch())
    return len(self.repo.git.log('--pretty=tformat:"%H"', revision_string).split('\n')) - 1

  def load_config(self):
    base_path = self.path
    config = {
        'securepath': '/usr/sbin:/usr/bin:/sbin:/bin',
        'root': 'root',
        'host': socket.gethostbyaddr(socket.gethostname())[0],
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


def main():
  import ansi
  import optparse
  import posix

  if 'HOME' not in os.environ or os.environ['HOME'] == '' or os.environ['HOME'] == '/':
    os.environ['HOME'] = pwd.getpwuid(posix.getuid())[7]

  parser = optparse.OptionParser()
  parser.add_option('-v', '--verbose', help='set verbose', action='store_true')
  parser.add_option('--force', help='force apply changes', action='store_true')
  parser.add_option('--deploy', help='deploy changes', action='store_true')
  parser.add_option('-d', '--base-path', help='base path')
  parser.add_option('-b', '--backup', help='backup files')

  (options, args) = parser.parse_args()
  if not options.base_path:
    parser.error('-d/--base-path required')
  if options.force and not options.deploy:
    parser.error('Cannot force without deployment')
  verbose = options.verbose
  gitman = GitMan(options.base_path)
  if verbose:
    ansi.writeout('Deployed version: %s' % gitman.deployed_version())
    ansi.writeout('Newest version: %s' % gitman.latest_version())
    ansi.writeout('  %d revisions between deployed and latest' %
                  gitman.undeployed_revisions())
    ansi.writeout('New files to deploy:\n  %s' % '\n  '.join(sorted(gitman.new_files.keys())))
  holdups, verbose_info = gitman.show_deployment()
  if verbose:
    ansi.writeout('%s\n' % '\n'.join(verbose_info))
  if len(holdups) > 0 and not options.force:
    ansi.writeout('${BRIGHT_YELLOW}Force deployment needed:${RESET}')
    ansi.writeout('${BRIGHT_RED}%s${RESET}' % '\n'.join(holdups))
    sys.exit('Deployment skipped due to holdups...')

  if options.deploy:
    gitman.deploy(backup=options.backup, force=options.force)
