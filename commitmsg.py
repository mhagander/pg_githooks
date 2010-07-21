#!/usr/bin/env python
#
# This is a simple script to generate commit messages formatted in the way
# the PostgreSQL projects prefer them. Anybody else is of course also
# free to use it..
#
# Note: the script (not surprisingly) uses the git commands in pipes, so git
# needs to be available in the path.
#
# Copyright (C) 2010 PostgreSQL Global Development Group
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
# subject = pgsql: $shortmsg
# gitweb = http://git.postgresql.org/gitweb?p=postgresql.git;a=$action;h=$commit
# debug = 0
#
# Expansion variables are available for the following fields:
#  subject   -  shortmsg
#  gitweb    -  action, commit
#
# destination      is the address to send commit messages to.
# fallbacksender   is the sender address to use for activities which don't have an
#                  author, such as creation/removal of a branch.
# subject          is the subject of the email
# gitweb           is a template URL for a gitweb link
# debug            set to 1 to output data on console instead of sending email
#


import sys
import os.path
from subprocess import Popen, PIPE
from email.mime.text import MIMEText
from ConfigParser import ConfigParser

cfgname = "%s/commitmsg.ini" % os.path.dirname(sys.argv[0])
if not os.path.isfile(cfgname):
	raise Exception("Config file '%s' is missing!" % cfgname)
c = ConfigParser()
c.read(cfgname)

# Figure out if we should do debugging
try:
	debug = int(c.get('commitmsg', 'debug'))
except Exception, e:
	print "Except: %s" % e
	debug = 1

allmail = []
def sendmail(msg):
	allmail.append(msg)


def flush_mail():
	"""
	Send off an email using the local sendmail binary.
	"""

	# Need to reverse list to make sure we send the emails out in the same
	# order as the commits appeared. They'll usually go out at the same time
	# anyway, but if they do get different timestamps, we want them in the
	# correct order.
	for msg in reversed(allmail):
		if debug == 1:
			print msg
		else:
			pipe = Popen("sendmail -t", shell=True, stdin=PIPE).stdin
			pipe.write(msg.as_string())
			pipe.close()

			
def create_message(text, sender, subject):
	# Don't specify utf8 when doing a charset, because that will encode the output
	# as base64 which is completely useless on the console...
	if debug == 1:
		msg = MIMEText(text)
	else:
		msg = MIMEText(text, _charset='utf-8')
	msg['To'] = c.get('commitmsg', 'destination')
	msg['From'] = sender
	msg['Subject'] = subject
	return msg

	
def parse_commit_log(lines):
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
	dateinfo = ""
	mergeinfo = ""
	while True:
		l = lines.pop().strip()
		if l == "":
			break
		elif l.startswith("commit "):
			commitinfo = l
		elif l.startswith("Author: "):
			authorinfo = l
		elif l.startswith("Date:   "):
			dateinfo = l
		elif l.startswith("Merge: "):
			mergeinfo = l
		else:
			raise Exception("Unknown header line: %s" % l)

	if not (commitinfo or authorinfo or dateinfo):
		# If none of these existed, we must've hit the end of the log
		return False
	# Check for any individual piece that is missing
	if not commitinfo:
		raise Exception("Could not find commit hash!")
	if not authorinfo:
		raise Exception("Could not find author!")
	if not dateinfo:
		raise Exception("Could not find commit date!")
	
	commitmsg = []
	# We are in the commit message until we hit one line that doesn't start
	# with four spaces (commit message).
	while len(lines):
		l = lines.pop()
		if l.startswith("    "):
			# Remove the 4 leading spaces and any trailing spaces
			commitmsg.append(l[4:].rstrip())
		else:
			break # something else means start of stats section

	diffstat = []
	while len(lines):
		l = lines.pop()
		if l.strip() == "": break
		if not l.startswith(" "):
			# If there is no starting space, it means there were no stats rows,
			# and we're already looking at the next commit. Put this line back
			# on the list and move on
			lines.append(l)
			break
		diffstat.append(l.strip())

	# Figure out affected branches
	p = Popen("git branch --contains %s" % commitinfo[7:], shell=True, stdout=PIPE)
	branches = p.stdout.readlines()
	p.stdout.close()

	# Everything is parsed, put together an email
	mail = []
	mail.append("Commit: %s" % (
			c.get('commitmsg', 'gitweb').replace('$action','commitdiff').replace('$commit', commitinfo[7:])))
	mail.append("")
	mail.append("Log Message")
	mail.append("-----------")
	mail.extend(commitmsg)
	mail.append("")
	mail.append("Branches")
	mail.append("--------")
	mail.append("\n".join([branch.strip(' *') for branch in branches]))
	mail.append("")
	mail.append("Modified Files")
	mail.append("--------------")
	mail.extend(diffstat)

	msg = create_message("\n".join(mail),
						 authorinfo[7:],
						 c.get('commitmsg','subject').replace("$shortmsg",
															  commitmsg[0][:80-len(c.get('commitmsg','subject'))]))
	sendmail(msg)
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
			c.get('commitmsg','gitweb').replace('$action','tag').replace('$commit', 'refs/tags/%s' % tagname)))
	mail.append("")
	mail.append("Log Message")
	mail.append("-----------")

	for i in range(4, len(lines)):
		if lines[i].strip() == '':
			break
		mail.append(lines[i].rstrip())

	# Ignore the commit it's referring to here
	sendmail(
		create_message("\n".join(mail),
					   author,
					   c.get('commitmsg','subject').replace('$shortmsg', 'Tag %s has been created.' % tagname)))
	return

if __name__ == "__main__":
	# Get a list of refs on stdin, do something smart with it
	while True:
		l = sys.stdin.readline()
		if not l: break

		(oldobj, newobj, ref) = l.split()

		# Build the email
		if oldobj == "".zfill(40):
			# old object being all zeroes means a new branch or tag was created
			if ref.startswith("refs/heads/"):
				# It's a branch!
				sendmail(
					create_message("Branch %s was created.\n\nView: %s" % (
							ref,
							c.get('commitmsg', 'gitweb').replace('$action','shortlog').replace('$commit', ref),
							),
								   c.get('commitmsg', 'fallbacksender'),
								   c.get('commitmsg','subject').replace("$shortmsg",
																		"Branch %s was created" % ref)))
			elif ref.startswith("refs/tags/"):
				# It's a tag!
				# It can be either an annotated tag or a lightweight one.
				p = Popen("git cat-file -t %s" % ref, shell=True, stdout=PIPE)
				t = p.stdout.read().strip()
				p.stdout.close()
				if t == "commit":
					# Lightweight tag with no further information
					sendmail(
						create_message("Tag %s was created.\n" % ref,
									   c.get('commitmsg', 'fallbacksender'),
									   c.get('commitmsg','subject').replace("$shortmsg",
																			"Tag %s was created" % ref)))
				elif t == "tag":
					# Annotated tag! Get the description!
					p = Popen("git show %s" % ref, shell=True, stdout=PIPE)
					lines = p.stdout.readlines()
					p.stdout.close()
					parse_annotated_tag(lines)
				else:
					raise Exception("Unknown tag type '%s'" % t)
			else:
				raise Exception("Unknown branch/tag type %s" % ref)

		elif newobj == "".zfill(40):
			# new object being all zeroes means a branch was removed
			sendmail(
				create_message("Branch %s was removed." % ref,
							   c.get('commitmsg', 'fallbacksender'),
							   c.get('commitmsg','subject').replace("$shortmsg",
																	"Branch %s was removed" % ref)))
		else:
			# If both are real object ids, we can call git log on them
			cmd = "git log %s..%s --stat" % (oldobj, newobj)
			p = Popen(cmd, shell=True, stdout=PIPE)
			lines = p.stdout.readlines()
			lines.reverse()
			while parse_commit_log(lines):
				pass

	flush_mail()
