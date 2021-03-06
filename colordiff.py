#!/usr/bin/env python
# Copyright (C) 2006 Aaron Bentley <aaron@aaronbentley.com>
# Copyright (C) 2016 Piers Titus van der Torren <pierstitus@gmail.com>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# Based on colordiff from bzrtools

import re
import sys
import os

from difflib import SequenceMatcher

import terminal

class LineParser(object):
    def parse_line(self, line):
        if line.startswith("@"):
            return "diffstuff"
        elif line.startswith("+++ ") or line.startswith("--- "):
            return "metaline"
        elif line.startswith("+"):
            return "newtext"
        elif line.startswith("-"):
            return "oldtext"
        elif line.startswith(" "):
            return "plain"
        else:
            return "plain"


class DiffWriter(object):

    def __init__(self, target, check_style=False, color='always'):
        self.target = target
        self.lp = LineParser()
        self.oldtext_hold = None
        self.chunks = []
        self.color = 'always' == color or ('auto' == color and terminal.has_ansi_colors())
        if self.color:
            self.colors = {
                'metaline':      'white',
                'plain':         None,
                'newtext':       'darkgreen',
                'oldtext':       'darkred',
                'newsame':       'darkyellow',
                'oldsame':       'darkyellow',
                'diffstuff':     'darkcyan',
                'trailingspace': 'red',
                'leadingtabs':   'magenta',
                'longline':      'white',
            }
            self._read_colordiffrc('/etc/colordiffrc')
            self._read_colordiffrc(os.path.expanduser('~/.colordiffrc'))
        else:
            self.colors = {
                'metaline':      None,
                'plain':         None,
                'newtext':       None,
                'oldtext':       None,
                'diffstuff':     None,
                'trailingspace': None,
                'leadingtabs':   None,
                'longline':      None,
            }
        self.added_leading_tabs = 0
        self.added_trailing_whitespace = 0
        self.spurious_whitespace = 0
        self.long_lines = 0
        self.max_line_len = 79
        self._new_lines = []
        self._old_lines = []
        self.check_style = check_style

    def _read_colordiffrc(self, path):
        try:
            f = open(path, 'r')
        except IOError:
            return

        for line in f.readlines():
            try:
                key, val = line.split('=')
            except ValueError:
                continue

            key = key.strip()
            val = val.strip()

            if val in ('none', 'normal', 'off'):
                val = None
            else:
                tmp = val
                if val.startswith('dark'):
                    tmp = val[4:]
                if tmp not in terminal.colors:
                    continue

            self.colors[key] = val

    def colorstring(self, type, line, bgcolor_if_space=False, bgcolor=None):
        color = self.colors[type]
        if color is not None:
            if ('newtext' == type or 'newsame' == type) and line.endswith('\n'):
                bad_ws_match = re.match(r'^(.*?)([\t ]+)(\r?\n)$',
                                        line)
                if bad_ws_match:
                    return ''.join(terminal.colorstring(txt, color, bcol)
                        for txt, bcol in (
                            (bad_ws_match.group(1), bgcolor),
                            (bad_ws_match.group(2), self.colors['trailingspace'])
                        )) + bad_ws_match.group(3)
            elif 'diffstuff' == type:
                diffstuff_match = re.match(r'^(@@[^@]*@@)(.*\r?\n)$',
                                        line)
                if diffstuff_match:
                    return (terminal.colorstring(diffstuff_match.group(1), color)
                            + diffstuff_match.group(2))
            elif bgcolor_if_space and line.isspace() and not line.endswith('\n'):
                bgcolor = color
            return terminal.colorstring(str(line), color, bgcolor)
        else:
            return str(line)

    def write(self, text):
        newstuff = text.split('\n')
        for newchunk in newstuff[:-1]:
            self.writeline(''.join(self.chunks + [newchunk, '\n']))
            self.chunks = []
        self.chunks = [newstuff[-1]]

    def writelines(self, lines):
        for line in lines:
            self.writeline(line)

    def writeline(self, line):
        if self.color:
            output = []
            line_type = self.lp.parse_line(line)
            if None != self.oldtext_hold:
                if 'newtext' == line_type:
                    output.extend(self.parse_changed_line(self.oldtext_hold, line))
                    self.target.writelines(output)
                    self.oldtext_hold = None
                    return
                else:
                    output.append(self.colorstring('oldtext', self.oldtext_hold))
                self.oldtext_hold = None
            if 'oldtext' == line_type:
                self.oldtext_hold = line
            else:
                output.append(self.colorstring(line_type, line))
            self.target.writelines(output)
        else:
            self.target.writelines(line)

    def flush(self):
        if None != self.oldtext_hold:
            self.target.writelines(self.colorstring('oldtext', self.oldtext_hold))
            self.oldtext_hold = None
        self.target.flush()

    def parse_changed_line(self, oldtext, newtext):
        s = SequenceMatcher(None, oldtext[1:], newtext[1:])
        # only color changes when enough matches found, related to how klondiff tests it
        if sum(m[2] for m in s.get_matching_blocks()) > 0.6 * min(len(oldtext), len(newtext)): #s.quick_ratio() > 0.6 and s.ratio() > 0.6:
            oldtext = oldtext[1:]
            newtext = newtext[1:]
            matches = s.get_matching_blocks()
            # filter matches on minimum length or at least one special character,
            # the last match alway has lenght 0 and must be included too
            matches = [m for m in matches if m[2] == 0 or m[2] >= 4
                       or re.search('[^\w \r\n]', oldtext[m[0]:m[0]+m[2]])]
            old = [self.colorstring('oldtext', '-')]
            new = [self.colorstring('newtext', '+')]
            old.append(self.colorstring('oldtext', oldtext[0:matches[0][0]], bgcolor_if_space=True))
            new.append(self.colorstring('newtext', newtext[0:matches[0][1]], bgcolor_if_space=True))
            for n, m in enumerate(matches[:-1]):
                old.append(self.colorstring('oldsame', oldtext[m[0]:m[0]+m[2]]))
                new.append(self.colorstring('newsame', newtext[m[1]:m[1]+m[2]]))
                old.append(self.colorstring('oldtext', oldtext[m[0]+m[2]:matches[n+1][0]]))
                new.append(self.colorstring('newtext', newtext[m[1]+m[2]:matches[n+1][1]]))
            output = [''.join(old), ''.join(new)]
        else:
            output = [self.colorstring('oldtext', oldtext),
                      self.colorstring('newtext', newtext)]
        return output

    @staticmethod
    def _matched_lines(old, new):
        matcher = patiencediff.PatienceSequenceMatcher(None, old, new)
        matched_lines = sum (n for i, j, n in matcher.get_matching_blocks())
        return matched_lines

    def _analyse_old_new(self):
        if (self._old_lines, self._new_lines) == ([], []):
            return
        if not self.check_style:
            return
        old = [l.contents for l in self._old_lines]
        new = [l.contents for l in self._new_lines]
        ws_matched = self._matched_lines(old, new)
        old = [l.rstrip() for l in old]
        new = [l.rstrip() for l in new]
        no_ws_matched = self._matched_lines(old, new)
        assert no_ws_matched >= ws_matched
        if no_ws_matched > ws_matched:
            self.spurious_whitespace += no_ws_matched - ws_matched
            self.target.write('^ Spurious whitespace change above.\n')
        self._old_lines, self._new_lines = ([], [])


def auto_diff_writer(output):
    return DiffWriter(output, color='auto')


def colordiff(color, check_style, *args, **kwargs):
    real_stdout = sys.stdout
    dw = DiffWriter(real_stdout, check_style, color)
    sys.stdout = dw
    try:
        get_cmd_object('diff').run(*args, **kwargs)
    finally:
        sys.stdout = real_stdout
    if check_style:
        if dw.added_leading_tabs > 0:
            trace.warning('%d new line(s) have leading tabs.' %
                          dw.added_leading_tabs)
        if dw.added_trailing_whitespace > 0:
            trace.warning('%d new line(s) have trailing whitespace.' %
                          dw.added_trailing_whitespace)
        if dw.long_lines > 0:
            trace.warning('%d new line(s) exceed(s) %d columns.' %
                          (dw.long_lines, dw.max_line_len))
        if dw.spurious_whitespace > 0:
            trace.warning('%d line(s) have spurious whitespace changes' %
                          dw.spurious_whitespace)

def main(args):
    real_stdout = sys.stdout
    dw = DiffWriter(real_stdout)
    for line in sys.stdin:
        dw.write(line)

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
