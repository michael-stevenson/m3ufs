#!/usr/bin/env python

import logging
import argparse
import pathlib
import os
import fuse
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
from stat import S_IFDIR, S_IFREG

class M3UFS(LoggingMixIn, Operations):

    def wrapped(self, original):
        def _wrapped(path, *args):
            if path == self.internal_path:
                return original(self.external_path, *args)
            return original(self.repath(path), *args)
        return _wrapped

    def repath(self, path):

        if path == self.internal_path:
            return self.internal_path

        if self.args.strip_prefix:
            path = self.args.strip_prefix + path

        return path

    def __init__(self, args):

        self.external_path = args.m3u
        self.name = pathlib.Path(self.external_path).parts[-1]
        self.internal_path = "/" + self.name
        self.args = args

        if self.args.emulated_m3u:
            with open(self.external_path, 'r') as playlist:
                self.data = playlist.read()
                if self.args.strip_prefix:
                    self.data = self.data.replace("\n{}/".format(self.args.strip_prefix), "\n")

        self.chmod = self.wrapped(os.chmod)
        self.chown = self.wrapped(os.chown)
        self.readlink = self.wrapped(os.readlink)
        self.getxattr = None
        self.listxattr = None
        self.mkdir = self.wrapped(os.mkdir)
        self.mknod = self.wrapped(os.mknod)
        self.open = self.wrapped(os.open)

    def _get_entries(self):
        
        files = list()
        with open(self.external_path, 'r') as f:
            for line in f.readlines():
                logging.debug(line)
                if line.lstrip()[0] == '#':
                    continue
                if self.args.strip_prefix:
                    line = line[len(self.args.strip_prefix):]
                line = line.rstrip()
                files.append(line)
        return files

    def _get_listing(self, path):

        entries = [ x for x in self._get_entries() if x.startswith(path) ]
        depth = len(pathlib.Path(path).parts)

        listing = [ pathlib.Path(p).parts[depth] for p in entries ]
        listing.append('.')
        listing.append('..')

        if depth == 1 and self.args.emulated_m3u:
            listing.append(self.name)

        return set(listing)

    def __call__(self, op, path, *args):
        return super(M3UFS, self).__call__(op, path, *args)

    def readdir(self, path, fh):
        return self._get_listing(path)

    def getattr(self, path, fh = None):

        if path == self.internal_path:
            st = os.lstat(self.args.strip_prefix)
            stats = dict((key, getattr(st, key)) for key in (
                'st_atime', 'st_ctime', 'st_gid', 'st_mode',
                'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
            stats['st_mode'] |= S_IFREG
            stats['st_mode'] ^= S_IFDIR
            return stats

        path = self.repath(path)
        logging.debug("getattr: {p}".format(p = path))

        st = os.lstat(path)
        return dict((key, getattr(st, key)) for key in (
            'st_atime', 'st_ctime', 'st_gid', 'st_mode',
            'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    def read(self, path, size, offset, fh):
        logging.debug("read: {p} {s} {o} {fh}".format(p = path, s = size,
            o = offset, fh = fh))

        if path == self.internal_path:
            return self.data[offset:offset+size].encode('utf-8')

        path = self.repath(path)
        os.lseek(fh, offset, 0)
        return os.read(fh, size)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--m3u", type=str, help = "The file to mirror", required = True)
    parser.add_argument("--mountpoint", type=str, help = "mountpoint", required = True)
    parser.add_argument("--strip_prefix", type=str, default = None, help = "The leading path within the m3u file that should be stripped")
    parser.add_argument("--emulated_m3u", action = 'store_true', help = "Whether to generate an m3u within the mountpoint that mimics the original")
    args = parser.parse_args()

    if args.strip_prefix:
        args.emulated_m3u = True

    logging.basicConfig(level = logging.DEBUG)
    fuse = FUSE(M3UFS(args), args.mountpoint, foreground=True, allow_other=False)
