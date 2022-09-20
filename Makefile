
DOCDIR=$(DESTDIR)/usr/share/doc/packages/podman-hpc


clean:
	rm -rf dist build

install:
	python3 -m setup install --root=$(DESTDIR) --prefix=/usr
	install -d ./etc $(DOCDIR)/



