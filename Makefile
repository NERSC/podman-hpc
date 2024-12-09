.PHONY: clean setuptools-build_py build rpmbuild-install install

DOCDIR=$(DESTDIR)/usr/share/doc/packages/podman-hpc

all: build

clean:
	rm -rf dist build *.egg-info MANIFEST bin/exec-wait podman_hpc/*.pyc podman_hpc/__pycache__

build:
	echo "Nothing to do"

rpmbuild-install: 
	python3 -m setup install --root=$(DESTDIR) --prefix=/usr --install-data=/
	python3 -m podman_hpc.configure_hooks \
		--hooksd $(DESTDIR)/usr/share/containers/oci/hooks.d
	mkdir -p $(DESTDIR)/etc/

install: rpmbuild-install
