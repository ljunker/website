# Create, manage, and deploy the website
#
# Basiert auf ysap von Dave Eddy (MIT), siehe NOTICE



# duh
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: help
help:
	@echo 'make build         default target, builds the site into ./_site'
	@echo 'make venv          create ./.venv and install pinned requirements'
	@echo 'make check-deps    check to ensure needed dependencies are installed'
	@echo 'make check         check tools syntax using shellcheck'
	@echo 'make serve         serve site locally out of ./_site'
	@echo 'make deploy        deploy the site (using rsync)'
	@echo 'make update-nginx  copy nginx config if changed'
	@echo 'make all           clean, build and deploy the site'
	@echo 'make clean         remove any generated files'

.PHONY: build
build:
	mkdir -p _site _site/static _site/schedule _site/drei-fragezeichen _site/sammlungen _site/one-piece _site/dn9lfj _site/impressum _site/schrittjagd-support _site/schrittjagd-datenschutz _site/schrittjagd-delete
	# disable indexing for certain dirs
	echo -n > _site/static/index.html
	# copy static files
	cat static/favicon.ico > _site/favicon.ico
	cat static/robots.txt > _site/robots.txt
	cat static/style.css > _site/static/style.css
	cat static/ansi.css > _site/static/ansi.css
	cp static/ical.min.js _site/static/ical.min.js
	mkdir -p _site/static/fonts
	cp static/fonts/* _site/static/fonts/
	./make-page static/index.html > _site/index.html
	./make-page static/404.html > _site/404.html
	./make-page static/schedule.html > _site/schedule/index.html
	./make-page static/drei-fragezeichen.html > _site/drei-fragezeichen/index.html
	./make-page static/sammlungen.html > _site/sammlungen/index.html
	./make-page static/one-piece.html > _site/one-piece/index.html
	./make-page static/dn9lfj.html > _site/dn9lfj/index.html
	./make-page static/impressum.html > _site/impressum/index.html
	./make-page static/schrittjagd-support.html > _site/schrittjagd-support/index.html
	./make-page static/schrittjagd-datenschutz.html > _site/schrittjagd-datenschutz/index.html
	./make-page static/schrittjagd-delete.html > _site/schrittjagd-delete/index.html
	# make /ping endpoint (nginx handles this for me, but just in case)
	echo 'pong' > _site/ping
	# create ASCII index page for curl users
	./make-index > _site/index.txt
	# create ASCII help page
	./make-help > _site/help
	./make-events
	# create episodes ASCII table
	./make-schedule > _site/schedule/index.txt
	# make episodes JSON file for curl
	./make-schedule-json > _site/json
	cat _site/json > _site/schedule.json
	./make-drei-fragezeichen
	./make-drei-fragezeichen-index > _site/drei-fragezeichen/index.txt
	./make-drei-fragezeichen-json DREI > _site/static/drei.js
	cp -r static/images _site
	./make-one-piece-index > _site/one-piece/index.txt
	.venv/bin/python3 ./one_piece_sheet.py --js ONEPIECE > _site/static/one-piece.js
	./make-dn9lfj-index > _site/dn9lfj/index.txt

.PHONY: all
all:
	$(MAKE) clean
	$(MAKE) build
	$(MAKE) deploy

.PHONY: venv
venv:
	if [[ ! -x .venv/bin/python3 ]]; then python3 -m venv .venv; fi
	.venv/bin/python3 -m pip install -r requirements.txt

.PHONY: serve
serve:
	python3 -mhttp.server -d _site

.PHONY: check-deps
check-deps:
	./check-deps

.PHONY: check
check:
	shellcheck -x check-* make-* upgrade tools/*

.PHONY: clean
clean:
	rm -rf _site

.PHONY: deploy
deploy:
	sudo rsync -avh --delete ./_site/ /var/www/kryptikk.de/html

.PHONY: update-nginx
update-nginx:
	@if ! sudo test -e /etc/nginx/sites-available/kryptikk.de || ! sudo cmp -s kryptikk.de /etc/nginx/sites-available/kryptikk.de; then \
		backup="/tmp/kryptikk.de.$$(date +%Y%m%d%H%M%S).bak"; \
		echo "Updating /etc/nginx/sites-available/kryptikk.de (backup: $$backup)"; \
		if sudo test -e /etc/nginx/sites-available/kryptikk.de; then \
			sudo cp /etc/nginx/sites-available/kryptikk.de "$$backup"; \
		fi; \
		sudo cp kryptikk.de /etc/nginx/sites-available/kryptikk.de; \
		if sudo nginx -t; then \
			echo "nginx -t ok, reloading nginx"; \
			sudo systemctl reload nginx; \
		else \
			echo "nginx -t failed, restoring backup"; \
			if sudo test -e "$$backup"; then \
				sudo cp "$$backup" /etc/nginx/sites-available/kryptikk.de; \
			fi; \
			sudo nginx -t; \
		fi; \
	else \
		echo "nginx config unchanged"; \
	fi
