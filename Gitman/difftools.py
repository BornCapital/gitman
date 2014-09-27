import difflib
import os
import re


def git_ls_tree(repo, path, rev='HEAD'):
  ls = repo.git.ls_tree('-r', rev, path)
  return re.split('\s+', ls)


def git_catfile(repo, path, rev='HEAD'):
  (mode, objtype, obj, fl) = git_ls_tree(repo, path, rev)
  return repo.git.cat_file('-p', obj)
  

def get_diff(file1, file2, repo, rev1=None, rev2=None, gitbasedir='', prefixa='deployed', prefixb='newest'):
  reponame = os.path.basename(repo.working_dir)

  file1_gitpath = os.path.join(gitbasedir, file1)
  file2_gitpath = os.path.join(gitbasedir, file2)

  if rev1 and rev2:
    assert(file1 == file2)
    d1 = git_catfile(repo, file1_gitpath, rev1).split('\n')
    d2 = git_catfile(repo, file2_gitpath, rev2).split('\n')
    prefixa = '%s-%s' % (reponame, prefixa)
    prefixb = '%s-%s' % (reponame, prefixb)
  elif rev1:
    d1 = git_catfile(repo, file1_gitpath, rev1).split('\n')
    if os.path.islink(file2):
      d2 = [os.readlink(file2)]
    else:
      with open(file2) as f:
        d2 = f.read().split('\n')
    prefixa = '%s-%s' % (reponame, prefixa)
  elif rev2:
    if os.path.islink(file1):
      d1 = [os.readlink(file1)]
    else:
      with open(file1) as f:
        d1 = f.read().split('\n')
    d2 = git_catfile(repo, file2_gitpath, rev2).split('\n')
    prefixb = '%s-%s' % (reponame, prefixb)

  file1 = os.path.join(prefixa, file1)
  file2 = os.path.join(prefixb, file2)
  return '\n'.join(difflib.unified_diff(d1, d2, file1, file2, lineterm=''))


def get_diff_deployed_to_fs(git_file, fs_file, repo, rev):
  if rev is None:
    return ''
  working_dir = repo.working_dir
  assert(git_file.startswith(working_dir))
  git_file = git_file[len(working_dir):].lstrip('/')
  return get_diff(git_file, fs_file, repo, rev, prefixb='existing')


def get_diff_deployed_to_newest(git_file, repo, rev1, rev2):
  if rev1 is None:
    return ''
  working_dir = repo.working_dir
  assert(git_file.startswith(working_dir))
  git_file = git_file[len(working_dir):].lstrip('/')
  return get_diff(git_file, git_file, repo, rev1, rev2)


def get_diff_fs_to_newest(fs_file, git_file, repo, rev):
  if rev is None:
    return ''
  working_dir = repo.working_dir
  assert(git_file.startswith(working_dir))
  git_file = git_file[len(working_dir):].lstrip('/')
  return get_diff(fs_file, git_file, repo, rev2=rev, prefixa='existing')

