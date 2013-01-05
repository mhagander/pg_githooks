#!/usr/bin/env python
#
# This is a simple policy enforcement script for the PostgreSQL project
# git server.
# It supports a couple of different policies that can be enforced on
# all commits.
#
# Note: the script (not surprisingly) uses the git commands in pipes, so git
# needs to be available in the path.
#
# Copyright (C) 2010-2013 PostgreSQL Global Development Group
# Author: Magnus Hagander <magnus@hagander.net>
#
# Released under the PostgreSQL license
#

#
# The script is configured by having a file named policyenforce.ini in the same
# directory as the script. See the README file for information about the contents.
#

import sys
import os.path
import re
from subprocess import Popen, PIPE
from ConfigParser import ConfigParser

#
# Load the global config
#
cfgname = "%s/policyenforce.ini" % os.path.dirname(sys.argv[0])
if not os.path.isfile(cfgname):
	raise Exception("Config file '%s' is missing!" % cfgname)
c = ConfigParser()
c.read(cfgname)

# Figure out if we should do debugging
try:
	debug = int(c.get('policyenforce', 'debug'))
except Exception, e:
	print "Except: %s" % e
	debug = 1

class PolicyObject(object):
	def _enforce(self, policyname):
		"""
		Check if a specific policy should be enforced, returning True/False
		"""
		try:
			enf = int(c.get("policies", policyname))
			if enf == 1:
				return True
			return False
		except Exception,e:
			return False

	def _enforce_str(self, policyname):
		"""
		Check if a specific policy should be enforced, returning a string
		containing the value of the policy, or None if the policy is not
		specified or empty.
		"""
		try:
			enf = c.get("policies", policyname).strip()
			if enf == "":
				return None
			return enf
		except Exception, e:
			return None


class Commit(PolicyObject):
	"""
	This class wraps a single commit, and the checking of policies on it.
	"""
	def __init__(self, commitid):
		"""
		Initialize and load basic information about a commit. Takes the SHA-1
		of a commit as parameter (should in theory work with other types of
		references as well).
		"""
		self.commitid = commitid
		self.tree = None
		self.parent = []
		self.author = None
		self.committer = None

		# Get the basic info about the commit using git cat-file
		p = Popen("git cat-file commit %s" % commitid, shell=True, stdout=PIPE)
		for l in p.stdout:
			if l == "\n":
				break
			elif l.startswith("tree "):
				self.tree = l[5:].strip()
			elif l.startswith("parent "):
				self.parent.append(l[7:].strip())
			elif l.startswith("author "):
				self.author = self._parse_author(l[7:].strip())
			elif l.startswith("committer "):
				self.committer = self._parse_author(l[10:].strip())
			else:
				raise Exception("Unknown commit info line for commit %s: %s" % (commitid, l))
		p.stdout.close()

		# Verify that the basic information we retrieved is complete.
		if not self.tree:
			raise Exception("Commit %s has no tree" % commitid)
		if len(self.parent) == 0:
			raise Exception("Commit %s has no parent(s)" % commitid)
		if not self.author:
			raise Exception("Commit %s has no author" % commitid)
		if not self.committer:
			raise Exception("Commit %s has no committer" % commitid)

	def _parse_author(self, authorstring):
		"""
		Parse an author record from a git object. Expects the format
		name <email> number timezone

		Returns the "name <email>" part.
		"""
		m = re.search('^([a-zA-Z0-9. ]+ <[^>]+>) \d+ [+-]\d{4}$', authorstring)
		if not m:
			raise Exception("User '%s' on commit %s does not follow format rules." % (authorstring, self.commitid))
		return m.group(1)

	def _policyfail(self, msg):
		"""
		Indicate that a commit violated a policy, and abort the program with the
		appropriate exitcode.
		"""
		print "Commit %s violates the policy: %s" % (self.commitid, msg)
		sys.exit(1)

	def check_policies(self):
		"""
		For this commit, check all policies that are enabled in the configuration
		file.
		"""

		if self._enforce("nomerge"):
			# Merge commits always have more than one parent
			if len(self.parent) != 1:
				self._policyfail("No merge commits allowed")

		if self._enforce("committerequalsauthor"):
			if self.author != self.committer:
				self._policyfail("Author (%s) must be equal to committer (%s)" % (self.author, self.committer))

		if self._enforce("committerlist"):
			# Enforce specific committer listed in config file.
			self.enforce_user(self.committer, 'Committer')

		if self._enforce("authorlist"):
			# Enforce specific author is listed in config file (as committer).
			self.enforce_user(self.author, 'Author')

	def enforce_user(self, user, usertype):
		# We do this by splitting the name again, and doing a lookup
		# match on that.
		m = re.search('^([a-zA-Z0-9. ]+) <([^>]+)>', user)
		if not m:
			raise Exception("%s '%s' for commit %s does not follow format rules." % (usertype, user, self.commitid))
		if not c.has_option('committers', m.group(1)):
			self._policyfail("%s %s not listed in committers section" % (usertype, m.group(1)))
		if not c.get('committers', m.group(1)) == m.group(2):
			self._policyfail("%s %s has wrong email (%s, should be %s)" % (
				usertype, m.group(1), m.group(2), c.get('committers', m.group(1))))

class Tag(PolicyObject):
	def __init__(self, ref, name):
		self.ref = ref
		self.name = name

	def check_policies(self):
		if self._enforce("nolightweighttag"):
			# A lightweight tag is a tag object, a "heavy" tag is
			# a commit object.
			p = Popen("git cat-file -t %s" % self.ref, shell=True, stdout=PIPE)
			t = p.stdout.read().strip()
			p.stdout.close()
			if t == "commit":
				self._policyfail("No lightweight tags allowed")

	def _policyfail(self, msg):
		"""
		Indicate that a tag violated a policy, and abort the program with the
		appropriate exitcode.
		"""
		print "Tag %s violates the policy: %s" % (self.name, msg)
		sys.exit(1)

class Branch(PolicyObject):
	def __init__(self, ref, name):
		self.ref = ref
		self.name = name

	def check_create(self):
		if self._enforce("nobranchcreate"):
			self._policyfail("No branch creation allowed")
		if self._enforce_str("branchnamefilter"):
			# All branch names starts with refs/heads/, so just remove that
			# when doing the regexp match
			if not re.match(self._enforce_str("branchnamefilter"),
							self.name[11:]):
				self._policyfail("Branch name does not match allowed regexp")

	def check_remove(self):
		if self._enforce("nobranchdelete"):
			self._policyfail("No branch removal allowed")

	def _policyfail(self, msg):
		"""
		Indicate that a branch violated a policy, and abort the program with the
		appropriate exitcode.
		"""
		print "Branch %s violates the policy: %s" % (self.name, msg)
		sys.exit(1)

if __name__ == "__main__":
	# Get a list of refs on stdin, do something smart with it
	ref = sys.argv[1]
	oldobj = sys.argv[2]
	newobj = sys.argv[3]

	if oldobj == "".zfill(40):
		# old object being all zeroes means a new branch or tag was created
		if ref.startswith("refs/heads/"):
			# It's a branch!
			Branch(newobj, ref).check_create()
		elif ref.startswith("refs/tags/"):
			# It's a tag!
			Tag(newobj, ref).check_policies()
		else:
			raise Exception("Unknown branch/tag type %s" % ref)

	elif newobj == "".zfill(40):
		# new object being all zeroes means a branch was removed
		Branch(newobj, ref).check_remove()
	else:
		# These are both real objects. Use git rev-list to identify
		# exactly which ones they are, and apply policies as needed.
		p = Popen("git rev-list %s..%s" % (oldobj, newobj), shell=True, stdout=PIPE)
		for l in p.stdout:
			if debug:
				print "Checking commit %s" % l.strip()
			Commit(l.strip()).check_policies()
			if debug:
				print "Commit ok."

	if debug:
		print "In debugging mode, refusing push unconditionally."
		sys.exit(1)
