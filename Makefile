# Create, manage, and deploy the YSAP website
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
	@echo 'make all           build and deploy the site'
	@echo 'make clean         remove any generated files'

.PHONY: build
build:
	mkdir -p _site _site/static _site/schedule
	# disable indexing for certain dirs
	echo -n > _site/static/index.html
	# copy static files
	cat static/favicon.ico > _site/favicon.ico
	cat static/robots.txt > _site/robots.txt
	cat static/style.css > _site/static/style.css
	cat static/ansi.css > _site/static/ansi.css
	cat static/index.html > _site/index.html
	cat static/schedule.html > _site/schedule/index.html
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
	sudo rsync -avh --delete ./_site/ /var/www/ljunker.de/html
