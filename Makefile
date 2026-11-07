PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
SYSTEMD_USER_DIR ?= $(HOME)/.config/systemd/user

.PHONY: install install-systemd uninstall test

install:
	install -Dm755 hardstage.py $(DESTDIR)$(BINDIR)/hardstage

install-systemd:
	install -Dm644 contrib/systemd/hardstage.service $(DESTDIR)$(SYSTEMD_USER_DIR)/hardstage.service
	install -Dm644 contrib/systemd/hardstage.timer $(DESTDIR)$(SYSTEMD_USER_DIR)/hardstage.timer

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/hardstage
	rm -f $(DESTDIR)$(SYSTEMD_USER_DIR)/hardstage.service $(DESTDIR)$(SYSTEMD_USER_DIR)/hardstage.timer

test:
	python3 -m unittest discover -s tests -v
