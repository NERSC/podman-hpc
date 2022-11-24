
DOCDIR=$(DESTDIR)/usr/share/doc/packages/podman-hpc


clean:
	rm -rf dist build

build:
	g++ -std=c++17 -static -o bin/exec-wait exec-wait.cpp

install: 
	python3 -m setup install --root=$(DESTDIR) --prefix=/usr
	mkdir -p $(DESTDIR)/etc/
	ln -s ../usr/etc/podman_hpc $(DESTDIR)/etc/podman_hpc

