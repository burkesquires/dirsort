#!/usr/bin/env python
# -*- coding: utf-8 -*-

# (C) 2010, Taher Shihadeh <taher@unixwars.com>
# Licensed: GPL v2.        http://unixwars.com

import operator
import optparse
import os
import re
import shutil
import string
import sys

__author__  = 'Taher Shihadeh <taher@unixwars.com>'
__version__ = '1.0'
USAGE       = '%prog [options] paths'
EPILOG      = 'Report bugs to taher@unixwars.com'

NEW_DIR_SEP = '_' # Separator used for parts of new directory names
REGEXES     = ['\[.*?\]' , '\(.*?\)',# strings in brackets or parens
               's\d{1,2}[ex]\d{1,2}',# episode numbers
               '\d{3,4}x\d{3,4}',    # video resolutions
               '\d+',                # numbers
               ]
SEP         = """ _-+~.·:;·()[]¡!¿?<>"'`""" # word separators
STRINGS     = ['dvd', 'bdrip', 'dvdrip', 'xvid', 'divx', 'x264',
               'h264', 'aac', 'mp3', 'ova', 'hdtv', 'vtv', 'notv',
               '2hd', 'hd', '720p' '1080p', 'lol', 'fqm', 'oav',
               'episode', 'season', 'volume', 'vol', 'volumen',
               'extra','episodio', 'temporada'] # lowercase

class Entry (dict):
    """Model for entries"""

    __getattr__= dict.__getitem__
    __setattr__= dict.__setitem__
    __delattr__= dict.__delitem__

    regex      = '|'.join (REGEXES)
    trans      = string.maketrans (SEP, ' '*len(SEP))
    del_set    = set([s.lower() for s in STRINGS])

    def __init__ (self, *args):
        assert len(args) <= 3

        self.dir = False
        if len(args) == 1:
            tmp = self.__from_str (args[0])
            self.path = tmp['path']
            self.name = tmp['name']
            self.dir  = tmp['dir']

        elif len(args) > 1:
            self.path = args[0]
            self.name = ['',args[1]][bool(args[1])]
        if len(args) == 3:
            self.dir  = args[2]

    def process (self):
        """Cleanup and divide entry's name down to comparable components"""
        tmp = self.name.lower()

        if self.dir == False:
            tmp, _ = os.path.splitext (tmp)

        # Remove regex matches, split, and disregard unwanted strings
        tmp = re.sub (self.regex, ' ', tmp)
        tmp = tmp.translate(self.trans).split()
        keep = set(tmp).difference(self.del_set)

        return filter(None, keep)

    def __str__ (self):
        p,n = self['path'], self['name']
        pn  = os.path.normpath(os.path.join(p,n))
        if self.dir:
            pn += os.path.sep
        return pn

    def __from_str (self, entry_str):
        is_dir     = bool (entry_str[-1] == os.path.sep)
        entry_str  = os.path.normpath (entry_str)
        path   = os.path.dirname  (entry_str)
        name   = os.path.basename (entry_str)

        return {'path':path, 'name':name, 'dir':is_dir}


class Sorter:
    """Class to sort according to similarity factor"""
    def __init__ (self, options, paths):
        assert type(paths) == list
        self.options = options
        self.paths   = paths
        self.entries = self._get_entries ()
        self.results = []

    def __call__ (self):
        if not self.results:
            self._run()
        return self.results

    def _get_entries (self):
        entries = []
        for path in self.paths:
            listdir = os.listdir (path)

            for x in listdir:
                is_dir = os.path.isdir (os.path.join(path, x))
                entries.append (Entry(path, x, is_dir))
        return entries

    def _compare (self, entry1, entry2):
        """Return similarity factor as percentage"""
        aux1    = entry1.process()
        aux2    = entry2.process()
        set_or  = set(aux1) | set(aux2)
        set_and = set(aux1) & set(aux2)
        return (float(len(set_and)) / float(len(set_or)))*100

    def _run (self):
        entries = self.entries[:]
        total   = float(len(entries))
        count   = 0

        for x in self.entries:
            for y in entries:
                if x == y:
                    continue # Don't compare with itself
                if self.options.prefix == None and all((not x['dir'], not y['dir'])):
                    continue # Skip file-file comparison if possible
                if self.options.dirs == False and all((x['dir'],y['dir'])):
                    continue # Skip dir-dir comparison if possible

                result = {'x':x, 'y':y, 'factor': self._compare (x,y) }
                self.results.append(result)

            entries.remove(x)# No need to compare it on both lists
            count += 1
            print >> sys.stderr, '\rAnalyzing.. %.2f%%' %(min(100.00,(count/total)*200)),

        print >> sys.stderr, ''
        self.results = sorted(self.results, key=operator.itemgetter('factor'), reverse=True)


class Mover:
    """Class to move files/dirs according to similarity factor"""
    def __init__ (self, options, results):
        self.options  = options
        self.results  = results
        self.used_src = []
        self.log      = []
        self.no_dir   = []
        self.sets     = []
        self._run()

    def _run (self):
        threshold = self.options.factor
        for result in self.results:
            x,y,factor = result['x'],result['y'],result['factor']

            if factor < threshold:
                break
            if   all([x['dir'], y['dir']]):
                self._merge_dirs (x,y,factor)
            elif any([x['dir'], y['dir']]):
                self._move_file (x,y,factor)
            else:
                self.no_dir.append ((x,y,factor))

        self._make_dirs()

    def __call__ (self):
        return self._report()

    def _report (self):
        for src,dst,status in self.log:
            print '%s\t%s --> %s'%(['Fail','OK'][status], str(src), str(dst))

    def _register_operation (self, x, y, status):
        assert not x in self.used_src, 'Source already processed'

        self.used_src.append(x)
        self.log.append ((x,y,status))

    def _confirm (self, src, dst, factor):
        if factor < self.options.factor:
            value, opt = False, 'y/N'
        else:
            value, opt = True, 'Y/n'

        if self.options.ask:
            question = '[%.2f%%] %s --> %s\nConfirm? [%s] ' %(factor, str(src), str(dst), opt)

            while True:
                answer = raw_input (question)
                if answer.lower() == 'y':
                    value = True
                    break
                elif answer.lower() == 'n':
                    value = False
                    break
                elif answer == '':
                    break

        return value

    def _move_file (self, x, y, factor):
        assert not all([x['dir'], y['dir']])

        if x['dir']:
            x,y = y,x

        if x in self.used_src:
            return

        src = os.path.join (x['path'], x['name'])
        dst = os.path.join (y['path'], y['name'])

        if not self._confirm (x, y, factor):
            return

        status = False
        if not self.options.demo:
            try:
                shutil.move (src, dst)
                status = True
            except:
                pass

        self._register_operation (x,y,status)

    def _merge_dirs (self, x, y, factor):
        assert all([x['dir'], y['dir']])

        if x in self.used_src:
            return

        if not self._confirm (x, y, factor):
            return

        src_pre = str(x)
        dst     = str(y)

        if self.options.demo:
            status = False
        else:
            status = True

        for e in os.listdir (src_pre):
            if status == False:
                break
            try:
                src = os.path.normpath (os.path.join(src_pre,e))
                shutil.move (src, dst)
            except:
                status = False

        if status == True:
            try:
                os.removedirs (src_pre)
            except:
                status = False

        self._register_operation (x,y,status)

    def _make_dirs (self):
        if not self.no_dir:
            return

        self.__create_sets ()

        for s in self.sets:
            dst = self.__process_set (s)
            if not self.options.demo:
                try:
                    os.makedirs (str(dst))
                except:
                    pass

            lst = list(s)
            for e_str in lst:
                e = Entry (e_str)
                self._move_file (e, dst, self.options.factor)

    # Helpers for __make_dirs
    def __create_sets (self):
        for x,y,factor in self.no_dir:
            if x in self.used_src or y in self.used_src:
                continue

            x_set = self.__in_set (x)
            y_set = self.__in_set (y)

            if x_set and y_set:
                continue
            elif x_set:
                self.__add_to_set (y, x_set)
            elif y_set:
                self.__add_to_set (x, y_set)
            else:
                self.__create_set (x, y)

    def __in_set (self, entry):
        """Return candidate set to which an entry belongs, if any"""
        for s in self.sets:
            if str(entry) in s:
                return s

    def __add_to_set (self, entry, s):
        s.update(set([str(entry)]))

    def __create_set (self, x, y):
        self.sets.append (set([str(x), str(y)]))

    def __process_set (self, s):
        """Infere a target-entry for the set"""
        entry_lst   = [Entry(x) for x in list(s)]
        parts       = [x.process() for x in entry_lst]
        pieces      = min (parts, key=len)
        idx         = parts.index (pieces)
        entry       = entry_lst[idx]
        name_pieces = entry.name.translate (entry.trans).split()

        if self.options.prefix:
            dir_pieces = [self.options.prefix]
        else:
            dir_pieces  = []

        for p in name_pieces:
            if p.lower() in pieces:
                dir_pieces.append (p)

        path     = entry_lst[0]['path']
        dir_name = NEW_DIR_SEP.join(dir_pieces)

        # Just in case there is a file with that name
        if os.path.isfile (os.path.join (path, dir_name)):
            dir_name = self.__cycle_name (path, dir_name)

        return Entry (path, dir_name, True)

    def __cycle_name (self, path, dir_name):
        suffix   = 0
        while True:
            if not os.path.isfile ('%s%s%s' %(os.path.join (path, dir_name), NEW_DIR_SEP, suffix)):
                break
            suffix += 1
        return NEW_DIR_SEP.join ([dir_name, str(suffix)])



def main():
    parser = optparse.OptionParser (USAGE, epilog=EPILOG)
    parser.add_option("-s", "--simulate",
                      action="store_true", dest="demo", default=False,
                      help="No-act. Perform simulation")
    parser.add_option("-d", "--directories",
                      action="store_true", dest="dirs", default=False,
                      help="Merge directories if appropriate")
    parser.add_option("-y", "--yes",
                      action="store_false", dest="ask",  default=True,
                      help="Assume Yes to all queries and do not prompt")
    parser.add_option("-f", "--factor", type="float",  dest="factor", default=50.0,
                      help="Similarity threshold. By default, a minimun of 50% similarity is required before taking action")
    parser.add_option("-p", "--prefix", dest="prefix", default=None,
                      help="If needed, create new directories beginning with given prefix. You can specify '' or \"\" if you want to create new directories without prefix")

    (options, args) = parser.parse_args()

    for arg in args:
        if not os.path.isdir (arg):
            print >> sys.stderr, 'Argument "%s" is not a directory.'%(arg)
            sys.exit(1)

    if args == []:
        args.append (os.getcwd())

    sorter = Sorter (options, args)
    mover  = Mover (options, sorter())
    mover()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print ''
