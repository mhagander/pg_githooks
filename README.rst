PostgreSQL git scripts
======================
This projects holds some misc scripts for the PostgreSQL git repository,
mainly hooks. They're not intended to be complete - just to do the parts
that the PostgreSQL projects require.

Parts of it may of course apply to other projects as well...


git commit message script
=========================
This is a simplified (in some ways) and enhanced (in other ways) script
for sending commit messages from a git repository, specifically written
for the PostgreSQL repositories.

It doesn't deal with "advanced git workflows", it only accepts regular
commits in straight order. This is how the PostgreSQL project uses git,
so it's by design.

It creates commit messages that look a lot like those previously used
in the cvs environment. The main difference is that there will be a single
link to the full diff (using gitweb) instead of individual links for
each file. This is natural given that git deals with commits as atomic
units and not individually for each file like cvs does.

Installation & configuration
----------------------------
Copy or link the script ``commitmsg.py`` as ``hooks/post-receive`` in your (bare) git
repository. Make sure python is available at the given path, or adjust
the first line of the script to match where it is. git has to be available
in the path as well.

Create a file called ``hooks/commitmsg.ini``. This file will contain all the
configuration for the script. It should contain something like: ::

	[commitmsg]
	destination = somewhere@somewhere.com
	fallbacksender = somewhere@somewhere.com
	forcesenderaddr = noreply@somewhere.com
	forcesendername = Some Git Repository
	replyto = somewhere@somewhere.com, $committer
	subject = pgsql: $shortmsg
	gitweb = http://git.postgresql.org/gitweb?p=postgresql.git;a=$action;h=$commit
	debug = 0
	commitmsg = 1
	tagmsg = 1
	branchmsg = 1
	pingurl = http://somewhere.com/git_repo_updated

Expansion variables are available for the following fields:

subject
  shortmsg
gitweb
  action, commit

The following fields are all available under the [commitmsg] header:

destination
  is the address to send commit messages to. Multiple addresses can be
  specified with a comma in between, in which case multiple
  independent messages will be sent.
fallbacksender
  is the sender address to use for activities which don't have an author,
  such as creation/removal of a branch.
forcesenderaddr
  is the email address to use as sender of email, when an author can
  be found. In this case the name of the sender will be taken from
  the commit record, but the address is forced to the one specified
  here (to ensure DKIM compliance)
forcesendername
  is the name to use as the sender, instead of the committer name.
replyto
  is a comma separated list of addresses to add as reply-to.
  Use $committer to insert the email address of the committer (if one exists)
subject
  is the subject of the email
gitweb
  is a template URL for a gitweb link
debug
  set to 1 to output data on console instead of sending email
commitmsg, tagmsg, branchmsg
  set to 0 to disable generating this type of message. If unspecified or
  set to anything other than 0, the mail will be sent.
excludebranches
  set to a comma separated list of branch names that will *not* get commit messages
  sent for them (such as a CI branch or so). Branch creation and removal messages
  are still sent for such branches (assuming *branchmsg* is enabled).
includediff
  include the diff of the commit (up to 500 lines) at the end of the message
attacharchive
  set to 1 to attach a complete .tar.gz file of the entire branch
  that a commit was made on to the email. Only use this if the git
  repository is small!!!
pingurl
  set to one or more URLs to make the script send an empty HTTP post to this URL
  whenever something is received. This is useful for example to trigger
  a redmine installation to pull the repository. Separate multiple URLs with
  spaces.
  If $branch is included in the URL, insert the branchname in
  that position, and if multiple branches are pushed then ping
  all of them.


git policy enforcement script
=============================
This script performs some simple policy enforcment on git commits. Git supports
a lot of advanced operations that the PostgreSQL project doesn't use - or wants
to use. This script attempts to enforce as many of these policies as possible.

Installation & configuration
----------------------------
Copy or link the script ``policyenforce.py`` as ``hooks/update`` in your (bare) git
repository. Make sure python is available at the given path, or adjust
the first line of the script to match where it is. git has to be available
in the path as well.

Create a file called ``hooks/policyenforce.ini``. This file will contain all the
configuration for the script. It should contain something like: ::

	[policyenforce]
	debug = 0
	gpghome=/some/where/

	[policies]
	nomerge=1
	committerequalsauthor=1
	committerlist=1
	nolightweighttags=1
	nobranchcreate=1
	nobranchdelete=1
	branchnamefilter=REL_\d+$
	forcepushbranches=
	signcommits=1
	signtags=1

	[committers]
	Example User=example@example.org
	Example Other=other@example.org

The policy section lists which policies are available. Set a policy to 1 to
enforce the check, or 0 (or non-existant) to disable the check.

nomerge
	Enforce no merge commits. It's recommended that you use the core
	git feature for this as well (denyNonFastforwards = true).
signcommits
	Enforce that commits are GPG signed
signtags
	Enforce that tags are GPG signed
committerequalsauthor
	Enforce that the user listed under "committer" is the same as that
	under "author". This is for projects that track authors in the text
	contents of the message instead.
committerlist
	Enforce that the username and email of the committer is listed in the
	config file. This ensures that committers don't accidentally use a
	badly configured client. All the commiters should be listed in the
	[committers] section, in the format User Name=email.
authorlist
	Enforce that the username and email of the author is listed in the
	config file. It uses the same list of users as the committerlist,
	thus it should be listed in [committers]. This allows one committer
	to push things made by another committer, while still making sure
	all authors are registered.
nolightweighttags
	Enforce that there are no lightweight tags - only tags carrying
	a description are allowed.
nobranchcreate
	Enforce that new branches cannot be created.
nobranchdelete
	Enforce that existing branches cannot be removed (by pushing a
	branch with the name :*branch*)

There are also policies that should be set to a string:

branchnamefilter
	Set to a regular expression that will be applied to all new branches
	created. If the expression matches, the branch creation will be
	allowed, otherwise not. The expression will always be anchored at
	the beginning, but if you want it anchored at the end you need to
	add a $ at the end. Setting *nobranchcreate* will override this
	setting and not allow any branches at all.

forcepushbranches
	Set to a comma separated list of regular expressions (or just
	strings) that represent branches that *allow* forced
	pushing. If left empty, no check against forced pushing is
	made, and everything is allowed.  If set to any value, then
	any branch that does not match a pattern configured will
	refuse a forced push.


git command wrapper script
==========================
This script wraps the command run through ssh to make sure that it can
only be approved git commands, and to make sure the commands are logged
with who does what.

The script is adapted from the one running on git.postgresql.org, but
significantly simplified.

Installation & configuration
----------------------------
Put the script ``gitwrap.py`` "somewhere". In the same directory, create
a file called ``gitwrap.ini`` with contents like this: ::

	[paths]
	logfile=/some/where/gitwrap.log
	repobase=/some/where

Make sure the git user has permissions on these directories.

When this is done, put something like this in ``~/.ssh/authorized_keys``
for the git user: ::

	command="/home/git/gitwrap/gitwrap.py 'Some User'",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-rsa ABCDABCD<sshkeyhere>

One row for each committer.

The script will only allow access to repositories in the top level directory, and only
those that already exist. All users will be granted access to all repositories.
