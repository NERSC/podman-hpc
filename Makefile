
DOCDIR=$(DESTDIR)/usr/share/doc/packages/podman-hpc


clean:
	rm -rf dist build *.egg-info MANIFEST

build:
	g++ -std=c++17 -static -o bin/exec-wait exec-wait.cpp

install: 
	python3 -m setup install --root=$(DESTDIR) --prefix=/usr
	python3 -m podman_hpc.configure_hooks \
		--hooksd $(DESTDIR)/usr/share/containers/oci/hooks.d
	mkdir -p $(DESTDIR)/etc/
	ln -s ../usr/etc/podman_hpc $(DESTDIR)/etc/podman_hpc


