> [!Prompt (Claude Opus 5.5 Medium)]
> Can you help me put together a project? Alternative: a thing like this already exists, in which case I'm happy to be pointed to it.
> 
> What it does: uses a configuration file to provision a directory and hard link structure with the goal of producing a directory that can be backed up at a time of the user's choosing. For example, synchronizing this directory with a cloud-based storage provider, burning it to a DVD, copying to network storage, whatever. This is very simple: no incremental storage, diffs, or the like. This is left to the entity conducting the backup. (In my case, I'd like to put together something that syncs this with Proton Drive but haven't gotten there yet.)
> 
> I'm not sure what this is called: pre-backup staging? Feel free to pick a name.
> 
> The idea is the user edits a file to contain a list of directories and files (`gitignore` style). The project uses this file to ensure a directory and hard link structure reflects the configuration. This requires some kind of mapping between the user's home directory and the target directory: for instance, tracking `~/.config/Trolltech.conf` might result in `~/Backup/.config/Trolltech.conf`.
> 
> Expected use case: things that are unsuitable being picked up by chezmoi, because they're not so much provisioning things as quality of life things, they're too big, or they contain information that isn't suitable for a public git repository. Email stores, browser profiles, maybe photo stores and so on.
> 
> Desired requirements:
> 
> - MIT License
> - A README.md suitable for a git repo
> - Linux-ish environment
> - No sudo required
> - Invoked under roughly the same circumstances as chezmoi; can be dropped in a crontab without too much fuss
> - Laid out such that install packaging is straightforward (not part of this effort)
> - Lightweight where it makes sense
> - Probably should fail gracefully if hard links aren't a thing on the target file system
> - Backup target directory gets a README.md that explains what it's for in case the user forgets

I'm not aware of a tool that does exactly this. Several come close, and I'll cover them at the end. I've built it as a small Python script and named it **hardstage** (hard links plus staging).

All 15 tests pass. Next I'll check the cross-filesystem failure path by pointing the target at tmpfs:

The cross-filesystem case fails with a clear error. Now I'll add the packaging files and docs.

The full repo is in **hardstage.zip**, and the README and the script are also attached on their own. The script is a single file of standard-library Python 3.8+ with no dependencies. The repo also includes the MIT license, a `pyproject.toml` (so `pipx install .` works), a `Makefile` with `PREFIX`/`DESTDIR` for packaging, systemd user units, an example config, and 15 passing unit tests.

**Does this already exist?** Not quite, as far as I know. `cp -al` and `rsync --link-dest` build hard-link trees but don't maintain a selection over time, and GNU Stow manages symlinks in the opposite direction. The closest alternative is to skip the staging directory: rclone, restic and borg all take include/exclude filter files and can back up straight from `~`. If Proton Drive will be your only backup target, that may be enough on its own. The value of hardstage is a tool-agnostic folder you can hand to anything, including a DVD burner.

**How it works:**
- **Config format:** gitignore-style, with last match winning. Includes are always relative to `~`, so it only walks the directories you name. An exclude without a `/` matches a name at any depth, so `!Cache/` excludes every `Cache` directory under your includes.
- **Directives:** `@target` sets the staging directory. `@keep` protects paths in the target that it must never delete, such as Syncthing's `.stfolder`.
- **Each run converges:** it creates missing links, replaces stale ones atomically, deletes anything no longer selected, and removes empty directories. It's silent on success, so cron only emails you about problems. A lock prevents overlapping runs.
- **Safety:** it refuses to manage a non-empty directory that lacks its `.hardstage` marker, since it deletes anything it doesn't manage. If part of the source can't be read, it leaves the matching part of the target alone instead of pruning it.
- **When hard links aren't possible:** it first test-links a file inside the target. On a filesystem without hard-link support it stops before changing anything. Files on a different filesystem from the target get a single summarised error instead of one per file.

**Hard-link behaviour that matters for your use case** (the README covers this in detail):
- **Atomic saves break links.** Many programs save by writing a new file and renaming it over the old one, which leaves the staged copy pointing at the old contents. The next run detects this and relinks, so run it right before the backup: `hardstage && <backup command>`.
- **Live databases can be copied mid-write.** Browser profiles and many mail stores are SQLite. If either app is open during the backup, the copy may be inconsistent.
- **The backup must be one-way.** The staged files *are* your real files, so a two-way sync client writing into the staging directory writes into your home directory.

**For Proton Drive:** as far as I know, rclone has a Proton Drive backend (`protondrive`). It's community-built rather than official Proton software, so check its current status. `hardstage && rclone sync ~/Backup proton:Backup` would be a one-way setup. Note that rclone skips symlinks unless you pass `-l`.

**Name:** I went with "hardstage". The other candidate I liked was "porch", as in where you leave things to be picked up.