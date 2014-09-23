import os
import os.path
import shutil


def rmf(f):
  try:
    os.unlink(f)
  except:
    pass


def copy_or_remove(src, dst):
  'Copy src to dst, or remove dst on failure'
  if os.path.islink(src):
    l = os.readlink(src)
    os.symlink(l, dst)
  else:
    try:
      shutil.copy(src, dst)
    except:
      rmf(dst)
      raise


def move_or_remove(src, dst):
  'Move src to dst, or remove src on failure'
  try:
    shutil.move(src, dst)
  except:
    rmf(src)
    raise


def copy(src, dst, backup=False, backup_ext='.gitman'):
  backup_file = dst + backup_ext
  backup_tmp = backup_file + '.tmp'
  tmp_file = dst + '.tmp'

  if os.path.exists(dst) and backup:
    copy_or_remove(dst, backup_tmp)
  copy_or_remove(src, tmp_file)

  if backup:
    move_or_remove(backup_tmp, backup_file)

  move_or_remove(tmp_file, dst)

