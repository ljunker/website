# Create, manage, and deploy the website
#



# duh
SHELL := bash

.PHONY: help
help:
	@echo 'make build         default target, builds the site into ./_site'
	@echo 'make check-deps    check to ensure needed dependencies are installed'
	@echo 'make check         check tools syntax using shellcheck'
	@echo 'make serve         serve site locally out of ./_site'
	@echo 'make deploy        deploy the site (using rsync)'
	@echo 'make update-nginx  copy nginx config if changed'
	@echo 'make all           build and deploy the site'
	@echo 'make clean         remove any generated files'

.PHONY: build
build:
	mkdir -p _site _site/static _site/schedule _site/drei-fragezeichen _site/sammlungen _site/one-piece
	# disable indexing for certain dirs
	echo -n > _site/static/index.html
	# copy static files
	cat static/favicon.ico > _site/favicon.ico
	cat static/robots.txt > _site/robots.txt
	cat static/style.css > _site/static/style.css
	cat static/ansi.css > _site/static/ansi.css
	cat static/index.html > _site/index.html
	cat static/schedule.html > _site/schedule/index.html
	cat static/drei-fragezeichen.html > _site/drei-fragezeichen/index.html
	cat static/sammlungen.html > _site/sammlungen/index.html
	cat static/one-piece.html > _site/one-piece/index.html
	cat static/nav.html > _site/nav.html
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
	# make jsonp for our HTML files
	./make-schedule-json SCHEDULE > _site/static/schedule.js
	cat _site/json > _site/schedule.json
	./make-drei-fragezeichen
	./make-drei-fragezeichen-index > _site/drei-fragezeichen/index.txt
	./make-drei-fragezeichen-json DREI > _site/static/drei.js
	./make-one-piece-index > _site/one-piece/index.txt

.PHONY: all
all: build deploy

.PHONY: serve
serve:
	python3 -mhttp.server -d _site

.PHONY: check-deps
check-deps:
	./check-deps

.PHONY: check
check:
	shellcheck -x check-* make-* tools/*

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
			echo "nginx -t ok"; \
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
