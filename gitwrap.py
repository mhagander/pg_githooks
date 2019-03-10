#!/usr/bin/env python

#
# Simple wrapper around the git commands to ensure that we only speak
# git. Should be referenced in the authorized_keys file.
#
# Copyright (C) 2010 PostgreSQL Global Development Group
# Author: Magnus Hagander <magnus@hagander.net>
#
# Released under the PostgreSQL license
#
# Looks for a config file in the same directory as gitwrap.py called
# gitwrap.ini, containing:
#
# [paths]
# logfile=/some/where/gitwrap.log
# repobase=/some/where/
#

import sys
import os
import os.path
import datetime
import ConfigParser

ALLOWED_COMMANDS = ('git-upload-pack', 'git-receive-pack')


class Logger(object):
    def __init__(self, cfg):
        self.user = "Unknown"
        self.logfile = cfg.get('paths', 'logfile')

    def log(self, message):
        f = open(self.logfile, "a")
        f.write("%s (%s): %s" % (datetime.datetime.now(), self.user, message))
        f.write("\n")
        f.close()

    def setuser(self, user):
        if user:
            self.user = user


class InternalException(Exception):
    pass


class PgGit(object):
    user = None
    command = None
    path = None

    def __init__(self, cfg):
        self.cfg = cfg
        self.logger = Logger(cfg)
        self.repobase = cfg.get('paths', 'repobase')

    def parse_commandline(self):
        if len(sys.argv) != 2:
            raise InternalException("Can only be run with one commandline argument!")
        self.user = sys.argv[1]
        self.logger.setuser(self.user)

    def parse_command(self):
        env = os.environ.get('SSH_ORIGINAL_COMMAND', None)
        if not env:
            raise InternalException("No SSH_ORIGINAL_COMMAND present!")

        # env contains "git-<command> <argument>" or "git <command> <argument>"
        command, args = env.split(None, 1)
        if command == "git":
            subcommand, args = args.split(None, 1)
            command = "git-%s" % subcommand
        if command not in ALLOWED_COMMANDS:
            raise InternalException("Command '%s' not allowed" % command)

        self.command = command
        if not args.startswith("'/"):
            raise InternalException("Expected git path to start with slash!")

        self.path = os.path.normpath("%s/%s" % (self.repobase, args[2:].rstrip("'")))
        if not self.path.startswith(self.repobase):
            raise InternalException("Attempt to escape root directory")
        if not self.path.endswith(".git"):
            raise InternalException("Repository paths must end in .git")
        if not os.path.isdir(self.path):
            raise InternalException("Repository does not exist")

    def run_command(self):
        self.logger.log("Running \"git shell %s %s\"" % (self.command, "'%s'" % self.path))
        os.execvp('git', ['git', 'shell', '-c', "%s %s" % (self.command, "'%s'" % self.path)])

    def run(self):
        try:
            self.parse_commandline()
            self.parse_command()
            self.run_command()
        except InternalException, e:
            try:
                self.logger.log(e)
            except Exception, e:
                pass
            sys.stderr.write("%s\n" % e)
            sys.exit(1)
        except Exception, e:
            try:
                self.logger.log(e)
            except Exception, e:
                # If we failed to log, try once more with a new logger, otherwise,
                # just accept that we failed.
                try:
                    Logger().log(e)
                except:
                    pass
            sys.stderr.write("An unhandled exception occurred on the server\n")
            sys.exit(1)


if __name__ == "__main__":
    c = ConfigParser.ConfigParser()
    c.read("%s/gitwrap.ini" % os.path.abspath(sys.path[0]))
    PgGit(c).run()
