
DOCDIR=$(DESTDIR)/usr/share/doc/packages/podman-hpc


clean:
	rm -rf dist build

build:
	g++ -static -o exec-wait exec-wait.cpp

install:
	python3 -m setup install --root=$(DESTDIR) --prefix=/usr
	install -d ./etc $(DOCDIR)/
	install ./bin/fuse-overlayfs-wrap $(DESTDIR)/usr/bin/
	mkdir -p $(DESTDIR)/etc/podman_hpc/
	install ./etc/nersc-plug.yaml $(DESTDIR)/etc/podman_hpc/
	install ./etc/01-gpu.conf $(DESTDIR)/etc/podman_hpc/
	install ./etc/02-mpich.conf $(DESTDIR)/etc/podman_hpc/
	mkdir -p $(DESTDIR)//usr/share/containers/oci/hooks.d/
	install ./hooks.d/02-hook_tool.json $(DESTDIR)//usr/share/containers/oci/hooks.d/



