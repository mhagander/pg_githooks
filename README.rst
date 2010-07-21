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
	subject = pgsql: $shortmsg
	gitweb = http://git.postgresql.org/gitweb?p=postgresql.git;a=$action;h=$commit
	debug = 0

Expansion variables are available for the following fields:

subject
  shortmsg
gitweb
  action, commit

The following fields are all available under the [commitmsg] header:

destination
  is the address to send commit messages to.
fallbacksender
  is the sender address to use for activities which don't have an author,
  such as creation/removal of a branch.
subject
  is the subject of the email
gitweb
  is a template URL for a gitweb link
debug
  set to 1 to output data on console instead of sending email


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
	
	[policies]
	nomerge=1
	committerequalsauthor=1
	committerlist=1
	
	[committers]
	Example User=example@example.org
	Example Other=other@example.org

The policy section lists which policies are available. Set a policy to 1 to
enforce the check, or 0 (or non-existant) to disable the check.

nomerge
	Enforce no merge commits. It's recommended that you use the core
	git feature for this as well (denyNonFastforwards = true).
committerequalsauthor
	Enforce that the user listed under "committer" is the same as that
	under "author". This is for projects that track authors in the text
	contents of the message instead.
committerlist
	Enforce that the username and email of the committer is listed in the
	config file. This ensures that committers don't accidentally use a
	badly configured client. All the commiters should be listed in the
	[committers] section, in the format User Name=email.


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
	gitrepo=/some/where/repository.git

Make sure the git user has permissions on these directories.

When this is done, put something like this in ``~/.ssh/authorized_keys``
for the git user: ::

	command="/home/git/gitwrap/gitwrap.py 'Some User'",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-rsa ABCDABCD<sshkeyhere>

One row for each committer.
