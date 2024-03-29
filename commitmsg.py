#!/usr/bin/env python3
#
# This is a simple script to generate commit messages formatted in the way
# the PostgreSQL projects prefer them. Anybody else is of course also
# free to use it..
#
# Note: the script (not surprisingly) uses the git commands in pipes, so git
# needs to be available in the path.
#
# Copyright (C) 2010-2018 PostgreSQL Global Development Group
# Author: Magnus Hagander <magnus@hagander.net>
#
# Released under the PostgreSQL license
#

#
# The script is configured by having a file named commitmsg.ini in the same
# directory as the script, with the following format:
#
# [commitmsg]
# destination = somewhere@somewhere.com
# fallbacksender = somewhere@somewhere.com
# forcesenderaddr = somewhere@somewhere.com
# forcesendername = Some Git Repository
# subject = pgsql: $shortmsg
# gitweb = http://git.postgresql.org/gitweb?p=postgresql.git;a=$action;h=$commit
# debug = 0
# commitmsg = 1
# tagmsg = 1
# branchmsg = 1
# pingurl = http://somewhere.com/git_repo_updated
#
# Expansion variables are available for the following fields:
#  subject   -  shortmsg
#  gitweb    -  action, commit
#
# destination      is the address to send commit messages to. Multiple addresses can
#                  be specified with a comma in between, in which case multiple
#                  independent messages will be sent.
# fallbacksender   is the sender address to use for activities which don't have an
#                  author, such as creation/removal of a branch.
# forcesenderaddr  is the email address to use as sender of email, when an author can
#                  be found. In this case the name of the sender will be taken from
#                  the commit record, but the address is forced to the one specified
#                  here (to ensure DKIM compliance)
# forcesendername  is the name to use as the sender, instead of the committer name.
#                  Use $committer to inject the original name of the committer in the string.
# replyto          is a comma separated list of addresses to add as reply-to.
#                  Use $committer to insert the email address of the committer (if one exists)
# subject          is the subject of the email
# gitweb           is a template URL for a gitweb link
# debug            set to 1 to output data on console instead of sending email
# commitmsg        set to 0 to disable generation of commit mails
# tagmsg           set to 0 to disable generation of tag creation mails
# branchmsg        set to 0 to disable generation of branch creation mails
# excludebranches  exclude commit messages if they are made on specified comma-separate list
#                  of branches.
# includediff      include the diff of the commit (up to 500 lines) at the end of the message
# attacharchive    set to 1 to attach a complete .tar.gz file of the entire branch
#                  that a commit was made on to the email. Only use this if the git
#                  repository is small!!!
# pingurl          when set to something, a http POST will be made to the
#                  specified URL whenever run. Note that unlike some more
#                  advanced git hooks, we just make an empty POST, we don't
#                  (currently) include any information about what's in the pack.
#                  If $branch is included in the URL, insert the branchname in
#                  that position, and if multiple branches are pushed then ping
#                  all of them.
#


import sys
import os.path
from subprocess import Popen, PIPE
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.header import Header
from email.utils import formataddr, parseaddr
from email import encoders
import email.utils
import smtplib
from configparser import ConfigParser
import requests

cfgname = "%s/commitmsg.ini" % os.path.dirname(sys.argv[0])
if not os.path.isfile(cfgname):
    raise Exception("Config file '%s' is missing!" % cfgname)
c = ConfigParser()
c.read(cfgname)

# Figure out if we should do debugging
try:
    debug = c.getboolean('commitmsg', 'debug', fallback=False)
except Exception as e:
    print("Except: %s" % e)
    debug = True


def should_send_message(msgtype):
    """
    Determine if a specific message type should be sent, by looking
    in the ini file. Unless specifically disabled, all types are
    sent.
    """
    try:
        sendit = int(c.get('commitmsg', '%smsg' % msgtype))
        if sendit == 0:
            return False
        return True
    except Exception as e:
        return True


allmail = []
allbranches = []


def reencode_mail_address(m):
    (name, email) = parseaddr(m)

    if name:
        return formataddr((str(Header(name, 'utf-8')), email))
    else:
        return email


def sendmail(text, sender, subject, archive=None):
    if not c.has_option('commitmsg', 'destination'):
        return

    if c.has_option('commitmsg', 'replyto'):
        pieces = []
        for p in c.get('commitmsg', 'replyto').split(','):
            pp = p.strip()
            if pp == '$committer':
                if sender:
                    pieces.append(sender.strip())
                # Don't add fallback sender as committer
            else:
                pieces.append(pp)
        replyto = ', '.join(pieces)
    else:
        replyto = None

    if not sender:
        # No sender specified, so use fallback
        sender = c.get('commitmsg', 'fallbacksender')

    (sender_name, sender_address) = email.utils.parseaddr(sender)

    if c.has_option('commitmsg', 'forcesenderaddr'):
        sender_address = c.get('commitmsg', 'forcesenderaddr')

    if c.has_option('commitmsg', 'forcesendername'):
        sender_name = c.get('commitmsg', 'forcesendername').replace('$committer', sender_name)

    if sender_name:
        fullsender = "{0} <{1}>".format(sender_name, sender_address)
    else:
        fullsender = sender_address

    for m in c.get('commitmsg', 'destination').split(','):
        msg = MIMEMultipart()
        msg['From'] = reencode_mail_address(fullsender)
        msg['To'] = m
        msg['Subject'] = subject
        if replyto:
            msg['Reply-To'] = replyto
        msg['X-Auto-Response-Suppress'] = 'All'
        msg['Auto-Submitted'] = 'auto-generated'

        # Don't specify utf8 when doing debugging, because that will encode the output
        # as base64 which is completely useless on the console...
        if debug:
            msg.attach(MIMEText(text))
        else:
            msg.attach(MIMEText(text, _charset='utf-8'))

        if archive:
            part = MIMENonMultipart('application', 'x-gzip')
            part.set_payload(archive)
            part.add_header('Content-Disposition', 'attachment; filename="archive.tar.gz"')
            encoders.encode_base64(part)
            msg.attach(part)

        allmail.append({
            'sender': sender_address,
            'to': m,
            'msg': msg,
        })


def flush_mail():
    """
    Send off an email using the local sendmail binary.
    """

    # Need to reverse list to make sure we send the emails out in the same
    # order as the commits appeared. They'll usually go out at the same time
    # anyway, but if they do get different timestamps, we want them in the
    # correct order.
    for msg in reversed(allmail):
        if debug:
            print(msg['msg'])
        else:
            smtp = smtplib.SMTP("localhost")
            smtp.sendmail(msg['sender'], msg['to'], msg['msg'].as_string().encode('utf8'))
            smtp.close()


def parse_commit_log(do_send_mail, lines):
    """
    Parse a single commit off the commitlog, which should be in an array
    of lines, generate a commit message, and send it.

    The order of the array must be reversed.

    The contents of the array will be destroyed.
    """

    if len(lines) == 0:
        return False

    # Reset our parsing data
    commitinfo = ""
    authorinfo = ""
    committerinfo = ""
    mergeinfo = ""
    while True:
        l = lines.pop().decode('utf8', errors='ignore').strip()
        if l == "":
            break
        elif l.startswith("commit "):
            commitinfo = l
        elif l.startswith("Author: "):
            authorinfo = l
        elif l.startswith("Commit: "):
            committerinfo = l
        elif l.startswith("Merge: "):
            mergeinfo = l
        else:
            raise Exception("Unknown header line: %s" % l)

    if not (commitinfo or authorinfo):
        # If none of these existed, we must've hit the end of the log
        return False
    # Check for any individual piece that is missing
    if not commitinfo:
        raise Exception("Could not find commit hash!")
    if not authorinfo:
        raise Exception("Could not find author!")
    if not committerinfo:
        raise Exception("Could not find committer!")

    commitmsg = []
    # We are in the commit message until we hit one line that doesn't start
    # with four spaces (commit message).
    while len(lines):
        l = lines.pop().decode('utf8', errors='ignore')
        if l.startswith("    "):
            # Remove the 4 leading spaces and any trailing spaces
            commitmsg.append(l[4:].rstrip())
        else:
            break  # something else means start of stats section

    diffstat = []
    while len(lines):
        ll = lines.pop()
        l = ll.decode('utf8', errors='ignore')
        if l.strip() == "":
            break
        if not l.startswith(" "):
            # If there is no starting space, it means there were no stats rows,
            # and we're already looking at the next commit. Put this line back
            # on the list and move on
            lines.append(ll)
            break
        diffstat.append(l.strip())

    # Figure out affected branches
    p = Popen("git branch --contains %s" % commitinfo[7:], shell=True, stdout=PIPE)
    branches = [b.decode('utf8', errors='ignore').strip(" *\r\n") for b in p.stdout.readlines()]
    p.stdout.close()
    allbranches.extend(branches)

    # We have now collected all data. If we're not going to actually send the mail,
    # now is the time to bail.
    if not do_send_mail:
        return True

    if c.has_option('commitmsg', 'excludebranches'):
        for branchmatch in branches:
            if branchmatch in [b.strip() for b in c.get('commitmsg', 'excludebranches').split(',')]:
                print("Not sending commit message for excluded branch {}".format(branches[0]))
                return True

    # Everything is parsed, put together an email
    mail = []
    mail.extend(commitmsg)
    mail.append("")
    if c.has_option('commitmsg', 'forcesendername'):
        # If the sender name is changed, put the committer info in the contents
        # of the mail.
        mail.append("Committer: {}".format(committerinfo[7:]))
        mail.append("")
    if len(branches) > 1:
        mail.append("Branches")
        mail.append("--------")
    else:
        mail.append("Branch")
        mail.append("------")
    mail.append("\n".join(branches))
    mail.append("")
    if c.has_option('commitmsg', 'gitweb') or committerinfo[7:] != authorinfo[7:]:
        mail.append("Details")
        mail.append("-------")
        if c.has_option('commitmsg', 'gitweb'):
            mail.append(
                c.get('commitmsg', 'gitweb').replace('$action', 'commitdiff').replace('$commit', commitinfo[7:]))
        if committerinfo[7:] != authorinfo[7:]:
            mail.append(authorinfo)  # already includes Author: part
        mail.append("")
    mail.append("Modified Files")
    mail.append("--------------")
    mail.extend(diffstat)
    mail.append("")
    mail.append("")

    if c.has_option('commitmsg', 'includediff') and c.get('commitmsg', 'includediff') == '1':
        # Include the full diff, up to 500 lines.
        mail.append("Changes")
        mail.append("--------------")
        p = Popen("git diff {}^..{}".format(commitinfo[7:], commitinfo[7:]), shell=True, stdout=PIPE)
        for l in p.stdout.read().splitlines():
            mail.append(l.decode('utf8', errors='ignore'))
        p.stdout.close()

    if len(branches) == 1 and c.has_option('commitmsg', 'attacharchive') and c.get('commitmsg', 'attacharchive') == '1':
        # Archive the branch to a .tar.gz and send it (this is probably really
        # slow on big archives, but that's not what it's supposed to be used for)
        p = Popen("git archive %s | gzip -9" % branches[0], shell=True, stdout=PIPE)
        archive = p.stdout.read()
        p.stdout.close()
    else:
        archive = None

    sendmail(
        "\n".join(mail),
        committerinfo[7:],
        c.get('commitmsg', 'subject').replace("$shortmsg",
                                              commitmsg[0][:80 - len(c.get('commitmsg', 'subject'))]),
        archive,
    )
    return True


def parse_annotated_tag(lines):
    """
    Parse a single commit off the commitlog, which should be in an array
    of lines, generate a commit message, and send it.

    The contents of the array will be destroyed.
    """
    if len(lines) == 0:
        return

    if not lines[0].startswith('tag'):
        raise Exception("Tag message does not start with tag!")
    tagname = lines[0][4:].strip()

    if not lines[1].startswith('Tagger: '):
        raise Exception("Tag message does not contain tagger!")
    author = lines[1][8:].strip()

    if not lines[2].startswith('Date:   '):
        raise Exception("Tag message does not contain date!")
    if not lines[3].strip() == "":
        raise Exception("Tag message does not contian message separator!")

    mail = []
    mail.append('Tag %s has been created.' % tagname)
    mail.append("View: %s" % (
        c.get('commitmsg', 'gitweb').replace('$action', 'tag').replace('$commit', 'refs/tags/%s' % tagname))
    )
    mail.append("")
    mail.append("Log Message")
    mail.append("-----------")

    for i in range(4, len(lines)):
        if lines[i].strip() == '':
            break
        mail.append(lines[i].rstrip())

    # Ignore the commit it's referring to here
    sendmail("\n".join(mail),
             author,
             c.get('commitmsg', 'subject').replace('$shortmsg', 'Tag %s has been created.' % tagname))
    return


if __name__ == "__main__":
    # Get a list of refs on stdin, do something smart with it
    do_send_mail = c.has_option('commitmsg', 'destination')

    while True:
        l = sys.stdin.readline()
        if not l:
            break

        (oldobj, newobj, ref) = l.split()

        # Build the email
        if oldobj == "".zfill(40):
            # old object being all zeroes means a new branch or tag was created
            if ref.startswith("refs/heads/"):
                # It's a branch!
                if not do_send_mail:
                    continue
                if not should_send_message('branch'):
                    continue

                branchname = ref.replace('refs/heads/', '')
                if c.has_option('commitmsg', 'gitweb'):
                    gwstr = "View: %s" % (
                        c.get('commitmsg', 'gitweb').replace('$action', 'shortlog').replace('$commit', ref),
                    )
                else:
                    gwstr = ""

                sendmail(
                    "Branch %s was created.\n\n%s" % (branchname, gwstr),
                    None,
                    c.get('commitmsg', 'subject').replace("$shortmsg",
                                                          "Branch %s was created" % branchname)
                )
                allbranches.append(branchname)
            elif ref.startswith("refs/tags/"):
                # It's a tag!
                # It can be either an annotated tag or a lightweight one.
                if not do_send_mail:
                    continue
                if not should_send_message('tag'):
                    continue

                p = Popen("git cat-file -t %s" % ref, shell=True, stdout=PIPE)
                t = p.stdout.read().strip()
                p.stdout.close()
                if t == b"commit":
                    # Lightweight tag with no further information
                    sendmail("Tag %s was created.\n" % ref,
                             None,
                             c.get('commitmsg', 'subject').replace("$shortmsg",
                                                                   "Tag %s was created" % ref))
                elif t == b"tag":
                    # Annotated tag! Get the description!
                    p = Popen("git show %s" % ref, shell=True, stdout=PIPE)
                    lines = p.stdout.readlines()
                    p.stdout.close()
                    parse_annotated_tag([l.decode('utf8', errors='ignore') for l in lines])
                else:
                    raise Exception("Unknown tag type '%s'" % t)
            else:
                raise Exception("Unknown branch/tag type %s" % ref)

        elif newobj == "".zfill(40):
            # new object being all zeroes means a branch was removed
            if not do_send_mail:
                continue
            if not should_send_message('branch'):
                continue

            sendmail("Branch %s was removed." % ref,
                     None,
                     c.get('commitmsg', 'subject').replace("$shortmsg",
                                                           "Branch %s was removed" % ref))
        else:
            # If both are real object ids, we can call git log on them
            if not should_send_message('commit'):
                continue

            cmd = "git log %s..%s --stat --pretty=full" % (oldobj, newobj)
            p = Popen(cmd, shell=True, stdout=PIPE)
            lines = p.stdout.readlines()
            lines.reverse()
            while parse_commit_log(do_send_mail, lines):
                pass

    flush_mail()

    # Send of a http POST ping if there is something changed
    if c.has_option('commitmsg', 'pingurl'):
        pingurls = []
        # First build a list of all the URLs to ping, there could
        # be more than one.
        for pingurl in c.get('commitmsg', 'pingurl').split(' '):
            if pingurl.find('$branch') >= 0:
                # Branch is included, possibly send multiple
                for b in set(allbranches):
                    pingurls.append(pingurl.replace('$branch', b))
            else:
                pingurls.append(pingurl)

        # Then actuall ping them all
        for pingurl in pingurls:
            # Make a http POST (the empty content makes it a POST)
            # We ignore what the result is, so we also ignore any exceptions.
            try:
                r = requests.post(pingurl)
                if r.status_code == 200:
                    for l in r.text.splitlines():
                        print("PING: {0}".format(l))
                else:
                    print("ERROR: status {0} {1} from ping!".format(r.status_code, r.reason))
                    if r.headers['content-type'].split(';')[0] == 'text/plain':
                        for l in r.text.splitlines():
                            print("ERROR: {0}".format(l))
                    else:
                        print("ERROR: message is in '{}' format, not including".format(r.headers['content-type']))
            except Exception as e:
                print("ERROR: Exception when pinging!")
