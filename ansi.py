from string import Template

import curses
import sys


"""
This module defines the ANSI terminal codes and support functions
"""

# CODES:
ESC                   = chr(27)
RESET                 = ESC + '[0m'
BOLD_ON               = ESC + '[1m'
ITALICS_ON            = ESC + '[3m'
UNDERLINE_ON          = ESC + '[4m'
BLINK_ON              = ESC + '[5m'
INVERSE_ON            = ESC + '[7m'
INVISIBLE_ON          = ESC + '[8m'
STRIKETHROUGH_ON      = ESC + '[9m'
BOLD_OFF              = ESC + '[22m'
ITALICS_OFF           = ESC + '[23m'
UNDERLINE_OFF         = ESC + '[24m'
BLINK_OFF             = ESC + '[25m'
INVERSE_OFF           = ESC + '[27m'
STRIKETHROUGH_OFF     = ESC + '[29m'
BLACK                 = ESC + '[30m' + BOLD_OFF
RED                   = ESC + '[31m' + BOLD_OFF
GREEN                 = ESC + '[32m' + BOLD_OFF
YELLOW                = ESC + '[33m' + BOLD_OFF
BLUE                  = ESC + '[34m' + BOLD_OFF
MAGENTA               = ESC + '[35m' + BOLD_OFF
CYAN                  = ESC + '[36m' + BOLD_OFF
WHITE                 = ESC + '[37m' + BOLD_OFF
DEFAULT               = ESC + '[39m' + BOLD_OFF
BRIGHT_BLACK          = ESC + '[30m' + BOLD_ON
BRIGHT_RED            = ESC + '[31m' + BOLD_ON
BRIGHT_GREEN          = ESC + '[32m' + BOLD_ON
BRIGHT_YELLOW         = ESC + '[33m' + BOLD_ON
BRIGHT_BLUE           = ESC + '[34m' + BOLD_ON
BRIGHT_MAGENTA        = ESC + '[35m' + BOLD_ON
BRIGHT_CYAN           = ESC + '[36m' + BOLD_ON
BRIGHT_WHITE          = ESC + '[37m' + BOLD_ON
BRIGHT_DEFAULT        = ESC + '[39m' + BOLD_ON
BG_BLACK              = ESC + '[40m'
BG_RED                = ESC + '[41m'
BG_GREEN              = ESC + '[42m'
BG_YELLOW             = ESC + '[43m'
BG_BLUE               = ESC + '[44m'
BG_MAGENTA            = ESC + '[45m'
BG_CYAN               = ESC + '[46m'
BG_WHITE              = ESC + '[47m'
BG_DEFAULT            = ESC + '[49m'
CLEARSCREEN           = ESC + '[2J' + ESC + '[1;1H'


current_locals = locals().copy()
ANSI_MAP = dict([(x, current_locals[x])
  for x in current_locals if x[0] != '_']) #: Map of codenames to codes

DEFAULT_MAP = dict([(x, '')
  for x in ANSI_MAP.keys()]) #: Map of codenames to empty strings


del current_locals


def map_string(s, map = DEFAULT_MAP):
  """
  Coverts a templatized string to a string with the template parameters
  replaced by ANSI codes.

  @type  s: string
  @param s: Templatized string (see string.Template). Template variables
            are from the set of ANSI codes in this module.
  @type  map: dict 
  @param map: dict of ANSI codename -> ANSI code. Default = DEFAULT_MAP.
              DEFAULT_MAP maps the codenames to empty string, and thus,
              removes the markup for non-ANSI terminals. ANSI_MAP can
              be used to keep the appropriate mapping.

  @rtype:  string
  @return: string containing appropriate ANSI codes based on the given
           map
  """

  t = Template(s)
  return t.safe_substitute(map)


def check_has_color():
  if not sys.stdout.isatty():
    return False

  curses.setupterm()
  set_fg_ansi = curses.tigetstr('setaf')
  set_bg_ansi = curses.tigetstr('setab')
  return (set_fg_ansi is not None and
          set_bg_ansi is not None)


has_color = check_has_color()


def writeout(msg, file=sys.stdout):
  """
  Writes a colorized template string to file, substituting the
  template patterns as appropriate. Decides to use ANSI colors
  based on if the file is a tty and curses says color is
  supported.

  @type  msg: string
  @param msg: Templatized string (see string.Template). Template variables
              are from the set of ANSI codes in this module.
  """

  if file.isatty() and has_color:
    print(map_string(msg, ANSI_MAP))
  else:
    print(map_string(msg))



if __name__ == '__main__':
  writeout('${BG_WHITE}${BLACK}This is black${RESET}')
  writeout('${RED}This is red${RESET}')
  writeout('${GREEN}This is green${RESET}')
  writeout('${YELLOW}This is yellow${RESET}')
  writeout('${BLUE}This is blue${RESET}')
  writeout('${MAGENTA}This is magenta${RESET}')
  writeout('${CYAN}This is cyan${RESET}')
  writeout('${WHITE}This is white${RESET}')
  writeout('${DEFAULT}This is default${RESET}')
  writeout('${BG_WHITE}${BRIGHT_BLACK}This is bright black${RESET}')
  writeout('${BRIGHT_RED}This is bright red${RESET}')
  writeout('${BRIGHT_GREEN}This is bright green${RESET}')
  writeout('${BRIGHT_YELLOW}This is bright yellow${RESET}')
  writeout('${BRIGHT_BLUE}This is bright blue${RESET}')
  writeout('${BRIGHT_MAGENTA}This is bright magenta${RESET}')
  writeout('${BRIGHT_CYAN}This is bright cyan${RESET}')
  writeout('${BRIGHT_WHITE}This is bright white${RESET}')
  writeout('${BRIGHT_DEFAULT}This is bright default${RESET}')
  writeout('${BG_BLACK}This is a black background${RESET}')
  writeout('${BG_RED}This is a red background${RESET}')
  writeout('${BG_GREEN}This is a green background${RESET}')
  writeout('${BG_YELLOW}This is a yellow background${RESET}')
  writeout('${BG_BLUE}This is a blue background${RESET}')
  writeout('${BG_MAGENTA}This is a magenta background${RESET}')
  writeout('${BG_CYAN}This is a cyan background${RESET}')
  writeout('${BG_WHITE}${BLACK}This is a white background${RESET}')
  writeout('${BG_DEFAULT}This is a default background${RESET}')

