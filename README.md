# hardstage

Mirror a hand-picked selection of files from your home directory into a single
**staging directory** using hard links, so that any backup method (cloud sync,
rsync to a NAS, a burned disc, `tar`) only has to deal with one folder.

```
~/.thunderbird/…            ─┐
~/.mozilla/firefox/…         ├──  hardstage  ──>  ~/Backup/  ──>  your backup tool
~/.config/Trolltech.conf    ─┘    (hard links)
```

hardstage does not back anything up. It doesn't compress, encrypt, version, or
diff. It keeps `~/Backup` an accurate, near-zero-cost reflection of a list of
paths, and leaves the rest to whatever you point at it.

It is meant for things that don't belong in a dotfiles manager like
[chezmoi](https://www.chezmoi.io/): mail stores, browser profiles, photo
libraries, and other large, private, or "quality of life" state.

## Features

- A gitignore-style configuration file: includes, `!` excludes, globs, `**`
- Idempotent: each run converges the target onto the configuration
- Silent on success, so it fits in a crontab or a systemd timer
- No root, no dependencies beyond Python 3.8+ on Linux (or another POSIX
  system with `fcntl`)
- Refuses to manage a non-empty directory it didn't create
- Fails with a clear error when hard links aren't possible (unsupported
  filesystem, or source and target on different filesystems)
- Writes a `README.md` into the target explaining what the directory is

## Install

It's a single file. Either:

```sh
make install                    # copies hardstage.py to ~/.local/bin/hardstage
make install PREFIX=/usr/local  # or anywhere else
```

or `pipx install .`, or copy `hardstage.py` onto your `PATH` yourself.

## Quick start

```sh
hardstage init            # writes ~/.config/hardstage/config with examples
$EDITOR ~/.config/hardstage/config
hardstage list            # what would be staged, and how big it is
hardstage --dry-run       # what would change
hardstage                 # do it
```

## Configuration

The configuration lives at `$HARDSTAGE_CONFIG`, or
`$XDG_CONFIG_HOME/hardstage/config` (normally `~/.config/hardstage/config`).
`-c FILE` overrides both.

```gitignore
@target ~/Backup

# A single file
.config/Trolltech.conf

# Mail, minus lock files
.thunderbird/
!.thunderbird/*/lock
!.thunderbird/*/.parentlock

# Photos, minus thumbnail caches anywhere inside them
Pictures/
!.thumbnails/

# Keep a sync client's state directory in the target
@keep .stfolder
```

| Syntax | Meaning |
| --- | --- |
| `path` | Include a file or directory (recursively). Always relative to `~`; `/path` and `~/path` mean the same thing. |
| `!pattern` | Exclude. With no `/` (other than a trailing one) it matches a name at any depth, like `.gitignore`. With a `/` it is relative to `~`. |
| `pattern/` | Trailing slash: match directories only. |
| `*` `?` `[abc]` `[!abc]` | Globs within one path component. |
| `**` | Zero or more directories, as a whole component (`a/**/b`, `**/*.kdbx`). |
| `\#`, `\!`, `\@` | A literal leading `#`, `!`, or `@`. |
| `@target PATH` | The staging directory (default `~/Backup`). `-t DIR` overrides it. Relative paths are relative to `~`. |
| `@keep PATTERN` | A path in the target (relative to its root) that hardstage must never delete, e.g. a sync client's metadata. |
| `# …` | Comment. |

**The last matching line wins**, and a line matches a path if it matches the
path itself or any directory above it. So put broad includes first and
exceptions after them, and you can re-include something inside an excluded
directory by naming it on a later line.

Includes are always anchored at `~` so that hardstage only walks the
directories you name. A pattern whose first component is a glob (such as
`**/*.kdbx`) makes hardstage walk your entire home directory, which works but
is slow.

## How it works

On each run, hardstage:

1. Takes a lock (the `.hardstage` marker in the target), so overlapping runs
   from cron are harmless.
2. Walks the included paths and works out the set of files that should be
   staged.
3. For each file, makes sure `TARGET/<path>` is a hard link to `~/<path>`.
   Missing links are created. Links pointing to a stale inode are replaced
   atomically (see below).
4. Deletes anything in the target that is no longer selected, then removes
   empty directories.
5. Writes the target's `README.md` if it is missing or out of date.

Directories in the target are created with the same permissions as their
source (the target root itself is `0700`). Symbolic links are reproduced as
symbolic links with the same contents; they are never followed. Sockets,
FIFOs and device files are skipped. Empty directories are not staged.

If part of the source can't be read (permissions, a vanished directory), the
error is reported and the matching part of the target is left alone rather
than pruned.

## Things to know about hard links

Hard links are what make this cheap, but they come with real behavior to
understand.

**Same filesystem only.** A hard link can't cross filesystems, so the target
must live on the same filesystem as the files you stage, which in practice
means somewhere inside your home directory. hardstage checks this. If the
target filesystem can't do hard links at all (FAT, exFAT, many network and
FUSE mounts) it stops before touching anything. Files that are on a different
filesystem (a separately mounted `~/Pictures`, say) are reported and skipped.

**Atomic saves break links, and the next run repairs them.** Many programs
save by writing a new file and renaming it over the old one. After that, the
staged copy still points at the *old* contents. hardstage detects this (the
inodes differ) and relinks on its next run. **Run hardstage immediately before
your backup**, not only on an unrelated schedule:

```sh
hardstage && rclone sync ~/Backup remote:Backup
```

**The target is live.** The staged files *are* your files, so a backup that
runs while Thunderbird or Firefox is open reads databases that may be
mid-write. For SQLite-backed stores (browser profiles, many mail clients)
that can produce an inconsistent copy. If that matters, close those
applications before the backup, or back them up with a tool that understands
them.

**Writes go both ways.** Anything that writes into the target writes into
your real files. Use a *one-way* sync or upload. A two-way sync client, or
restoring a backup straight into the staging directory, can overwrite or
corrupt originals. Restore into your home directory instead (the generated
README in the target shows how).

**Deleting in the target is harmless.** It removes one of the two names. The
original stays, and hardstage puts the link back on its next run.

**`fs.protected_hardlinks`.** Most Linux distributions only let you hard-link
files you own (or can read and write). Files in your own home directory are
fine; anything else fails with "Operation not permitted" and is reported.

## Scheduling

hardstage prints nothing unless something goes wrong, so cron only mails you
about problems:

```crontab
# cron's PATH usually lacks ~/.local/bin, so use the full path
15 * * * *  $HOME/.local/bin/hardstage
```

Or with systemd user units:

```sh
make install-systemd
systemctl --user daemon-reload
systemctl --user enable --now hardstage.timer
```

## Using it with backup tools

Some ways to consume the staging directory:

```sh
# Cloud storage via rclone (one-way; rclone skips symlinks unless you pass -l)
hardstage && rclone sync ~/Backup myremote:Backup

# A NAS
hardstage && rsync -a --delete ~/Backup/ nas:/backups/$(hostname)/

# A disc image
hardstage && xorriso -as mkisofs -R -J -o backup.iso ~/Backup
```

## Command line

```
hardstage [sync|list|init] [-c FILE] [-t DIR] [-n] [-v] [-q]
```

| | |
| --- | --- |
| `sync` | Update the staging directory (the default). |
| `list` | Print the paths that would be staged, plus a count and total size on stderr. |
| `init` | Write an example configuration file. |
| `-n`, `--dry-run` | Show what would change without changing anything. |
| `-v`, `--verbose` | Print each change and a summary. |
| `-q`, `--quiet` | Suppress warnings. Errors are always printed. |

Exit status: `0` success, `1` finished with some errors, `2` fatal error
(nothing staged), `3` another run holds the lock.

## Development

```sh
make test
```

The program is the single file `hardstage.py`, using only the standard
library. `pyproject.toml` exposes it as a `hardstage` console script for pip,
pipx and distribution packaging, and the `Makefile` supports `DESTDIR` and
`PREFIX`.

## Related tools

- **`cp -al` / `rsync --link-dest`** build hard-link trees, but have no notion
  of a maintained selection that converges over time.
- **GNU Stow** manages symlinks in the other direction (from a package tree into
  `~`).
- **rclone, restic and borg** all accept include/exclude filter files and can
  back up straight from `~`. If you only ever use one of them, that may be
  all you need. hardstage is for when you want a tool-agnostic, browsable
  folder in between.

## License

MIT. See [LICENSE](LICENSE).
