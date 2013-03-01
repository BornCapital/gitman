import difflib
import os


def get_diff(file1, file2, repo, rev1=None, rev2=None, gitbasedir='', prefixa='deployed', prefixb='newest'):
  reponame = os.path.basename(repo.working_dir)

  if rev1 and rev2:
    assert(file1 == file2)
    d1 = repo.git.show('%s:%s' % (rev1, os.path.join(gitbasedir, file1))).split('\n')
    d2 = repo.git.show('%s:%s' % (rev2, os.path.join(gitbasedir, file2))).split('\n')
    prefixa = '%s-%s' % (reponame, prefixa)
    prefixb = '%s-%s' % (reponame, prefixb)
  elif rev1:
    d1 = repo.git.show('%s:%s' % (rev1, os.path.join(gitbasedir, file1))).split('\n')
    with open(file2) as f:
      d2 = f.read().split('\n')
    prefixa = '%s-%s' % (reponame, prefixa)
    prefixb = ''
  elif rev2:
    with open(file1) as f:
      d1 = f.read().split('\n')
    d2 = repo.git.show('%s:%s' % (rev2, os.path.join(gitbasedir, file2))).split('\n')
    prefixa = ''
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
  return get_diff(git_file, fs_file, repo, rev)


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
  return get_diff(fs_file, git_file, repo, rev)

