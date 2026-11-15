Website
============

https://kryptikk.de

```
curl kryptikk.de
```

Setup
-----

```
pip install -r requirements.txt
make check-deps
```

Usage
-----

```
$ make help
make build         default target, builds the site into ./_site
make check-deps    check to ensure needed dependencies are installed
make check         check tools syntax using shellcheck
make serve         serve site locally out of ./_site
make deploy        deploy the site (using rsync)
make all           build and deploy the site
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
