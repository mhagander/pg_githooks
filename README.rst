PostgreSQL git commit message script
====================================
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
Copy or link the script as "hooks/post-receive" in your (bare) git
repository. Make sure python is available at the given path, or adjust
the first line of the script to match where it is. git has to be available
in the path as well.

Create a file called hooks/commitmsg.ini. This file will contain all the
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

