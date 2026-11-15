Website
============

https://kryptikk.de

```
curl kryptikk.de
```

Setup
-----

```
make venv
make check-deps
```

Usage
-----

```
$ make help
make build         default target, builds the site into ./_site
make venv          create ./.venv and install pinned requirements
make check-deps    check to ensure needed dependencies are installed
make check         check tools syntax using shellcheck
make serve         serve site locally out of ./_site
make deploy        deploy the site (using rsync)
make update-nginx  copy nginx config if changed
make all           clean, build and deploy the site
make clean         remove any generated files
```

Upgrade
-------

Pull the latest changes, rebuild and deploy in one step:

```
./upgrade
```

Lizenz / Herkunft
-----------------

Teile dieses Projekts basieren auf der ysap-Website von Dave Eddy
(https://github.com/bahamas10/ysap, MIT). Details, Dateiliste und Lizenztext
stehen in [NOTICE](NOTICE).
