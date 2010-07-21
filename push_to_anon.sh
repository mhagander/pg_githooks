#!/bin/bash

#
# This script is used to push changes from gitmaster to the anonymous
# mirror. It's designed to be run (very frequently) from cron, and will
# run as soon as there are any refs that are newer than the last pull.
#
#
# Copyright (C) 2010 PostgreSQL Global Development Group
# Author: Magnus Hagander <magnus@hagander.net>
#
# Released under the PostgreSQL license
#
#
#
# Can be run with --force to push even if nothing appears to have
# changed.
#
# The git repository should have a remote called "anonymous" configured.
# All branches will be pushed.
#

if [ "$1" == "" ]; then
    echo "Usage: push_to_anon.sh <path to git repository> [--force]"
    exit 1
fi

set -e

cd $1
M=$(find refs -type f -newer last_anonymous_push | grep -v refs/remotes/ | wc -l)
if [ $M -gt 0 -o "$2" == "--force" ]; then
    # Perform push in interlock
    if [ ! -e /tmp/.git_repo_push.lck ]; then
	trap "rm -f /tmp/.git_repo_push.lck" INT TERM EXIT
	touch /tmp/.git_repo_push.lck
	touch last_anonymous_push
	git push anonymous --all >/dev/null
	git push anonymous --tags >/dev/null
	rm -f /tmp/.git_repo_push.lck
	trap - INT TERM EXIT
    else
	echo Push script already running.
    fi
fi
